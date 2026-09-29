"""ShyClone — moteur de capture de sites.

Chaque capture est un « job » isolé : ses fichiers vivent dans clones/<job_id>,
ce qui permet de prévisualiser et de télécharger une capture précise sans que
deux exécutions se mélangent.

API consommée par l'interface :
    POST /api/check              teste qu'une URL répond
    POST /api/clone              démarre un job
    GET  /api/jobs/<id>          état + journal du job (paramètre ?from=n)
    POST /api/jobs/<id>/abort    interrompt le job
    GET  /api/jobs/<id>/zip      archive de la capture
    GET  /preview/<id>/<chemin>  sert les fichiers capturés
"""

import gzip
import hashlib
import ipaddress
import os
import secrets
import socket
import tempfile
import posixpath
import re
import shutil
import threading
import time
import uuid
import zipfile
import zlib
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

try:
    import brotli
except ImportError:                     # dépendance facultative
    brotli = None

import requests
import urllib3
from requests.adapters import HTTPAdapter

# Les tentatives sans vérification du certificat sont volontaires et déjà
# signalées dans le journal du job ; l'avertissement de la bibliothèque ferait
# doublon à chaque ressource.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import navigateur as nav
from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

# ── Configuration ────────────────────────────────────────────────────────────
RACINE = Path(__file__).resolve().parent.parent
DOSSIER_CLONES = RACINE / "clones"
# PORT est la variable injectée par les hébergeurs (Render, Railway, Fly…).
PORT = int(os.environ.get("PORT") or os.environ.get("SHYCLONE_PORT") or 5000)
HOTE = os.environ.get("SHYCLONE_HOST", "127.0.0.1")
# Protection facultative, pour un moteur exposé sur Internet. Vide en local :
# rien ne change. Renseignée, elle empêche un inconnu de faire télécharger
# n'importe quel site par votre serveur.
JETON = os.environ.get("SHYCLONE_TOKEN", "").strip()

# Code de vérification Google Search Console, injecté dans la page pour éviter
# d'avoir à reconstruire l'image à chaque changement.
VERIF_GOOGLE = os.environ.get("SHYCLONE_VERIF_GOOGLE", "").strip()

# Mot de passe d'accès (authentification HTTP « Basic »). Vide en local : rien
# ne change. Renseigné, il ferme l'application entière — interface, API et
# aperçu — sans page de connexion à maintenir : le navigateur retient les
# identifiants et les renvoie pour l'iframe comme pour le téléchargement.
MDP = os.environ.get("SHYCLONE_MDP", "").strip()
UTILISATEUR = os.environ.get("SHYCLONE_UTILISATEUR", "shy").strip()

# Derrière un hébergeur (Render, Fly…), la requête arrive en clair avec
# l'en-tête X-Forwarded-Proto. Actif dès que le moteur n'écoute plus en local.
_https = os.environ.get("SHYCLONE_FORCE_HTTPS")
FORCER_HTTPS = (HOTE != "127.0.0.1") if _https is None else _https not in ("0", "false", "")

# Nombre de requêtes tolérées par adresse IP et par heure. Un aspirateur de
# sites laissé ouvert se fait sinon utiliser en boucle.
QUOTA_CLONE = int(os.environ.get("SHYCLONE_QUOTA_CLONE") or 12)
QUOTA_CHECK = int(os.environ.get("SHYCLONE_QUOTA_CHECK") or 60)
FENETRE = 3600

# Interdit au moteur d'aller chercher une adresse interne (127.x, 10.x, 192.168.x,
# 169.254.169.254 des métadonnées cloud…). Sans ce filtre, un moteur exposé sur
# Internet devient un relais pour scanner le réseau privé qui l'héberge.
# Actif dès que le moteur écoute ailleurs que sur la boucle locale.
_prive = os.environ.get("SHYCLONE_BLOQUER_PRIVE")
BLOQUER_PRIVE = (HOTE != "127.0.0.1") if _prive is None else _prive not in ("0", "false", "")

DOSSIER_UI = RACINE / "dist"

# Se présenter en navigateur réel : beaucoup de sites renvoient 403 à un
# client qui s'annonce comme robot.
AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
ENTETES = {
    "User-Agent": AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br" if brotli else "gzip, deflate",
}
# Niveaux de parallélisme. Réglables pour s'adapter à la tolérance du site
# visé : trop haut, on se fait bannir avant d'avoir fini.
# Mesuré sur une capture de 40 pages : 5,9 s à 5/8, 4,0 s à 8/12, 3,3 s à
# 12/16. Au-delà le gain se tasse et le risque de bannissement grimpe — c'est
# une trentaine de connexions simultanées sur un seul serveur.
ASSETS_PARALLELES = int(os.environ.get("SHYCLONE_ASSETS_PAR") or 12)
PAGES_PARALLELES = int(os.environ.get("SHYCLONE_PAGES_PAR") or 8)
PAGES_PARALLELES_RENDU = int(os.environ.get("SHYCLONE_PAGES_PAR_RENDU") or 2)
CODES_BLOCAGE = (401, 403, 429)
# Délai réseau par requête. Relevé à 20 s : certains hébergements régionaux
# répondent lentement, et un timeout court les faisait passer pour injoignables.
DELAI = int(os.environ.get("SHYCLONE_DELAI") or 20)
PAGES_DEFAUT = 50
PAGES_MAX = 5000
ASSETS_MAX = 8000
POIDS_MAX = 1024 * 1024 * 1024   # garde-fou : 1 Go par capture
JOBS_CONSERVES = 8               # au-delà, les dossiers les plus vieux sont purgés
# Une capture est effacée ce nombre de secondes après la fin du job.
RETENTION = int(os.environ.get("SHYCLONE_RETENTION") or 13 * 60)


def duree_retention():
    """Rend la rétention lisible, y compris si elle est réglée sous la minute."""
    return f"{RETENTION // 60} min" if RETENTION >= 60 else f"{RETENTION} s"

TYPES_PAGE = ("text/html", "application/xhtml+xml")
SCHEMAS_IGNORES = ("mailto:", "tel:", "javascript:", "data:", "blob:", "about:", "sms:")
BALISES_ASSET = {
    "img", "script", "iframe", "source", "video", "audio", "embed", "track", "object",
}

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

JOBS = {}
VERROU_JOBS = threading.Lock()

APPELS = defaultdict(list)          # ip -> horodatages
VERROU_APPELS = threading.Lock()


