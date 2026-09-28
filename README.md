# ShyClone

Outil local de capture de sites web. Un moteur Python télécharge les pages et
leurs ressources, réécrit les liens pour qu'ils pointent vers les fichiers
récupérés, et une interface React permet de suivre l'opération, de prévisualiser
le résultat et de l'exporter en `.zip`.

La capture est **hors ligne** : les pages affichées dans l'aperçu sont servies
depuis votre disque, pas depuis le site d'origine.

## Démarrage

```bash
pip3 install -r requirements.txt
npm install
./start.sh
```

`start.sh` lance le moteur puis l'interface, attend que le moteur réponde avant
d'ouvrir Vite, et arrête les deux processus sur `Ctrl+C`.

L'interface est sur http://localhost:5173, le moteur sur le port 5000.
Pour les lancer séparément : `npm run server` et `npm run client`.

En production, un seul processus suffit : `npm run build` compile l'interface
dans `dist/`, que le moteur sert lui-même. Tout répond alors sur le port 5000,
sans second service ni configuration d'origine.

Variables d'environnement reconnues :

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `PORT` / `SHYCLONE_PORT` | port du moteur Flask | `5000` |
| `SHYCLONE_HOST` | interface d'écoute du moteur | `127.0.0.1` |
| `SHYCLONE_MDP` | mot de passe d'accès à l'application (vide = ouverte) | vide |
| `SHYCLONE_UTILISATEUR` | identifiant associé | `shy` |
| `SHYCLONE_TOKEN` | jeton exigé sur `/api` (vide = désactivé) | vide |
| `VITE_API_TOKEN` | jeton envoyé par l'interface | vide |
| `SHYCLONE_BLOQUER_PRIVE` | refuse les adresses réseau internes | actif si exposé |
| `SHYCLONE_FORCE_HTTPS` | redirection HTTPS + en-tête HSTS | actif si exposé |
| `SHYCLONE_QUOTA_CLONE` | captures autorisées par IP et par heure | `12` |
| `SHYCLONE_QUOTA_CHECK` | vérifications autorisées par IP et par heure | `60` |
| `SHYCLONE_DELAI` | délai réseau par requête, en secondes | `20` |
| `SHYCLONE_NAVIGATEUR` | chemin du navigateur de rendu | détecté |
| `SHYCLONE_PAGES_PAR` | pages récupérées simultanément | `8` |
| `SHYCLONE_ASSETS_PAR` | ressources récupérées simultanément | `12` |
| `SHYCLONE_PAGES_PAR_RENDU` | pages simultanées en rendu navigateur | `2` |
| `SHYCLONE_RETENTION` | secondes avant suppression d'une capture | `780` (13 min) |
| `VITE_PREVIEW_BASE` | origine servant l'aperçu, pour l'isoler | même origine |
| `SHYCLONE_UI_PORT` | port de Vite | `5173` |
| `SHYCLONE_ENGINE` | cible du proxy Vite | `http://127.0.0.1:5000` |
| `VITE_API_BASE` | préfixe d'API côté client, si l'interface est servie ailleurs | vide (relatif) |

## Déploiement

Tout tient dans **un seul service** : le `Dockerfile` compile l'interface puis
la sert depuis le même processus que l'API. Une image, un port, une URL.

```bash
docker build -t shyclone .
docker run -p 8000:8000 shyclone
```

Pour y inclure le navigateur de rendu :

```bash
docker build --build-arg AVEC_NAVIGATEUR=1 -t shyclone .
```

Mesuré sur l'image construite : **1,22 Go contre 202 Mo** sans le navigateur,
et **302 Mo de mémoire au pic** d'une capture (55 Mo au repos). La mémoire
tient sur une instance gratuite de 512 Mo ; c'est la taille de l'image qui
devient l'obstacle. Réservez cette variante à un hébergement qui en a les
moyens, et gardez l'image ordinaire ailleurs — sans navigateur, l'option
n'apparaît simplement pas dans l'interface.

### Gratuit, sur Render

