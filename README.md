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

Variables d'environnement reconnues :

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `PORT` / `SHYCLONE_PORT` | port du moteur Flask | `5000` |
| `SHYCLONE_HOST` | interface d'écoute du moteur | `127.0.0.1` |
| `SHYCLONE_TOKEN` | jeton exigé sur `/api` (vide = désactivé) | vide |
| `VITE_API_TOKEN` | jeton envoyé par l'interface | vide |
| `SHYCLONE_UI_PORT` | port de Vite | `5173` |
| `SHYCLONE_ENGINE` | cible du proxy Vite | `http://127.0.0.1:5000` |
| `VITE_API_BASE` | préfixe d'API côté client, pour un build servi ailleurs | vide (relatif) |

## Déploiement

**Le moteur ne peut pas tourner sur Vercel.** Vercel exécute des fonctions
serverless : chaque requête est une invocation isolée, sans disque partagé,
sans état en mémoire conservé d'un appel à l'autre, et les threads lancés en
arrière-plan sont gelés dès que la réponse est renvoyée. Or une capture dure
souvent plusieurs minutes, écrit des fichiers qu'une requête ultérieure doit
relire pour l'aperçu et l'archive, et garde l'état du job en mémoire. Aucune
commande de démarrage ne contourne ça : c'est le modèle d'exécution qui est
incompatible.

### Le plus simple : ne rien déployer

ShyClone est un outil de poste de travail. `./start.sh` lance les deux parties
en local, sans compte ni carte bancaire, et sans exposer un robot d'aspiration
sur Internet. Si personne d'autre que vous ne doit s'en servir, c'est l'option
à retenir.

### Gratuit et en ligne : tout sur Render

Render héberge gratuitement un service web Docker **et** un site statique. Un
seul compte, un seul dépôt, pas de carte bancaire. `render.yaml` décrit les
deux services ; vous pouvez aussi les créer à la main dans le tableau de bord :

| Service | Type | Réglages |
| --- | --- | --- |
| `shyclone-moteur` | Web Service · Docker · Free | `Dockerfile` à la racine, health check `/api/health` |
| `shyclone-interface` | Static Site · Free | build `npm ci && npm run build`, publication `dist` |

Sur le site statique, renseignez `VITE_API_BASE` avec l'URL publique du moteur,
et `VITE_API_TOKEN` avec la même valeur que `SHYCLONE_TOKEN` côté moteur. Vite
inscrit ces variables dans le bundle au moment du build : il faut redéployer
l'interface après les avoir changées.

Les limites du palier gratuit, à connaître avant de s'y engager :

- le service s'endort après 15 minutes sans trafic ; la première capture qui
  suit attend environ une minute le temps du réveil ;
- le disque est éphémère, les captures disparaissent à chaque redéploiement —
  ce qui rejoint de toute façon la purge automatique décrite plus bas ;
- 512 Mo de RAM : évitez les captures de plusieurs centaines de pages.

Autres pistes gratuites du même genre : Hugging Face Spaces (Docker), Fly.io,
ou une instance Always Free chez Oracle Cloud pour une machine qui ne dort pas.

### Garder Vercel pour l'interface

Si vous tenez à Vercel, il peut héberger l'interface seule : `vercel.json` est
déjà configuré. Le moteur, lui, doit tourner ailleurs (Render, au hasard), et
`VITE_API_BASE` pointe vers lui.

### Protéger un moteur public

Un moteur exposé sur Internet télécharge n'importe quelle URL qu'on lui donne —
c'est un aspirateur ouvert à tous, et c'est votre adresse IP qui se fait
bannir. Définissez `SHYCLONE_TOKEN` côté moteur et `VITE_API_TOKEN` côté
interface : sans le jeton, les routes `/api` répondent 401. Laissées vides (cas
local), elles ne changent rien.

## Fonctionnement## Fonctionnement

Chaque capture est un **job** identifié, avec son propre dossier
`clones/<job_id>` : deux captures successives ne se mélangent jamais.

**Une capture est supprimée 13 minutes après la fin du clonage** (constante
`RETENTION` dans `src/server.py`). L'interface affiche le décompte et invite à
télécharger l'archive avant l'échéance ; passé ce délai, l'aperçu et le `.zip`
renvoient une erreur explicite. Ce ménage est ce qui permet de tenir sur le
petit disque d'un hébergement gratuit. En parallèle, seules les huit dernières
captures sont gardées.

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

Pages et ressources sont récupérées en parallèle : 5 pages et 8 ressources
simultanément. Sur getbootstrap.com, 94 pages et 301 ressources en 31 s.

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

- L'aperçu s'affiche dans une `iframe` sans `allow-same-origin` : le code
  capturé est du code tiers, il n'a pas accès à l'origine de l'application.
- `clones/` et `HL7_Site_Complet/` (sortie de l'ancienne version) sont ignorés
  par Git.
- Ne capturez que des sites que vous avez le droit de copier.

## Scripts

| Commande | Rôle |
| --- | --- |
| `npm run dev` | moteur + interface (`start.sh`) |
| `npm run server` | moteur seul |
| `npm run client` | interface seule |
| `npm run build` | build de production dans `dist/` |
| `npm run lint` | Oxlint |

---

ShyClone 1.0 — mr_shy