def adresse_client():
    """IP réelle du visiteur, en tenant compte du proxy de l'hébergeur."""
    transmise = request.headers.get("X-Forwarded-For", "")
    if transmise:
        return transmise.split(",")[0].strip()
    return request.remote_addr or "?"


def quota_depasse(cle, limite):
    maintenant = time.time()
    with VERROU_APPELS:
        recents = [t for t in APPELS[cle] if maintenant - t < FENETRE]
        if len(recents) >= limite:
            APPELS[cle] = recents
            return True
        recents.append(maintenant)
        APPELS[cle] = recents
    return False


@app.before_request
def imposer_https():
    """Redirige le trafic en clair et demande au navigateur de ne plus y revenir."""
    if not FORCER_HTTPS:
        return None
    if request.headers.get("X-Forwarded-Proto", "https") == "http":
        return Response("", 308, {"Location": request.url.replace("http://", "https://", 1)})
    return None


@app.after_request
def entetes_reponse(reponse):
    """Aucune signature de la pile technique, et quelques en-têtes de sécurité."""
    reponse.headers["Server"] = "ShyClone"
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    # « no-referrer » partout, sauf pour les pages d'aperçu : le référent est
    # ce qui permet de rattacher à leur capture les ressources que le JS du
    # site demande à la racine du serveur. « same-origin » ne le divulgue
    # qu'à nous-mêmes.
    reponse.headers["Referrer-Policy"] = (
        "same-origin" if request.path.startswith("/preview/") else "no-referrer"
    )
    reponse.headers.pop("X-Powered-By", None)
    if FORCER_HTTPS:
        reponse.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Ceinture et bretelles : un robot qui ignorerait robots.txt se heurte
    # quand même à cet en-tête sur les copies de sites tiers.
    if request.path.startswith("/preview/"):
        reponse.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return reponse


@app.errorhandler(404)
def _404(_):
    return jsonify({"statut": "error", "message": "Ressource introuvable."}), 404


@app.errorhandler(405)
def _405(_):
    return jsonify({"statut": "error", "message": "Méthode non autorisée."}), 405


@app.errorhandler(Exception)
def _erreur(exc):
    """Renvoie un message neutre : ni trace d'exécution, ni nom de fichier."""
    code = getattr(exc, "code", 500)
    if not isinstance(code, int) or code < 400:
        code = 500
    if code >= 500:
        print(f"[ShyClone] erreur interne : {type(exc).__name__}: {exc}")
        return jsonify({"statut": "error", "message": "Erreur interne."}), 500
    return jsonify({"statut": "error", "message": "Requête invalide."}), code


@app.before_request
def controler_acces():
    """Ferme l'application derrière un mot de passe, si un mot de passe existe."""
    if not MDP or request.method == "OPTIONS":
        return None
    # La sonde de santé de l'hébergeur passe sans identifiants, sinon le
    # service est déclaré en panne et redémarré en boucle.
    if request.path == "/api/health":
        return None
    a = request.authorization
    if (a and a.type == "basic"
            and secrets.compare_digest(a.username or "", UTILISATEUR)
            and secrets.compare_digest(a.password or "", MDP)):
        return None
    return Response("", 401, {"WWW-Authenticate": 'Basic realm="ShyClone"'})


@app.before_request
def controler_jeton():
    """Filtre les routes /api quand un jeton est configuré.

    /preview reste ouvert : les identifiants de job sont aléatoires et
    imprévisibles, et l'iframe ne peut pas ajouter d'en-tête aux requêtes des
    ressources de la page capturée.
    """
    if request.method == "OPTIONS" or not request.path.startswith("/api/"):
        return None
    # Une page capturée affichée dans l'aperçu ne doit jamais atteindre l'API,
    # même lorsqu'elle partage l'origine de l'application.
    if urlsplit(request.headers.get("Referer", "")).path.startswith("/preview/"):
        return jsonify({"statut": "error", "message": "Requête refusée."}), 403
    if not JETON or request.path == "/api/health":
        return None
    fourni = request.headers.get("X-ShyClone-Token") or request.args.get("jeton", "")
    if not secrets.compare_digest(fourni, JETON):
        return jsonify({"statut": "error", "message": "Jeton manquant ou invalide."}), 401
    return None


# ── Utilitaires ──────────────────────────────────────────────────────────────
def separer_ancre(url):
    """Sépare l'URL de son fragment (#section)."""
    base, sep, frag = url.partition("#")
    return base, (sep + frag if sep else "")


def normaliser(url):
    """Retire le fragment et la barre finale superflue pour dédoublonner."""
    p = urlsplit(url)
    chemin = p.path or "/"
    return urlunsplit((p.scheme, p.netloc, chemin, p.query, ""))


def meme_hote(a, b):
    """Compare deux hôtes en ignorant le www. et la casse."""
    a = a.lower().removeprefix("www.")
    b = b.lower().removeprefix("www.")
    return a == b


def assainir(segment):
    """Rend un segment de chemin sûr pour le système de fichiers."""
    segment = re.sub(r"[^A-Za-z0-9._-]", "_", unquote(segment))
    segment = segment.lstrip(".") or "_"
    return segment[:100]


def chemin_local(url, est_page, hote_racine):
    """Traduit une URL en chemin relatif dans le dossier de capture.

    Les ressources d'un autre domaine atterrissent sous _externe/<hote>/ pour
    que l'archive reste utilisable hors ligne.
    """
    p = urlsplit(url)
    chemin = p.path or "/"
    if chemin.endswith("/"):
        chemin += "index.html"

    segments = [assainir(s) for s in chemin.split("/") if s not in ("", ".", "..")]
    if not segments:
        segments = ["index.html"]

    if p.query:
        # /page?id=1 et /page?id=2 sont deux fichiers distincts.
        suffixe = "_q" + hashlib.sha1(p.query.encode()).hexdigest()[:8]
        nom = segments[-1]
        tige, point, ext = nom.rpartition(".")
        segments[-1] = f"{tige}{suffixe}.{ext}" if point else f"{nom}{suffixe}"

    if est_page and not segments[-1].lower().endswith((".html", ".htm")):
        segments[-1] += ".html"

    if not meme_hote(p.netloc, hote_racine):
        segments = ["_externe", assainir(p.netloc)] + segments

    return "/".join(segments)


def chemin_sur(base, relatif):
    """Résout `relatif` sous `base` en refusant toute sortie du dossier."""
    cible = (base / relatif).resolve()
    base = base.resolve()
    if cible != base and base not in cible.parents:
        return None
    return cible