`render.yaml` décrit ce service unique, en palier gratuit, sans carte bancaire.
Vous pouvez aussi le créer à la main : Web Service · Docker · Free, `Dockerfile`
à la racine, health check `/api/health`. Aucune variable à renseigner côté
interface — elle est servie par le moteur, donc sur la même origine.

Le service est **ouvert à tous** par défaut : n'importe quel visiteur peut
lancer une capture, dans la limite de douze par heure et par adresse IP.

Pour le réserver à vous seul, ajoutez `SHYCLONE_MDP` dans l'onglet
*Environment* avec le mot de passe de votre choix. L'interface, l'API et
l'aperçu le réclament alors, l'identifiant étant `shy`. Seule `/api/health`
reste ouverte, faute de quoi Render déclare le service en panne et le
redémarre en boucle.

Ouvrir le service au public a trois conséquences à peser :

- **Votre serveur télécharge ce qu'on lui demande.** Les sites visés voient
  l'adresse IP de votre hébergement, pas celle du visiteur. C'est elle qui se
  fait bannir en cas d'abus.
- **Les pages légales deviennent obligatoires**, et leurs emplacements « à
  compléter » doivent l'être avant la mise en ligne.
- **La bande passante et la mémoire sont partagées** par tous les visiteurs, sur
  une instance gratuite de 512 Mo.

L'environnement Render a été rejoué localement — port injecté par `PORT`, mot
de passe généré, en-tête `X-Forwarded-Proto` du proxy — avec ces résultats :

| Situation | Attendu | Obtenu |
| --- | --- | --- |
| sonde `/api/health`, sans identifiants | 200 | 200 |
| visiteur sans identifiants | 401 | 401 |
| visiteur avec identifiants | 200 | 200 |
| requête en clair | 308 vers HTTPS | 308 |
| capture de 15 pages derrière le mot de passe | réussie | 15 pages, 170 ressources, 6,3 s |

Mémoire du conteneur pendant la capture : 82 Mo, loin des 512 Mo du palier
gratuit. Ces essais valident l'image et la configuration, pas le compte Render
lui-même : le blueprint n'a jamais été soumis à leur API.

Les limites du palier gratuit, à connaître avant de s'y engager :

- le service s'endort après 15 minutes sans trafic ; la première capture qui
  suit attend environ une minute le temps du réveil ;
- le disque est éphémère, les captures disparaissent à chaque redéploiement —
  ce qui rejoint de toute façon la purge automatique décrite plus bas ;
- 512 Mo de RAM : évitez les captures de plusieurs centaines de pages.

Autres hébergeurs gratuits du même genre : Hugging Face Spaces (Docker),
Fly.io, ou une instance Always Free chez Oracle Cloud pour une machine qui ne
dort pas.

### Pourquoi pas Vercel

Vercel exécute des fonctions serverless : chaque requête est une invocation
isolée, sans disque partagé, sans état en mémoire conservé d'un appel à
l'autre, et les threads lancés en arrière-plan sont gelés dès que la réponse
est renvoyée. Or une capture dure souvent plusieurs minutes, écrit des fichiers
qu'une requête ultérieure doit relire pour l'aperçu et l'archive, et garde
l'état du job en mémoire. Aucune commande de démarrage ne contourne ça : c'est
le modèle d'exécution qui est incompatible.

### Sans rien déployer

ShyClone est aussi un outil de poste de travail : `./start.sh` lance les deux
parties en local, sans compte ni hébergeur, et sans exposer un robot
d'aspiration sur Internet.

## Sécurité

Ce qui est en place :

- **Pas de signature technique.** L'en-tête `Server` vaut `ShyClone` (y compris
  derrière Gunicorn, voir `gunicorn.conf.py`), les pages
  d'erreur sont du JSON neutre, aucune trace d'exécution ni chemin de fichier
  n'est renvoyé au client, et l'interface ne mentionne aucun outil.
- **Pas de rebond vers le réseau interne.** Le moteur refuse toute URL qui
  résout vers une adresse privée, de bouclage, de lien-local ou réservée —
  y compris après redirection. Sans ce filtre, un moteur exposé sert à scanner
  le réseau de l'hébergeur et à lire ses métadonnées cloud
  (`169.254.169.254`). Actif dès que le moteur écoute ailleurs que sur
  `127.0.0.1` ; `SHYCLONE_BLOQUER_PRIVE=0` le désactive pour cloner un site
  local en développement.
