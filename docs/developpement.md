# Développer et publier

## Structure du dépôt

Le dépôt est une **intégration Home Assistant distribuée par HACS**
(`hacs.json` à la racine), publiée sur GitHub
(« Publier une version » ci-dessous).

- `custom_components/lg_webos_tv/` : l'intégration, seule partie installée
  par HACS.
  - `televiseur.py` : seul module qui parle au téléviseur (bscpylgtv et
    appels SSAP bruts) ; indépendant de Home Assistant, testable seul.
  - `arbre.py`, `restauration.py`, `presets.py`, `historique.py` : arbre
    des menus, écritures validées et historisées, presets, retour arrière.
  - `ecritures.py` : file d'écriture coalescente, partagée par les entités,
    les actions et le panneau.
  - `luminosite_adaptative.py` : luminosité OLED selon un capteur de lux
    (options de l'entrée) ; reprise en main détectée par l'origine des
    notifications du téléviseur et par l'écoute de l'historique.
  - `entite.py` et plateformes (`number.py`, `select.py`…) : entités
    dérivées de l'arbre.
  - `services.py` (actions), `websocket.py` (API du panneau), `panneau.py`
    (enregistrement du panneau), `config_flow.py`, `diagnostics.py`.
  - `menu_tree/` : arborescence des menus en JSON déclaratif (voir son
    `README.md`) ; `inventaire-api.json` : clés lisibles par catégorie,
    lu au démarrage ; `manifeste-ssap.json` : manifeste d'appairage.
  - `frontend/` : **build** du panneau (commité, pas de CI).
- `frontend/` : sources React / Vite du panneau.
- `tests/` : tests pytest sous Home Assistant
  (`pytest-homeassistant-custom-component`).
- `docs/` : notes de développement (exploration de l'API, incidents
  d'écriture, écarts entre firmwares).
- `lg_webos_tv/` et `repository.yaml` : ancienne app (add-on) 1.3.0, gelée,
  à retirer. Ses scripts d'exploration et de diagnostic
  (`lg_webos_tv/backend/scripts/`) restent utiles et lisent les données de
  l'intégration.

## Environnement

Home Assistant 2026.10 exige Python 3.14 ; `uv` fournit l'interpréteur.

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv -r requirements-dev.txt
.venv/bin/python -m pytest
```

Panneau (Node 22 ou plus) :

```bash
cd frontend
npm install
npm run build   # écrit dans custom_components/lg_webos_tv/frontend/
```

Le build doit être refait et commité à chaque modification de
`frontend/src/`. Le panneau n'a pas de mode autonome : il lui faut l'objet
`hass` de Home Assistant (voir « Panneau » ci-dessous pour le tester).

Arborescence : `lg_webos_tv/backend/.venv/bin/python
lg_webos_tv/backend/scripts/valider_menu_tree.py`.

## Publier une version

1. Incrémenter `version` dans `custom_components/lg_webos_tv/manifest.json`
   et compléter `CHANGELOG.md` ; refaire le build du panneau s'il a changé.
2. Commiter et pousser sur `main`.
3. Dans HACS : l'intégration → menu ⋮ → Mettre à jour (ou attendre la
   détection), puis redémarrer Home Assistant.

## Après une mise à jour du firmware du téléviseur

1. Lire le journal de Home Assistant (`custom_components.lg_webos_tv`) et
   l'entité diagnostic « Voie d'écriture » ; une demande de réauthentification
   signale une clé d'appairage refusée.
2. Diagnostic sans Home Assistant :
   `cd lg_webos_tv/backend && LG_TV_HOST=<ip> .venv/bin/python
   scripts/diag_enregistrement.py` (réponses brutes au `register`, sondes
   lecture/écriture), `scripts/diag_alerte.py` (pont d'alerte),
   `scripts/diag_origine.py` (champ `caller`, cadence d'écriture).
3. Relancer l'inventaire (`scripts/explore_05_inventaire.py`) et comparer
   `custom_components/lg_webos_tv/inventaire-api.json` à sa version
   précédente : une clé disparue ferait rejeter toute sa catégorie à
   l'abonnement.
4. Consigner les écarts dans `docs/` (méthode d'extraction du firmware :
   `docs/ecarts-firmware-43.21.77.md`).

Précédent : 43.21.77 / webOS 11.2 (`docs/incidents-ecriture.md` § 5 à 7,
`docs/rapport-api.md` phase 7).

## Détails techniques

- **Boucle d'événements** : rien de bloquant dans la boucle de Home
  Assistant. Le client bscpylgtv est construit dans un fil à part (son
  constructeur lit le manifeste et crée un contexte SSL) ; la clé
  d'appairage est passée par `client_key` (le stockage sqlitedict de
  bscpylgtv n'est jamais ouvert) ; arbre, inventaire et bases SQLite sont
  chargés hors boucle à l'installation de l'entrée.
- **Confirmation d'écriture** : par la notification d'abonnement (≈ 0,15 s
  sur 43.21.77), relecture en secours au bout d'une seconde.
- **Origine des changements** : champ `caller` des notifications
  (`docs/rapport-api.md`, phase 7) et suivi des écritures en cours ; une
  relecture passe par le même chemin qu'une notification, pour que toute
  valeur nouvelle soit diffusée.
- **Panneau** : enregistré par `panel_custom` avec `embed_iframe` ; Home
  Assistant charge `panneau.js` dans une iframe, y crée
  `<lg-webos-tv-panel>` et lui transmet `hass`. Le frontend appelle les
  commandes websocket `lg_webos_tv/…` (réservées aux administrateurs) par
  `hass.callWS`. Pour le tester hors de Home Assistant : page qui importe
  `panneau.js`, crée l'élément et lui donne un `hass` simulé (`callWS`,
  `connection.subscribeMessage`, `themes.darkMode`).
- **Tests et frontend de Home Assistant** : `frontend` et `panel_custom`
  sont en `after_dependencies` et le panneau n'est enregistré que si le
  frontend est chargé, ce qui évite d'installer le paquet du frontend de
  Home Assistant dans l'environnement de test.