def lien_relatif(cible, depuis):
    """Chemin de `cible` vu depuis le fichier `depuis` (chemins POSIX)."""
    return posixpath.relpath(cible, posixpath.dirname(depuis) or ".")


def decoder(brut, type_contenu):
    """Décode des octets HTML/CSS en respectant le charset annoncé."""
    m = re.search(r"charset=[\"']?([\w-]+)", type_contenu or "", re.I)
    encodage = m.group(1) if m else None
    if not encodage:
        m = re.search(rb"charset=[\"']?([\w-]+)", brut[:4096], re.I)
        encodage = m.group(1).decode("ascii", "ignore") if m else "utf-8"
    try:
        return brut.decode(encodage, errors="replace")
    except LookupError:
        return brut.decode("utf-8", errors="replace")


def verifier_cible(url):
    """Refuse une URL qui pointe vers le réseau interne. Lève ValueError."""
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("adresse non autorisée")
    if not BLOQUER_PRIVE:
        return
    try:
        infos = socket.getaddrinfo(p.hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError("domaine introuvable") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            raise ValueError("adresse réseau non autorisée")


def faire_session():
    """Session HTTP avec réutilisation des connexions.

    Rouvrir une connexion TLS à chaque ressource coûtait 72 % du temps de
    capture sur un site de documentation : dix requêtes passaient de 6,1 s à
    1,7 s une fois la connexion gardée ouverte.
    """
    session = requests.Session()
    adaptateur = HTTPAdapter(
        pool_connections=12,
        pool_maxsize=ASSETS_PARALLELES + PAGES_PARALLELES + 8,
        max_retries=0,
    )
    session.mount("https://", adaptateur)
    session.mount("http://", adaptateur)
    session.headers.update(ENTETES)
    return session


SESSION_GLOBALE = faire_session()

def hote_alternatif(url):
    """Renvoie la même URL avec ou sans « www. », ou None."""
    p = urlsplit(url)
    hote = p.netloc
    autre = hote[4:] if hote.lower().startswith("www.") else "www." + hote
    return urlunsplit((p.scheme, autre, p.path, p.query, "")) if autre != hote else None


def resoudre(hote):
    try:
        socket.getaddrinfo(hote, None, proto=socket.IPPROTO_TCP)
        return True
    except socket.gaierror:
        return False


def corriger_hote(url):
    """Bascule vers la variante www quand le domaine saisi ne résout pas.

    www.mtn.cm n'a pas d'enregistrement DNS alors que mtn.cm en a un : sans ce
    repli, l'adresse que tout le monde tape est déclarée injoignable.
    """
    p = urlsplit(url)
    if not p.hostname or resoudre(p.hostname):
        return url
    autre = hote_alternatif(url)
    if autre and resoudre(urlsplit(autre).hostname):
        return autre
    return url


def telecharger(url, cookies=None, session=None):
    """Récupère une URL. Renvoie (octets, mime, en-tête, url_finale, tls_souple).

    Les redirections sont suivies à la main pour revalider chaque saut : une
    URL publique peut rediriger vers une adresse interne.
    """
    session = session or SESSION_GLOBALE
    verifier_cible(url)
    entetes = {"Cookie": cookies} if cookies else None

    def parcourir(verifier_tls):
        courant = url
        for _ in range(8):
            reponse = session.get(
                courant, headers=entetes, timeout=DELAI,
                allow_redirects=False, verify=verifier_tls,
            )
            if reponse.is_redirect or reponse.is_permanent_redirect:
                suivant = urljoin(courant, reponse.headers.get("Location", ""))
                reponse.close()
                verifier_cible(suivant)
                courant = suivant
                continue
            return reponse, courant
        raise ValueError("trop de redirections")

    try:
        reponse, finale = parcourir(True)
        souple = False
    except requests.exceptions.SSLError:
        if cookies:
            # Sans certificat vérifié, transmettre la session de l'utilisateur
            # reviendrait à l'exposer à une interception.
            raise
        reponse, finale = parcourir(False)
        souple = True

    # Le site demande de lever le pied : on attend et on retente une fois
    # plutôt que d'insister et de se faire bannir.
    if reponse.status_code in (429, 503):
        attente = reponse.headers.get("Retry-After", "")
        reponse.close()
        try:
            pause = min(float(attente), 6.0)
        except ValueError:
            pause = 2.0
        time.sleep(max(1.0, pause))
        reponse, finale = parcourir(not souple)

    if reponse.status_code >= 400:
        code = reponse.status_code
        reponse.close()
        raise HTTPError(finale, code, f"HTTP {code}", None, None)

    brut = reponse.content
    entete = reponse.headers.get("Content-Type") or ""
    reponse.close()
    # Garde-fou : quelques serveurs renvoient du gzip sans l'annoncer, la
    # bibliothèque ne le décode alors pas.
    if brut[:2] == b"\x1f\x8b":
        try:
            brut = gzip.decompress(brut)
        except OSError:
            pass
    return brut, entete.split(";")[0].strip().lower(), entete, finale, souple


def message_erreur(exc):
    """Traduit une exception réseau en message lisible."""
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, requests.exceptions.SSLError):
        return "certificat TLS invalide"
    if isinstance(exc, requests.exceptions.Timeout):
        return "délai dépassé"
    if isinstance(exc, requests.exceptions.ConnectionError):
        texte = str(exc).lower()
        if "name or service not known" in texte or "nodename nor servname" in texte:
            return "domaine introuvable"
        if "connection refused" in texte:
            return "connexion refusée"
        return "connexion impossible"
    if isinstance(exc, HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, TimeoutError):
        return "délai dépassé"
    return str(exc) or type(exc).__name__