- **Écriture confinée.** Les chemins issus des URL sont assainis et vérifiés :
  rien ne s'écrit ni ne se lit hors du dossier du job.
- **Accès à l'application.** `SHYCLONE_MDP` ferme l'interface, l'API et
  l'aperçu derrière une authentification HTTP. Indispensable sur un moteur
  public : sinon n'importe qui fait télécharger n'importe quoi par votre
  serveur, et c'est votre adresse IP qui se fait bannir. Seule `/api/health`
  reste ouverte, pour la sonde de l'hébergeur. `SHYCLONE_TOKEN` existe en plus
  pour un accès programmatique à `/api` sans navigateur.
- **L'aperçu ne peut pas piloter l'API.** Une requête vers `/api` dont le
  référent est une page capturée est refusée.
- **HTTPS imposé.** Le trafic en clair est redirigé en 308 et l'en-tête HSTS
  demande au navigateur de ne plus y revenir pendant un an.
- **Quotas par visiteur.** Douze captures par heure et par adresse IP, soixante
  vérifications. Sans ça, un aspirateur laissé ouvert tourne en boucle.
- **Aucune indexation.** `robots.txt` interdit tout, et les pages portent
  `noindex` : ni l'outil ni les copies de sites tiers servies sous `/preview/`
  n'ont vocation à se retrouver dans un moteur de recherche.

Ce qu'il faut savoir :

- L'aperçu s'exécute avec `allow-same-origin`, sans quoi les scripts du site
  capturé n'accèdent pas à `localStorage` et ses fonctions (thème sombre,
  choix de langue, bandeau cookies) se cassent. En service unique, l'aperçu
  partage donc l'origine de l'interface : un site capturé délibérément
  hostile pourrait manipuler la page ShyClone affichée autour de lui. Ne
  clonez que des sites dont vous n'attendez pas ça. Pour une isolation
  complète, servez l'aperçu depuis un autre nom d'hôte et renseignez
  `VITE_PREVIEW_BASE` au build.
- L'authentification HTTP « Basic » transmet le mot de passe à chaque requête :
  elle ne vaut que derrière HTTPS. Render et les hébergeurs cités le
  fournissent d'office ; en auto-hébergement, mettez un certificat avant
  d'exposer quoi que ce soit.
- `SHYCLONE_TOKEN`, lui, est inscrit dans le bundle de l'interface au build :
  il écarte les robots, il ne protège pas d'un visiteur déterminé. C'est
  `SHYCLONE_MDP` qui ferme réellement l'accès.
- Un dépôt Git public expose l'intégralité de la pile. Si vous tenez à ce que
  personne ne sache comment le site est fait, le dépôt doit être privé.

## Pages légales

`public/mentions-legales.html`, `public/confidentialite.html` et
`public/cgu.html` sont servies par le moteur et reliées depuis le pied de
l'interface.

**Elles contiennent des emplacements marqués « à compléter »** : identité de
l'éditeur, coordonnées, hébergeur, pays du droit applicable. Tant qu'ils ne
sont pas remplis, ces pages ne valent rien juridiquement. Elles deviennent
obligatoires dès lors que le service est ouvert au public, et a fortiori s'il
devient payant.

La politique de confidentialité décrit l'état réel du code : aucun cookie,
aucun traceur, captures supprimées à treize minutes, adresse IP conservée une
heure pour les quotas. Si vous ajoutez une mesure d'audience ou un paiement,
il faudra la mettre à jour.

## Fonctionnement

Chaque capture est un **job** identifié, avec son propre dossier
`clones/<job_id>` : deux captures successives ne se mélangent jamais.

**Une capture est supprimée 13 minutes après la fin du clonage** (constante
`RETENTION` dans `src/server.py`). L'interface affiche le décompte et invite à
télécharger l'archive avant l'échéance ; passé ce délai, l'aperçu et le `.zip`
renvoient une erreur explicite. Ce ménage est ce qui permet de tenir sur le
petit disque d'un hébergement gratuit. En parallèle, seules les huit dernières
captures sont gardées.

