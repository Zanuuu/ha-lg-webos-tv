# Déploiement — app Home Assistant locale

## Architecture retenue (phase 6)

Le service est empaqueté en **app (add-on) Home Assistant locale** : le
dépôt entier est le dossier de l'app (`config.yaml` + `Dockerfile` à la
racine), copié dans le répertoire `/addons` de la machine Home Assistant.
Le **Superviseur construit l'image localement** à l'installation — aucun
registre d'images ni CI n'est nécessaire.

L'interface est intégrée par **Ingress** : entrée « Réglages TV LG » dans la
barre latérale, authentification héritée de Home Assistant, aucun port
exposé sur le réseau. Un port direct (8000) existe mais est **désactivé par
défaut** ; pour l'activer : mapper le port dans l'onglet Réseau de l'app
**et** passer l'option `acces_lan` à `true` (sinon le service refuse les
connexions ne venant pas du proxy Ingress, `172.30.32.2`).

Décisions associées :
- `arch: [amd64]` uniquement (HA sur x86).
- Hébergement et CI de build
  d'image : **reportés**. La structure reste compatible avec une évolution
  future vers un dépôt d'apps installable par URL et des images
  pré-construites (`image:` dans `config.yaml`).

## Installation

1. **Copier le dépôt dans `/addons/lg_settings/`** sur la machine HA, sans
   les artefacts locaux (`.git`, `.venv`, `node_modules`, `data/`,
   `frontend/dist`). Depuis la machine de développement, avec l'add-on SSH
   (ou un accès SSH équivalent) :

   ```bash
   rsync -av --delete \
     --exclude='.git' --exclude='.venv' --exclude='node_modules' \
     --exclude='data/' --exclude='frontend/dist' \
     --exclude='__pycache__' --exclude='.pytest_cache' \
     <dépôt>/ \
     root@<ip-home-assistant>:/addons/lg_settings/
   ```

   Variante sans SSH : add-on Samba, partage `addons`, copie du dossier via
   l'explorateur de fichiers (mêmes exclusions).

2. **Faire apparaître l'app** : Paramètres → Modules complémentaires →
   Boutique des modules → menu ⋮ (en haut à droite) → « Rechercher les
   mises à jour ». L'app « Réglages LG OLED G5 » apparaît dans la section
   des modules locaux.

3. **Installer** : le Superviseur construit l'image sur place (build du
   frontend inclus — quelques minutes au premier coup).

4. **Configurer** : onglet Configuration → `lg_tv_host` = adresse IP du
   téléviseur. Laisser `acces_lan: false`.

5. **Démarrer**, puis accepter la demande d'appairage affichée par le
   téléviseur (première connexion uniquement).

6. **Ouvrir** : entrée « Réglages TV LG » dans la barre latérale.

## Recette

- Interface complète dans le panneau Ingress (sections Image / Son /
  Général / Assistance, drill-down, contrôles).
- Indicateur « Connecté » et mode d'image dans l'en-tête ; une modification
  faite à la télécommande se reflète en temps réel (WebSocket).
- Écriture d'un réglage anodin (ex. netteté) : appliqué sur la TV, visible
  dans l'historique.
- Presets : création, application, export/import.
- Persistance : redémarrer l'app → historique, presets et appairage TV
  conservés (`/data`).
- Port direct : `http://<ip-ha>:8000` ne répond pas tant que le port n'est
  pas mappé ; une fois mappé sans `acces_lan`, réponse 403.

## Mise à jour

1. Modifier le code, incrémenter `version:` dans `config.yaml` (et
   compléter `CHANGELOG.md`).
2. Recopier le dépôt vers `/addons/lg_settings/` (même commande rsync).
3. Boutique → « Rechercher les mises à jour » → la nouvelle version est
   proposée sur la fiche de l'app → Mettre à jour (rebuild local).

Les données de `/data` (historique, presets, clé d'appairage) survivent aux
mises à jour ; elles sont supprimées à la **désinstallation**.

## Détails techniques

- **Options** : le Superviseur écrit les options dans `/data/options.json` ;
  `backend/app/config.py` les lit directement (pas de bashio), avec la
  priorité variables d'environnement > options > défauts. La présence de ce
  fichier active le mode app (filtrage Ingress).
- **Filtrage Ingress** : middleware ASGI dans `backend/app/main.py`
  (`FiltreIngress`) — en mode app, seules les requêtes du proxy du
  Superviseur (`172.30.32.2`) sont acceptées (HTTP et WebSocket), sauf
  `acces_lan: true`.
- **URLs relatives** : le frontend est construit avec `base: './'` (Vite) et
  toutes les URLs (fetch et WebSocket) sont résolues depuis
  `document.baseURI` (`frontend/src/api.js`) — nécessaire car Ingress sert
  l'app derrière un préfixe dynamique.
- **Conteneur autonome (hors HA)** : `docker-compose.yml` reste utilisable
  (volume `./data:/data`, variable `LG_TV_HOST`) ; sans `options.json`, le
  filtrage Ingress est inactif.