# ── Modèle de job ────────────────────────────────────────────────────────────
class Job:
    def __init__(self, url, pages_max, cookies=None, rendu_js=False):
        self.id = uuid.uuid4().hex[:12]
        # En-tête Cookie fourni par l'utilisateur pour capturer un espace
        # auquel il a accès. Jamais journalisé, jamais renvoyé par l'API.
        self.cookies = cookies or None
        # Type MIME réel de chaque fichier capturé. Une ressource issue d'une
        # URL sans extension (…/gtag/js?id=X) serait sinon servie en
        # application/octet-stream, et le navigateur refuserait de l'exécuter.
        self.types = {}
        # Rendu par un vrai navigateur : indispensable pour les sites qui
        # assemblent leur contenu en JavaScript.
        self.rendu_js = bool(rendu_js)
        self.url = url
        self.hote = urlsplit(url).netloc
        self.pages_max = pages_max
        self.dossier = DOSSIER_CLONES / self.id
        self.statut = "pending"
        self.pages = 0
        self.assets = 0
        self.octets = 0
        self.erreur = None
        self.entree = None
        self.debut = time.time()
        self.fin = None
        self.expire_a = None
        self.arret = threading.Event()
        self._evenements = []
        self._verrou = threading.Lock()

    def journal(self, texte, niveau="info"):
        with self._verrou:
            self._evenements.append({
                "i": len(self._evenements),
                "niveau": niveau,
                "texte": texte,
                "t": round(time.time() - self.debut, 1),
            })

    def etat(self, depuis=0):
        with self._verrou:
            evenements = self._evenements[depuis:]
            total = len(self._evenements)
        duree = (self.fin or time.time()) - self.debut
        return {
            "job_id": self.id,
            "statut": self.statut,
            "pages": self.pages,
            "assets": self.assets,
            "octets": self.octets,
            "duree": round(duree, 1),
            "erreur": self.erreur,
            "rendu_js": self.rendu_js,
            "retention": RETENTION,
            "expire_dans": (
                max(0, round(self.expire_a - time.time())) if self.expire_a else None
            ),
            "preview": f"/preview/{self.id}/{self.entree}" if self.entree else None,
            "evenements": evenements,
            "curseur": total,
        }


# ── Crawler ──────────────────────────────────────────────────────────────────
RE_BALISE = re.compile(r"<(?P<nom>[a-zA-Z][\w:-]*)(?P<attrs>[^>]*?)(?P<fin>/?)>")
RE_HREF = re.compile(r"(\bhref\s*=\s*)([\"'])(.*?)\2", re.I | re.S)
RE_SRC = re.compile(r"(\b(?:src|poster|data-src)\s*=\s*)([\"'])(.*?)\2", re.I | re.S)
RE_SRCSET = re.compile(r"(\bsrcset\s*=\s*)([\"'])(.*?)\2", re.I | re.S)
RE_STYLE_BLOC = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.I | re.S)
RE_CSS_URL = re.compile(r"url\(\s*([\"']?)([^\"')]+)\1\s*\)", re.I)
RE_CSS_IMPORT = re.compile(r"(@import\s+)([\"'])(.*?)\2", re.I)
RE_SCRIPT_BLOC = re.compile(r"(<script\b[^>]*>)(.*?)(</script\s*>)", re.I | re.S)
RE_REL = re.compile(r"""\brel\s*=\s*(["'])(.*?)\1""", re.I)
# Un <link> ne désigne une vraie sous-ressource que pour ces rel. Les autres
# (canonical, alternate, preconnect…) pointent vers des pages ou des domaines :
# les télécharger faisait réécrire index.html par la version brute de la page.
JETONS_REL_ASSET = {
    "stylesheet", "icon", "apple-touch-icon", "apple-touch-icon-precomposed",
    "mask-icon", "manifest", "preload", "modulepreload", "prefetch",
}
# Sous-Resource Integrity et crossorigin n'ont plus de sens sur une copie
# locale, et ils la cassent : l'aperçu tourne dans une iframe à origine opaque,
# donc chaque ressource est vue comme cross-origin et le contrôle d'intégrité
# échoue — la feuille de style est alors purement et simplement ignorée.
RE_ATTR_INTEGRITE = re.compile(
    r"""\s+(?:integrity|crossorigin|nonce)\s*=\s*(["']).*?\1""", re.I | re.S
)
RE_CROSSORIGIN_NU = re.compile(r"\s+crossorigin(?=[\s/]|$)", re.I)
RE_SANS_BALISES = re.compile(r"<[^>]+>")
RE_SCRIPT_ORPHELIN = re.compile(r"<script\b[^>]*/?>", re.I)