Deux étendues au choix : **page seule** ne capture que l'adresse saisie, avec
ses styles et ses images ; **site complet** suit les liens internes jusqu'au
budget de pages. Pendant la capture, l'aperçu montre une maquette dont les
blocs se reconstruisent à chaque page réellement écrite, avec le chemin de la
page en cours — l'animation suit le moteur, elle ne tourne pas en boucle dans
le vide.

Le moteur parcourt le site en largeur depuis l'URL de départ :

- seules les pages du même domaine sont suivies (`www.` ignoré) ; si l'URL de
  départ redirige vers un autre domaine, c'est ce domaine-là qui est suivi ;
- les feuilles de style, scripts, images et polices sont téléchargés, y compris
  depuis d'autres domaines — ils atterrissent alors sous `_externe/<hôte>/` ;
- les `url()` et `@import` des CSS sont suivis sur trois niveaux ;
- les liens sont réécrits en chemins relatifs ; ceux qui dépassent le budget de
  pages sont réécrits en URL absolue pour rester cliquables ;
- un `<base>` présent dans la page d'origine est retiré, sans quoi il
  court-circuiterait les chemins locaux.

Les pages sont écrites dès qu'elles sont réécrites ; leurs ressources partent
en téléchargement parallèle (8 en simultané) en tâche de fond. La première page
apparaît donc en quelques secondes même sur un site lourd, au lieu d'attendre
que toutes ses ressources soient récupérées.

Le moteur se présente comme un navigateur (`User-Agent` Chrome, en-têtes
`Accept` correspondants) : beaucoup de sites renvoient 403 à un client qui
s'annonce comme robot. Ceux protégés par un service anti-robot (DataDome,
Cloudflare Bot Management) restent hors de portée, et le job le dit
explicitement plutôt que de renvoyer une capture vide.

Pages et ressources sont récupérées en parallèle — 8 pages et 12 ressources
simultanément par défaut — sur des connexions réutilisées d'une requête à
l'autre. Rouvrir une connexion TLS par ressource coûtait la moitié du temps :
dix requêtes vers le même hôte passent de 6,1 s à 1,7 s une fois la connexion
gardée ouverte.

Mesuré sur une capture de 40 pages et 178 ressources (getbootstrap.com) :

| pages / ressources en parallèle | Connexion neuve à chaque fois | Connexion réutilisée |
| --- | --- | --- |
| 1 / 4 | 38,7 s | 16,2 s |
| 5 / 8 | 11,5 s | 5,9 s |
| **8 / 12** (défaut) | 8,6 s | **4,0 s** |
| 12 / 16 | 7,3 s | 3,3 s |
| 16 / 24 | 6,5 s | 3,1 s |

Au-delà de 8/12 le gain se tasse tandis que le risque de bannissement grimpe :
c'est une vingtaine de connexions simultanées sur un seul serveur. Les trois
niveaux restent réglables (`SHYCLONE_PAGES_PAR`, `SHYCLONE_ASSETS_PAR`,
`SHYCLONE_PAGES_PAR_RENDU`) pour un site dont vous maîtrisez l'hébergement.

Si le site répond 429 ou 503, le moteur attend le délai qu'il indique puis
retente une fois, plutôt que d'insister.

**Sites nécessitant une connexion.** Le formulaire accepte un en-tête `Cookie`
de session, copié depuis les outils de développement du navigateur. Il n'est
transmis qu'au domaine capturé — jamais aux ressources externes, sans quoi la
session de l'utilisateur partirait chez des tiers — n'apparaît dans aucune
réponse de l'API et disparaît avec la capture.

**Certificats TLS.** Une chaîne de certificats incomplète ou expirée — fréquent
sur les hébergements régionaux — ne fait plus échouer la capture : le moteur
réessaie sans vérifier et le signale dans le journal. Jamais lorsqu'une session
est transmise, ce serait l'exposer à une interception.

**Domaine sans enregistrement DNS.** `www.mtn.cm` n'existe pas quand `mtn.cm`
existe : le moteur bascule automatiquement sur la variante qui résout.

