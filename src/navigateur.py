"""Rendu des pages dans un vrai navigateur, en option.

Un site qui assemble son contenu en JavaScript ne livre qu'une coquille au
téléchargement direct. Ce module pilote un Chrome sans interface pour obtenir
deux choses :

1. le DOM après exécution des scripts ;
2. la liste des ressources que la page a réellement demandées — les morceaux de
   code dont le nom est calculé à l'exécution n'apparaissent nulle part dans le
   HTML, aucune analyse statique ne peut les deviner.

Entièrement facultatif : sans navigateur installé, le moteur retombe sur la
capture statique, qui suffit pour tout site rendu côté serveur.
"""

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

try:
    import websocket
except ImportError:                     # dépendance facultative
    websocket = None

CANDIDATS = [
    os.environ.get("SHYCLONE_NAVIGATEUR"),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
]

DRAPEAUX = [
    "--headless=new", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
    "--no-first-run", "--no-default-browser-check", "--disable-extensions",
    "--mute-audio", "--hide-scrollbars", "--disable-background-networking",
    "--disable-features=Translate,MediaRouter", "--window-size=1440,900",
]


def trouver_binaire():
    for candidat in CANDIDATS:
        if not candidat:
            continue
        if os.path.isabs(candidat):
            if os.path.isfile(candidat) and os.access(candidat, os.X_OK):
                return candidat
            continue
        trouve = shutil.which(candidat)
        if trouve:
            return trouve
    return None


def disponible():
    """Le rendu navigateur est-il utilisable sur cette machine ?"""
    return websocket is not None and trouver_binaire() is not None


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Session:
    """Échange minimal avec le point de contrôle du navigateur."""

    def __init__(self, ws):
        self.ws = ws
        self.numero = 0
        self.evenements = []

    def envoyer(self, methode, **params):
        self.numero += 1
        self.ws.send(json.dumps({"id": self.numero, "method": methode, "params": params}))
        return self.numero

    def _lire(self, delai):
        self.ws.settimeout(max(0.05, delai))
        try:
            return json.loads(self.ws.recv())
        except Exception:
            return None

    def attendre(self, ident, delai=10):
        fin = time.time() + delai
        while time.time() < fin:
            message = self._lire(fin - time.time())
            if message is None:
                break
            if message.get("id") == ident:
                return message.get("result") or {}
            if "method" in message:
                self.evenements.append(message)
        return {}

    def pomper(self, duree):
        fin = time.time() + duree
        while time.time() < fin:
            message = self._lire(fin - time.time())
            if message is None:
                break
            if "method" in message:
                self.evenements.append(message)

    def appeler(self, methode, delai=10, **params):
        return self.attendre(self.envoyer(methode, **params), delai)


class Navigateur:
    """Pilote un navigateur partagé, un onglet par page rendue."""

    def __init__(self, binaire=None, onglets=2):
        self.binaire = binaire or trouver_binaire()
        self.processus = None
        self.port = None
        self.profil = None
        self.jetons = threading.Semaphore(max(1, onglets))

    # -- cycle de vie ---------------------------------------------------------
    def demarrer(self):
        if not self.binaire or websocket is None:
            raise RuntimeError("aucun navigateur utilisable")
        self.profil = tempfile.mkdtemp(prefix="shyclone-nav-")
        self.port = _port_libre()
        self.processus = subprocess.Popen(
            [self.binaire, *DRAPEAUX,
             f"--remote-debugging-port={self.port}",
             f"--user-data-dir={self.profil}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(80):
            if self.processus.poll() is not None:
                break
            try:
                urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=1).read()
                return self
            except Exception:
                time.sleep(0.25)
        self.arreter()
        raise RuntimeError("le navigateur n'a pas démarré")

    def arreter(self):
        if self.processus and self.processus.poll() is None:
            self.processus.terminate()
            try:
                self.processus.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.processus.kill()
        self.processus = None
        if self.profil:
            shutil.rmtree(self.profil, ignore_errors=True)
            self.profil = None

    def __enter__(self):
        return self.demarrer()

    def __exit__(self, *_):
        self.arreter()

    # -- onglets --------------------------------------------------------------
    def _ouvrir_onglet(self):
        # Le point de contrôle n'accepte que PUT sur /json/new.
        requete = Request(
            f"http://127.0.0.1:{self.port}/json/new?about:blank", method="PUT"
        )
        return json.loads(urlopen(requete, timeout=10).read())

    def _fermer_onglet(self, identifiant):
        try:
            urlopen(f"http://127.0.0.1:{self.port}/json/close/{identifiant}", timeout=5).read()
        except Exception:
            pass

    # -- rendu ----------------------------------------------------------------
    def rendre(self, url, cookies=None, repos=1.5, plafond=22):
        """Charge l'URL et renvoie (html, ressources_demandées, url_finale).

        L'attente s'arrête dès que le réseau se calme, sans dépasser `plafond`.
        """
        with self.jetons:
            onglet = self._ouvrir_onglet()
            ws = websocket.create_connection(
                onglet["webSocketDebuggerUrl"], timeout=30, suppress_origin=True
            )
            session = _Session(ws)
            try:
                session.appeler("Network.enable")
                session.appeler("Page.enable")
                if cookies:
                    session.appeler("Network.setCookies", cookies=[
                        {"name": nom, "value": valeur, "url": url}
                        for nom, valeur in _decouper_cookies(cookies)
                    ])
                session.appeler("Page.navigate", delai=plafond, url=url)

                debut = dernier = time.time()
                while time.time() - debut < plafond:
                    avant = len(session.evenements)
                    session.pomper(0.3)
                    if any(e.get("method") == "Network.requestWillBeSent"
                           for e in session.evenements[avant:]):
                        dernier = time.time()
                    if time.time() - debut > 2 and time.time() - dernier > repos:
                        break

                html = session.appeler(
                    "Runtime.evaluate", expression="document.documentElement.outerHTML",
                    returnByValue=True,
                ).get("result", {}).get("value") or ""
                finale = session.appeler(
                    "Runtime.evaluate", expression="location.href", returnByValue=True,
                ).get("result", {}).get("value") or url

                ressources = []
                vues = set()
                for evenement in session.evenements:
                    if evenement.get("method") != "Network.requestWillBeSent":
                        continue
                    demande = evenement["params"]["request"]["url"]
                    if (demande not in vues and demande != finale
                            and urlsplit(demande).scheme in ("http", "https")):
                        vues.add(demande)
                        ressources.append(demande)
                return html, ressources, finale
            finally:
                try:
                    ws.close()
                except Exception:
                    pass
                self._fermer_onglet(onglet["id"])


def _decouper_cookies(entete):
    for morceau in entete.split(";"):
        nom, _, valeur = morceau.strip().partition("=")
        if nom and valeur:
            yield nom, valeur
