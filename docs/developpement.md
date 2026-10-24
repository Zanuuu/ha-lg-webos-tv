# Développer et publier

## Structure du dépôt

Le dépôt est un **dépôt d'apps (add-ons) Home Assistant** : `repository.yaml`
à la racine, l'app dans `lg_webos_tv/` (`config.yaml` + `Dockerfile`,
contexte de build = ce dossier). Le **Superviseur clone le dépôt et
construit l'image localement** à l'installation : aucun registre d'images
ni CI n'est nécessaire.

- `lg_webos_tv/backend/` : service FastAPI (Python 3.12) et accès au
  téléviseur (`app/televiseur.py`, seul module qui parle à la TV). Tests
  pytest dans `tests/`, scripts d'exploration et de diagnostic dans
  `scripts/`.
- `lg_webos_tv/frontend/` : interface React / Vite.
- `lg_webos_tv/menu-tree/` : arborescence des menus en JSON déclaratif
  (voir son `README.md`).
- `docs/` : notes de développement (exploration de l'API, incidents
  d'écriture, écarts entre firmwares).

`arch: [amd64]` uniquement pour l'instant.

## Lancer en local

```bash
cd lg_webos_tv/backend
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
LG_TV_HOST=<ip-du-téléviseur> .venv/bin/python -m uvicorn app.main:app --reload

cd lg_webos_tv/frontend
npm install
npm run dev      # ou npm run build : build servi par FastAPI
```

Sans `/data/options.json`, le service tourne en mode autonome (pas de
filtrage Ingress) ; données locales dans `lg_webos_tv/data/` (hors git).
Les scripts de `backend/scripts/` lisent aussi `LG_TV_HOST`.

Le conteneur autonome reste utilisable hors Home Assistant :
`docker-compose.yml` (volume `./data:/data`, variable `LG_TV_HOST`).

## Tests

```bash
cd lg_webos_tv/backend
.venv/bin/python -m pytest
.venv/bin/python scripts/valider_menu_tree.py   # cohérence de l'arborescence
```

## Publier une version

1. Incrémenter `version:` dans `lg_webos_tv/config.yaml` et compléter
   `lg_webos_tv/CHANGELOG.md`.
2. Commiter et pousser sur `main`.
3. Dans Home Assistant : Boutique → menu ⋮ → « Rechercher les mises à
   jour », puis Mettre à jour sur la fiche de l'app (rebuild local). Le
   Superviseur ne propose une mise à jour que si `version:` a changé.

Les données de `/data` (historique, presets, clé d'appairage) survivent aux
mises à jour ; elles sont supprimées à la désinstallation.

## Après une mise à jour du firmware du téléviseur

1. Lire le journal de l'app : un `401`/`403` à la connexion signale un
   changement du protocole d'appairage ou des permissions.
2. Diagnostic sans l'app : `cd lg_webos_tv/backend/scripts &&
   LG_TV_HOST=<ip> ../.venv/bin/python -u diag_enregistrement.py` (réponses
   brutes du téléviseur au `register`, puis sonde lecture/écriture ;
   `--non-signe` pour le manifeste de l'app).
3. Relancer l'inventaire (`explore_05_inventaire.py`) et comparer
   `lg_webos_tv/backend/app/inventaire-api.json` à sa version précédente :
   une clé disparue ferait rejeter toute sa catégorie à l'abonnement.
4. Consigner les écarts dans `docs/` (méthode d'extraction du firmware :
   `docs/ecarts-firmware-43.21.77.md`).

Précédent : 43.21.77 / webOS 11.2 (`docs/incidents-ecriture.md` § 5 à 7).

## Détails techniques

- **Options** : le Superviseur écrit les options dans `/data/options.json` ;
  `backend/app/config.py` les lit directement (pas de bashio), avec la
  priorité variables d'environnement > options > défauts. La présence de ce
  fichier active le mode app (filtrage Ingress). `lg_tv_host` n'a pas de
  valeur par défaut : sans elle, le service reste à l'état
  `non_configure` et ne tente aucune connexion.
- **Filtrage Ingress** : middleware ASGI `FiltreIngress`
  (`backend/app/main.py`). En mode app, seules les requêtes du proxy du
  Superviseur (`172.30.32.2`) sont acceptées (HTTP et WebSocket), sauf
  `acces_lan: true`. Le port direct 8000 est déclaré mais non mappé par
  défaut.
- **URLs relatives** : le frontend est construit avec `base: './'` (Vite) et
  toutes les URLs (fetch et WebSocket) sont résolues depuis
  `document.baseURI` (`frontend/src/api.js`), car Ingress sert l'app
  derrière un préfixe dynamique.
- **Pas d'en-tête anti-cadre** : le panneau Ingress est affiché dans un
  cadre de l'interface HA ; le service n'émet ni `X-Frame-Options` ni
  `frame-ancestors`.