**Ressources demandées à la racine.** Le JavaScript d'un site reconstruit
souvent ses URL à l'exécution (`/_next/…`, `/assets/…`), hors du dossier de la
capture. Le moteur rattache ces requêtes à leur capture grâce au référent, et
renvoie une vraie 404 quand le fichier manque au lieu de servir l'interface.

**Sites construits en JavaScript.** Une lecture statique du HTML ne peut rien
en tirer : le contenu est assemblé par le navigateur, et les morceaux de code
portent des noms calculés à l'exécution, introuvables dans la page.

L'option **Rendu JavaScript** ouvre alors un vrai navigateur sans interface. Il
en tire le DOM après exécution des scripts, et surtout la liste des ressources
réellement demandées — c'est ce qui rattrape les morceaux de code invisibles à
l'analyse. Mesures sur une capture d'une page, part du texte restituée :

| Site | Capture statique | Rendu navigateur |
| --- | --- | --- |
| react.dev | 0,12 | **1,00** |
| app.diagrams.net | 0,59 | **1,00** |
| excalidraw.com | 0,76 | **1,02** |
| getbootstrap.com | 0,99 | **1,00** |

Le rendu est quatre à sept fois plus lent, et la capture est **figée** : ses
scripts sont retirés — une page capturée en rendu navigateur ne contient plus
aucune balise `<script>`, là où la capture statique les conserve toutes. Les laisser serait contre-productif — une application
hydratée constate que le DOM enregistré ne correspond pas à ce qu'elle attend,
efface la page et la reconstruit, sans ses données. Sans eux, la capture est
une photographie fidèle, mais non interactive.

L'option n'apparaît dans l'interface que si un navigateur est disponible. Hors
rendu navigateur, le journal prévient simplement quand la page capturée n'a
presque aucun texte hors scripts.

**Adresse pointant sur un fichier.** Si l'URL de départ désigne un PDF, une
image ou une archive plutôt qu'une page, le fichier est conservé tel quel au
lieu de faire échouer la capture.

Garde-fous : 5000 pages maximum par job (50 par défaut), 8000 ressources, 1 Go,
12 s de timeout réseau par requête. Les chemins de fichiers sont assainis et confinés au dossier
du job.

Si aucune page n'a pu être récupérée, le job échoue explicitement — un site qui
renvoie 403 sur tout ne passe pas pour une capture réussie vide.

## API du moteur

| Méthode | Route | Rôle |
| --- | --- | --- |
| `GET` | `/api/health` | disponibilité du moteur |
| `POST` | `/api/check` | vérifie qu'une URL répond |
| `POST` | `/api/clone` | démarre un job (`url`, `pages_max`) |
| `GET` | `/api/jobs/<id>?from=n` | état et journal depuis l'événement `n` |
| `POST` | `/api/jobs/<id>/abort` | interrompt un job |
| `GET` | `/api/jobs/<id>/zip` | archive de la capture |
| `GET` | `/preview/<id>/<chemin>` | sert un fichier capturé |

## Organisation du code

```
src/
  server.py          moteur Flask : crawl, réécriture, archive, aperçu
  App.jsx            assemblage de l'écran
  components/        composants d'interface
  hooks/             thème, santé du moteur, machine à états d'un job, toasts
  lib/               client API, validation d'URL, formatage
```

Le thème clair/sombre est piloté par une classe `dark` sur `<html>`, les couleurs
sont des variables CSS déclarées dans `src/index.css`. Un composant n'a donc pas
à connaître le thème courant.

## Remarques

- `clones/` est ignoré par Git : les captures ne quittent jamais la machine.
- Ne capturez que des sites que vous avez le droit de copier.

## Scripts

| Commande | Rôle |
| --- | --- |
| `npm run dev` | moteur + interface (`start.sh`) |
| `npm run server` | moteur seul |
| `npm run client` | interface seule |
| `npm run build` | build de production dans `dist/` |
| `npm run lint` | Oxlint |

Il existe aussi un mode « service unique » où le moteur sert l'interface
compilée : `npm run build` puis `npm run server`, tout répond alors sur le
port 5000. C'est ce que fait l'image Docker.

---

ShyClone 1.0 — mr_shy