class Crawler:
    """Parcourt un site en largeur.

    Les pages sont traitées l'une après l'autre et écrites dès qu'elles sont
    réécrites ; leurs ressources partent en téléchargement parallèle en tâche
    de fond. Sans cette séparation, une page lourde n'apparaissait qu'après
    plusieurs minutes — le temps que chacune de ses ressources soit récupérée
    une par une.
    """

    def __init__(self, job, navigateur=None):
        self.job = job
        self.navigateur = navigateur
        # Session propre au job : les connexions sont réutilisées d'une
        # ressource à l'autre sans que deux captures partagent leur état.
        self.session = faire_session()
        self.file = deque()
        self.pages_connues = {}   # url normalisée -> chemin local
        self.chemins_pages = set()
        self.assets_connus = {}   # url normalisée -> chemin local
        self.verrou = threading.Lock()
        self.pool = None
        self.futures = set()
        self.codes_http = set()
        self.hote_verifie = False
        self.tls_signale = False
        self.verrou_pages = threading.Lock()
        self.actifs = 0
        self.echecs = 0

    # -- budget ---------------------------------------------------------------
    def budget_epuise(self):
        return (
            self.job.arret.is_set()
            or self.job.octets >= POIDS_MAX
            or len(self.assets_connus) >= ASSETS_MAX
        )

    def cookies_pour(self, url):
        """Ne transmet la session que vers le domaine capturé, jamais ailleurs."""
        if not self.job.cookies:
            return None
        return self.job.cookies if meme_hote(urlsplit(url).netloc, self.job.hote) else None

    def ecrire(self, relatif, donnees, texte=False):
        cible = chemin_sur(self.job.dossier, relatif)
        if cible is None:
            self.job.journal(f"Chemin refusé : {relatif}", "warn")
            return False
        octets = donnees.encode("utf-8") if texte else donnees
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(octets)
        with self.verrou:
            self.job.octets += len(octets)
        return True

    # -- résolution des liens -------------------------------------------------
    def ref_page(self, brut, url_page, page_relative):
        """Réécrit un lien <a href> vers la page capturée correspondante."""
        brut = brut.strip()
        if not brut or brut.lower().startswith(SCHEMAS_IGNORES) or brut.startswith("#"):
            return None
        cible, ancre = separer_ancre(urljoin(url_page, brut))
        p = urlsplit(cible)
        if p.scheme not in ("http", "https") or not meme_hote(p.netloc, self.job.hote):
            return None                      # lien externe : laissé intact
        cle = normaliser(cible)
        with self.verrou_pages:
            relatif = self.pages_connues.get(cle)
            if relatif is None:
                if len(self.pages_connues) >= self.job.pages_max:
                    return cible + ancre     # hors budget : on pointe vers le site d'origine
                relatif = chemin_local(cle, True, self.job.hote)
                self.pages_connues[cle] = relatif
                self.chemins_pages.add(relatif)
                self.file.append((cle, relatif))
        return lien_relatif(relatif, page_relative) + ancre

    def ref_asset(self, brut, url_base, fichier_relatif, profondeur=0):
        """Réserve le chemin local d'une ressource et programme son téléchargement.

        Ne télécharge rien : la page peut donc être écrite immédiatement.
        """
        brut = brut.strip()
        if not brut or brut.lower().startswith(SCHEMAS_IGNORES) or brut.startswith("#"):
            return None
        cible, _ = separer_ancre(urljoin(url_base, brut))
        p = urlsplit(cible)
        if p.scheme not in ("http", "https"):
            return None
        cle = normaliser(cible)
        with self.verrou:
            relatif = self.assets_connus.get(cle)
            nouveau = relatif is None
            if nouveau:
                if self.budget_epuise():
                    return cible             # hors budget : chargé depuis le site d'origine
                relatif = chemin_local(cle, False, self.job.hote)
                if relatif in self.chemins_pages:
                    return None          # ce chemin est déjà une page capturée
                self.assets_connus[cle] = relatif
        if nouveau:
            self.planifier(cle, relatif, profondeur)
        return lien_relatif(relatif, fichier_relatif)

    def planifier_observees(self, urls, page_relative):
        """Programme les ressources que le navigateur a réellement demandées.

        C'est ce qui rattrape les morceaux de code dont le nom est calculé à
        l'exécution : ils n'apparaissent dans aucun attribut du HTML.
        """
        for adresse in urls:
            self.ref_asset(adresse, adresse, page_relative)

    def planifier(self, url, relatif, profondeur):
        if self.job.arret.is_set() or self.pool is None:
            return
        future = self.pool.submit(self.capturer_asset, url, relatif, profondeur)
        with self.verrou:
            self.futures.add(future)

    def capturer_asset(self, url, relatif, profondeur):
        if self.job.arret.is_set():
            return
        try:
            brut, mime, entete, _, _ = telecharger(url, self.cookies_pour(url), self.session)
        except Exception as exc:
            self.job.journal(f"Ressource ignorée ({message_erreur(exc)}) : {url}", "warn")
            return
        if mime == "text/css" and profondeur < 3:
            # Une feuille de style peut référencer polices et images : on la
            # réécrit, ce qui programme à son tour ces ressources.
            contenu = self.reecrire_css(decoder(brut, entete), url, relatif, profondeur + 1)
            ecrit = self.ecrire(relatif, contenu, texte=True)
        else:
            ecrit = self.ecrire(relatif, brut)
        if ecrit:
            with self.verrou:
                self.job.assets += 1
                if mime:
                    self.job.types[relatif] = mime

    def attendre_assets(self):
        """Laisse les téléchargements en cours se terminer.

        La liste est relue à chaque tour : une feuille de style téléchargée
        pendant l'attente ajoute ses propres ressources.
        """
        while not self.job.arret.is_set():
            with self.verrou:
                restants = [f for f in self.futures if not f.done()]
            if not restants:
                return
            wait(restants, timeout=2)

    # -- réécriture -----------------------------------------------------------
    def reecrire_css(self, css, url_base, fichier_relatif, profondeur):
        def remplacer_url(m):
            nouveau = self.ref_asset(m.group(2), url_base, fichier_relatif, profondeur)
            return f"url({m.group(1)}{nouveau or m.group(2)}{m.group(1)})"

        def remplacer_import(m):
            nouveau = self.ref_asset(m.group(3), url_base, fichier_relatif, profondeur)
            return f"{m.group(1)}{m.group(2)}{nouveau or m.group(3)}{m.group(2)}"

        css = RE_CSS_IMPORT.sub(remplacer_import, css)
        return RE_CSS_URL.sub(remplacer_url, css)

    def reecrire_html(self, html, url_page, page_relative):
        def sub_attr(regex, attrs, resolveur):
            def remplacer(m):
                nouveau = resolveur(m.group(3))
                valeur = m.group(3) if nouveau is None else nouveau
                return f"{m.group(1)}{m.group(2)}{valeur}{m.group(2)}"
            return regex.sub(remplacer, attrs)

        def sub_srcset(attrs):
            def remplacer(m):
                parts = []
                for candidat in m.group(3).split(","):
                    morceaux = candidat.strip().split()
                    if not morceaux:
                        continue
                    nouveau = self.ref_asset(morceaux[0], url_page, page_relative)
                    morceaux[0] = nouveau or morceaux[0]
                    parts.append(" ".join(morceaux))
                return f"{m.group(1)}{m.group(2)}{', '.join(parts)}{m.group(2)}"
            return RE_SRCSET.sub(remplacer, attrs)

        def traiter_balise(m):
            nom = m.group("nom").lower()
            attrs = m.group("attrs")
            if nom in ("a", "area"):
                attrs = sub_attr(RE_HREF, attrs, lambda v: self.ref_page(v, url_page, page_relative))
            elif nom in ("link", "use"):
                rel = RE_REL.search(attrs)
                jetons = set(rel.group(2).lower().split()) if rel else set()
                if rel is None or jetons & JETONS_REL_ASSET:
                    attrs = sub_attr(RE_HREF, attrs, lambda v: self.ref_asset(v, url_page, page_relative))
                    attrs = RE_CROSSORIGIN_NU.sub("", RE_ATTR_INTEGRITE.sub("", attrs))
            elif nom == "base":
                return ""                    # un <base> d'origine casserait les liens locaux
            elif nom in BALISES_ASSET:
                attrs = sub_attr(RE_SRC, attrs, lambda v: self.ref_asset(v, url_page, page_relative))
                attrs = sub_srcset(attrs)
                attrs = RE_CROSSORIGIN_NU.sub("", RE_ATTR_INTEGRITE.sub("", attrs))
            return f"<{m.group('nom')}{attrs}{m.group('fin')}>"

        # Le corps des <script> est mis de côté le temps de la réécriture : il
        # contient souvent du HTML échappé (href=\\"...\\") que les expressions
        # ci-dessus prendraient pour de vrais attributs, produisant des URL
        # bancales du type "//cdn.jsdelivr.net\\/npm\\/…".
        corps_scripts = []

        def mettre_de_cote(m):
            corps_scripts.append(m.group(2))
            return f"{m.group(1)}\x00{len(corps_scripts) - 1}\x00{m.group(3)}"

        html = RE_SCRIPT_BLOC.sub(mettre_de_cote, html)
        html = RE_BALISE.sub(traiter_balise, html)
        html = re.sub(r"\x00(\d+)\x00", lambda m: corps_scripts[int(m.group(1))], html)
        return RE_STYLE_BLOC.sub(
            lambda m: m.group(1) + self.reecrire_css(m.group(2), url_page, page_relative, 1) + m.group(3),
            html,
        )

    # -- boucle principale ----------------------------------------------------
    def traiter_page(self, url, relatif):
        """Récupère, réécrit et écrit une page. Appelée par plusieurs workers."""
        job = self.job
        observees = []
        try:
            if self.navigateur:
                html_rendu, observees, url_finale = self.navigateur.rendre(
                    url, self.cookies_pour(url)
                )
                brut, mime, entete, tls_souple = b"", "text/html", "text/html", False
            else:
                brut, mime, entete, url_finale, tls_souple = telecharger(
                    url, self.cookies_pour(url)
                )
            if tls_souple and not self.tls_signale:
                self.tls_signale = True
                job.journal(
                    "Certificat TLS non vérifiable — capture poursuivie sans "
                    "contrôle du certificat.", "warn",
                )
        except HTTPError as exc:
            with self.verrou_pages:
                self.echecs += 1
                self.codes_http.add(exc.code)
            job.journal(f"Échec : {url} (HTTP {exc.code})", "error")
            return
        except Exception as exc:
            with self.verrou_pages:
                self.echecs += 1
            job.journal(f"Échec : {url} ({message_erreur(exc)})", "error")
            return

        if mime not in TYPES_PAGE:
            with self.verrou_pages:
                entree = not self.hote_verifie
                self.hote_verifie = True
            if entree:
                # L'adresse saisie pointe directement sur un fichier (PDF,
                # image, archive). On le conserve plutôt que de déclarer la
                # capture vide.
                nom = chemin_local(url, False, job.hote).rsplit("/", 1)[-1]
                if self.ecrire(nom, brut):
                    job.entree = nom
                    if mime:
                        job.types[nom] = mime
                    with self.verrou_pages:
                        job.pages += 1
                    job.journal(f"Fichier capturé ({mime or 'type inconnu'}) — {nom}", "ok")
                return
            job.journal(f"Ignoré (type {mime or 'inconnu'}) : {url}", "warn")
            return

        # Si l'URL de départ redirige vers un autre domaine
        # (service-public.fr -> service-public.gouv.fr), c'est ce domaine-là
        # qu'il faut suivre : sinon tous les liens internes passent pour
        # externes et une seule page est capturée. Au démarrage un seul worker
        # a du travail, donc l'ajustement précède bien les autres pages.
        with self.verrou_pages:
            premiere = not self.hote_verifie
            self.hote_verifie = True
        if premiere:
            hote_final = urlsplit(url_finale).netloc
            if hote_final and not meme_hote(hote_final, job.hote):
                job.journal(
                    f"Redirection vers {hote_final} — domaine suivi mis à jour.", "info"
                )
                job.hote = hote_final

        if self.navigateur:
            # Le DOM rendu est sauvegardé sans ses scripts. Les laisser serait
            # contre-productif : une application hydratée détecte que le DOM
            # enregistré ne correspond pas à ce qu'elle attend, efface la page
            # et la reconstruit — sans ses données, elle finit vide. Sans eux,
            # la capture est une photographie fidèle, mais figée.
            source = RE_SCRIPT_ORPHELIN.sub("", RE_SCRIPT_BLOC.sub("", html_rendu))
            if premiere:
                job.journal(
                    "Rendu navigateur : scripts neutralisés, la capture est "
                    "fidèle mais non interactive.", "info",
                )
        else:
            source = decoder(brut, entete)
        if observees:
            # Les ressources vues par le navigateur sont programmées avant la
            # réécriture : celles qui figurent aussi dans le HTML réutilisent
            # simplement le chemin déjà réservé.
            self.planifier_observees(observees, relatif)
        html = self.reecrire_html(source, url_finale, relatif)
        if premiere and not self.navigateur:
            self.avertir_si_coquille(html)
        if self.ecrire(relatif, html, texte=True):
            with self.verrou_pages:
                job.pages += 1
                numero = job.pages
            job.journal(f"Page {numero} — {relatif}", "ok")

    def avertir_si_coquille(self, html):
        """Prévient quand la page n'a quasiment pas de texte hors JavaScript.

        Une application qui construit son contenu côté navigateur ne livre
        qu'une coquille : la capture réussit techniquement mais donne une page
        presque vide. Mieux vaut le dire que de laisser croire à un succès.
        """
        sans_js = RE_SCRIPT_BLOC.sub(" ", html)
        sans_js = RE_STYLE_BLOC.sub(" ", sans_js)
        texte = re.sub(r"\s+", " ", RE_SANS_BALISES.sub(" ", sans_js)).strip()
        scripts = len(RE_SCRIPT_BLOC.findall(html)) + html.lower().count("<script src")
        if len(texte) < 500 and scripts >= 3:
            self.job.journal(
                "Ce site construit son contenu en JavaScript : la capture "
                "risque d'être incomplète.", "warn",
            )

    def boucle_pages(self):
        """Worker : dépile des pages jusqu'à épuisement de la file."""
        job = self.job
        while not job.arret.is_set():
            with self.verrou_pages:
                if job.pages >= job.pages_max or job.octets >= POIDS_MAX:
                    return
                if self.file:
                    url, relatif = self.file.popleft()
                    self.actifs += 1
                elif self.actifs == 0:
                    return        # file vide et plus aucun worker n'alimente
                else:
                    url = None    # un autre worker peut encore ajouter des liens
            if url is None:
                time.sleep(0.1)
                continue
            try:
                self.traiter_page(url, relatif)
            finally:
                with self.verrou_pages:
                    self.actifs -= 1

    def executer(self):
        job = self.job
        depart = normaliser(job.url)
        entree = chemin_local(depart, True, job.hote)
        self.pages_connues[depart] = entree
        self.chemins_pages.add(entree)
        self.file.append((depart, entree))
        job.entree = entree
        job.journal(f"Cible : {job.hote}", "info")
        job.journal(f"Budget : {job.pages_max} page(s) maximum", "info")

        self.pool = ThreadPoolExecutor(
            max_workers=ASSETS_PARALLELES, thread_name_prefix="shyclone-asset"
        )
        ouvriers = PAGES_PARALLELES_RENDU if self.navigateur else PAGES_PARALLELES
        pool_pages = ThreadPoolExecutor(
            max_workers=ouvriers, thread_name_prefix="shyclone-page"
        )
        try:
            wait([pool_pages.submit(self.boucle_pages) for _ in range(ouvriers)])
            if job.pages and not job.arret.is_set():
                job.journal("Pages capturées — récupération des ressources…", "info")
            self.attendre_assets()
        finally:
            pool_pages.shutdown(wait=False, cancel_futures=True)
            self.pool.shutdown(wait=False, cancel_futures=True)

        if job.pages == 0 and not job.arret.is_set():
            bloquants = sorted(c for c in self.codes_http if c in CODES_BLOCAGE)
            if bloquants:
                raise RuntimeError(
                    f"Le site refuse les requêtes automatisées (HTTP {bloquants[0]}). "
                    "Il est protégé par un service anti-robot, ShyClone ne peut pas le capturer."
                )
            raise RuntimeError(
                f"Aucune page n'a pu être capturée ({self.echecs} échec(s)). "
                "Vérifiez l'adresse, ou le site est injoignable."
            )


def purger_anciens_jobs():
    """Garde les JOBS_CONSERVES captures les plus récentes sur disque."""
    if not DOSSIER_CLONES.is_dir():
        return
    dossiers = sorted(
        (d for d in DOSSIER_CLONES.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    for vieux in dossiers[JOBS_CONSERVES:]:
        shutil.rmtree(vieux, ignore_errors=True)
        with VERROU_JOBS:
            JOBS.pop(vieux.name, None)


def concierge():
    """Supprime les captures arrivées à expiration.

    Le disque d'un hébergement gratuit est petit : sans ce ménage, quelques
    captures de sites lourds le rempliraient. L'échéance est annoncée à
    l'utilisateur dans l'interface.
    """
    while True:
        time.sleep(20)
        maintenant = time.time()
        with VERROU_JOBS:
            expires = [j for j in JOBS.values() if j.expire_a and j.expire_a <= maintenant]
        for job in expires:
            shutil.rmtree(job.dossier, ignore_errors=True)
            with VERROU_JOBS:
                JOBS.pop(job.id, None)
            print(f"[ShyClone] capture {job.id} expirée — fichiers supprimés")


threading.Thread(target=concierge, daemon=True, name="shyclone-concierge").start()


def executer_job(job):
    job.statut = "running"
    try:
        shutil.rmtree(job.dossier, ignore_errors=True)
        job.dossier.mkdir(parents=True, exist_ok=True)
        navigateur = None
        try:
            if job.rendu_js:
                job.journal("Démarrage du navigateur de rendu…", "info")
                navigateur = nav.Navigateur().demarrer()
            Crawler(job, navigateur).executer()
        finally:
            if navigateur:
                navigateur.arreter()
        if job.arret.is_set():
            job.statut = "aborted"
            job.journal("Interrompu à la demande de l'utilisateur.", "warn")
        else:
            job.statut = "done"
            job.journal(
                f"Terminé — {job.pages} page(s), {job.assets} ressource(s).", "ok"
            )
    except Exception as exc:
        job.statut = "error"
        job.erreur = str(exc)
        job.journal(str(exc), "error")
    finally:
        job.fin = time.time()
        job.expire_a = job.fin + RETENTION


# ── Routes ───────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return jsonify({"statut": "ok", "version": "1.0", "rendu_js": nav.disponible()})


@app.post("/api/check")
def check():
    if quota_depasse(f"check:{adresse_client()}", QUOTA_CHECK):
        return jsonify({"ok": False, "raison": "Trop de vérifications. Réessayez plus tard."}), 429
    url = ((request.get_json(silent=True) or {}).get("url") or "").strip()
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        return jsonify({"ok": False, "raison": "URL invalide."}), 400
    url = corriger_hote(url)
    try:
        _, _, _, finale, _ = telecharger(url)
        return jsonify({"ok": True, "url": finale})
    except HTTPError as exc:
        if exc.code in (401, 403, 405, 429):
            # Le serveur répond : le site existe, le clonage peut être tenté.
            return jsonify({"ok": True, "url": url, "avertissement": f"HTTP {exc.code}"})
        return jsonify({"ok": False, "raison": f"Le site a répondu HTTP {exc.code}."})
    except Exception as exc:
        return jsonify({"ok": False, "raison": f"Site injoignable ({message_erreur(exc)})."})


@app.post("/api/clone")
def clone():
    if quota_depasse(f"clone:{adresse_client()}", QUOTA_CLONE):
        return jsonify({
            "statut": "error",
            "message": f"Vous avez atteint la limite de {QUOTA_CLONE} captures par heure.",
        }), 429
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        return jsonify({"statut": "error", "message": "URL invalide."}), 400
    url = corriger_hote(url)

    try:
        pages_max = int(data.get("pages_max") or PAGES_DEFAUT)
    except (TypeError, ValueError):
        pages_max = PAGES_DEFAUT
    pages_max = max(1, min(pages_max, PAGES_MAX))
    cookies = (data.get("cookies") or "").strip().replace("\n", " ")[:4096] or None
    rendu_js = bool(data.get("rendu_js")) and nav.disponible()

    purger_anciens_jobs()
    job = Job(url, pages_max, cookies, rendu_js)
    with VERROU_JOBS:
        JOBS[job.id] = job
    threading.Thread(target=executer_job, args=(job,), daemon=True).start()
    print(f"[ShyClone] job {job.id} → {job.hote} ({pages_max} pages max)")
    return jsonify({"statut": "started", "job_id": job.id}), 202


@app.get("/api/jobs/<job_id>")
def etat_job(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({
            "statut": "expired",
            "message": "Capture expirée ou inconnue — relancez-la.",
        }), 404
    try:
        depuis = max(0, int(request.args.get("from", 0)))
    except ValueError:
        depuis = 0
    return jsonify(job.etat(depuis))


@app.post("/api/jobs/<job_id>/abort")
def abandonner(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"statut": "error", "message": "Job inconnu."}), 404
    job.arret.set()
    return jsonify({"statut": "aborting"})


@app.get("/api/jobs/<job_id>/zip")
def archive(job_id):
    job = JOBS.get(job_id)
    if not job or not job.dossier.is_dir():
        return jsonify({
            "statut": "expired",
            "message": f"Capture expirée — elle est supprimée {duree_retention()} "
                       "après la fin du clonage.",
        }), 404
    # L'archive passe par un fichier temporaire, pas par la mémoire : sur une
    # instance à 512 Mo, zipper une capture de plusieurs centaines de Mo ferait
    # tomber le processus.
    fichier = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    try:
        with zipfile.ZipFile(fichier, "w", zipfile.ZIP_DEFLATED) as zf:
            for chemin in job.dossier.rglob("*"):
                if chemin.is_file():
                    zf.write(chemin, chemin.relative_to(job.dossier))
        fichier.close()
    except Exception:
        fichier.close()
        os.unlink(fichier.name)
        raise

    nom = re.sub(r"[^A-Za-z0-9.-]", "-", job.hote) or "site"
    reponse = send_file(
        fichier.name, mimetype="application/zip",
        as_attachment=True, download_name=f"{nom}-{job.id}.zip",
    )
    reponse.call_on_close(lambda: os.path.exists(fichier.name) and os.unlink(fichier.name))
    return reponse


@app.get("/preview/<job_id>/")
@app.get("/preview/<job_id>/<path:relatif>")
def preview(job_id, relatif=None):
    job = JOBS.get(job_id)
    if not job or not job.dossier.is_dir():
        return (
            f"Capture expirée — les fichiers sont supprimés {duree_retention()} "
            "après la fin du clonage.",
            404,
        )
    relatif = relatif or job.entree or "index.html"
    if chemin_sur(job.dossier, relatif) is None:
        return "Chemin refusé", 403
    try:
        return send_from_directory(job.dossier, relatif, mimetype=job.types.get(relatif))
    except Exception:
        return "Fichier absent de la capture", 404


@app.get("/robots.txt")
def robots():
    """Autorise l'indexation de l'outil, jamais celle des sites capturés.

    Laisser un moteur indexer /preview reviendrait à publier sous ce domaine
    des copies de sites tiers — contenu dupliqué et demandes de retrait pour
    l'éditeur du service.
    """
    racine = request.url_root.rstrip("/")
    return Response(
        # Aucune règle Allow : tout ce qui n'est pas interdit l'est
        # implicitement, et un Allow mal placé sème la confusion.
        "User-agent: *\n"
        "Disallow: /preview/\n"
        "Disallow: /api/\n\n"
        f"Sitemap: {racine}/sitemap.xml\n",
        mimetype="text/plain",
    )


@app.get("/sitemap.xml")
def sitemap():
    racine = request.url_root.rstrip("/")
    entrees = "".join(
        f"<url><loc>{racine}{chemin}</loc>"
        f"<changefreq>{frequence}</changefreq>"
        f"<priority>{priorite}</priority></url>"
        for chemin, frequence, priorite in (
            ("/", "weekly", "1.0"),
            ("/cgu.html", "yearly", "0.3"),
            ("/confidentialite.html", "yearly", "0.3"),
            ("/mentions-legales.html", "yearly", "0.3"),
        )
    )
    return Response(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entrees}</urlset>",
        mimetype="application/xml",
    )


_page_accueil = {}


def page_accueil():
    """index.html, avec le code de vérification Search Console si fourni."""
    fichier = DOSSIER_UI / "index.html"
    signature = fichier.stat().st_mtime_ns
    if _page_accueil.get("signature") != signature:
        html = fichier.read_text(encoding="utf-8")
        if VERIF_GOOGLE:
            html = html.replace(
                "</head>",
                f'  <meta name="google-site-verification" content="{VERIF_GOOGLE}" />\n  </head>',
            )
        _page_accueil.update(signature=signature, html=html)
    return Response(_page_accueil["html"], mimetype="text/html")


@app.get("/")
@app.get("/<path:chemin>")
def interface(chemin=""):
    """Sert l'interface compilée (dist/) depuis le même service que l'API."""
    if chemin.startswith(("api/", "preview/")):
        return jsonify({"statut": "error", "message": "Ressource introuvable."}), 404

    # Le JS d'un site capturé reconstruit souvent des URL absolues (/_next/…,
    # /assets/…) qui sortent du dossier de la capture. Quand la requête vient
    # d'une page d'aperçu, on la redirige vers le dossier du job. Et si le
    # fichier manque, on renvoie une vraie 404 : lui servir l'interface ferait
    # échouer le navigateur sur un type MIME inattendu.
    venant = re.match(r"^/preview/([0-9a-f]{12})/", urlsplit(request.headers.get("Referer", "")).path)
    if venant:
        job = JOBS.get(venant.group(1))
        if job and job.dossier.is_dir():
            cible = chemin_sur(job.dossier, chemin)
            if cible is not None and cible.is_file():
                return send_from_directory(job.dossier, chemin, mimetype=job.types.get(chemin))
        return jsonify({"statut": "error", "message": "Ressource absente de la capture."}), 404
    if not DOSSIER_UI.is_dir():
        return jsonify({"statut": "error", "message": "Interface indisponible."}), 503
    if chemin:
        cible = chemin_sur(DOSSIER_UI, chemin)
        if cible is not None and cible.is_file():
            return send_from_directory(DOSSIER_UI, chemin)
        # Liens propres : /mentions-legales sert mentions-legales.html.
        if "." not in chemin.rsplit("/", 1)[-1]:
            page = chemin_sur(DOSSIER_UI, chemin + ".html")
            if page is not None and page.is_file():
                return send_from_directory(DOSSIER_UI, chemin + ".html")
    return page_accueil()


if __name__ == "__main__":
    # Le serveur de développement annonce sinon « Werkzeug/x Python/y », et
    # ajoute son propre en-tête Server en plus de celui de l'application.
    from werkzeug.serving import WSGIRequestHandler

    class HandlerDiscret(WSGIRequestHandler):
        def send_header(self, keyword, value):
            if keyword.lower() == "server":
                return
            super().send_header(keyword, value)

    DOSSIER_CLONES.mkdir(parents=True, exist_ok=True)
    print(f"[ShyClone] moteur à l'écoute sur http://{HOTE}:{PORT}")
    app.run(host=HOTE, port=PORT, debug=False, use_reloader=False,
            threaded=True, request_handler=HandlerDiscret)
