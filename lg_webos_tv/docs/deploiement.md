# Déploiement — dépôt d'apps Home Assistant

## Architecture retenue

Le projet est un **dépôt d'apps (add-ons) Home Assistant** hébergé sur
Dépôt : https://github.com/Zanuuu/ha-lg-webos-tv (public).
`repository.yaml` à la racine du dépôt, l'app dans `lg_webos_tv/`
(`config.yaml` + `Dockerfile`). Le **Superviseur clone le dépôt et
construit l'image localement** à l'installation : aucun registre d'images
ni CI n'est nécessaire.

L'interface est intégrée par **Ingress** : entrée « LG webOS TV » dans la
barre latérale, authentification héritée de Home Assistant, aucun port
exposé sur le réseau. Un port direct (8000) existe mais est **désactivé par
défaut** ; pour l'activer : mapper le port dans l'onglet Réseau de l'app
**et** passer l'option `acces_lan` à `true` (sinon le service refuse les
connexions ne venant pas du proxy Ingress, `172.30.32.2`).

Décisions associées :
- `arch: [amd64]` uniquement (HA sur x86).
- CI de build d'image : **reportée**. Évolution possible vers des images
  pré-construites (`image:` dans `config.yaml`) si le build local devient
  gênant.

## Installation

1. **Ajouter le dépôt** : Paramètres → Modules complémentaires → Boutique
   des modules → menu ⋮ (en haut à droite) → Dépôts → ajouter
   `https://github.com/Zanuuu/ha-lg-webos-tv`.

2. **Installer** l'app « LG webOS TV » depuis la Boutique : le Superviseur
   construit l'image sur place (build du frontend inclus — quelques minutes
   au premier coup).

3. **Configurer** : onglet Configuration → `lg_tv_host` = adresse IP du
   téléviseur. Laisser `acces_lan: false`.

4. **Démarrer**, puis accepter la demande d'appairage « Réglages TV (Home
   Assistant) » affichée par le téléviseur (première connexion uniquement ;
   l'en-tête affiche « Appairage » tant qu'elle n'est pas acceptée).

5. **Ouvrir** : entrée « LG webOS TV » dans la barre latérale.

## Bascule depuis l'ancienne app locale (`/addons/lg_settings`)

L'app installée depuis le dépôt est une app distincte pour le Superviseur
(identifiant `lg_webos_tv`) : historique, presets et clé d'appairage de
l'app locale ne sont **pas repris**.

1. Désinstaller l'app locale « LG webOS TV » (section des modules locaux).
2. Supprimer le dossier `/addons/lg_settings` (add-on SSH ou Samba), sinon
   la Boutique continue de la proposer.
3. Suivre l'installation ci-dessus.

## Recette

- Interface complète dans le panneau Ingress (sections Image / Son /
  Général / Assistance, drill-down, contrôles).
- Indicateur « Connecté » et mode d'image dans l'en-tête ; une modification
  faite à la télécommande se reflète en temps réel (WebSocket).
- Écriture d'un réglage anodin (ex. netteté) : appliqué sur la TV, visible
  dans l'historique. Sous webOS 11 : bandeau « Modification impossible… »,
  contrôles grisés, aucune écriture tentée.
- Presets : création, application, export/import.
- Persistance : redémarrer l'app → historique, presets et appairage TV
  conservés (`/data`).
- Port direct : `http://<ip-ha>:8000` ne répond pas tant que le port n'est
  pas mappé ; une fois mappé sans `acces_lan`, réponse 403.

## Mise à jour

1. Modifier le code, incrémenter `version:` dans `lg_webos_tv/config.yaml`
   (et compléter `lg_webos_tv/CHANGELOG.md`).
2. Commiter et pousser sur `main` (`git push`).
3. Boutique → menu ⋮ → « Rechercher les mises à jour » → la nouvelle
   version est proposée sur la fiche de l'app → Mettre à jour (rebuild
   local). Le Superviseur ne propose une mise à jour que si `version:` a
   changé.

Les données de `/data` (historique, presets, clé d'appairage) survivent aux
mises à jour ; elles sont supprimées à la **désinstallation**.

## Après une mise à jour du firmware du téléviseur

1. Lire le journal de l'app : un `401`/`403` à la connexion signale un
   changement du protocole d'appairage ou des permissions.
2. Diagnostic sans l'app : `cd backend/scripts && ../.venv/bin/python -u
   diag_enregistrement.py` (réponses brutes du téléviseur au `register`,
   puis sonde lecture/écriture ; `--non-signe` pour le manifeste de l'app).
3. Relancer l'inventaire (`explore_05_inventaire.py`) et comparer
   `docs/inventaire-api.json` à sa version précédente : une clé disparue
   ferait rejeter toute sa catégorie à l'abonnement.
4. Extraire le firmware (cf. `docs/ecarts-firmware-43.21.77.md`, méthode)
   et consigner les écarts dans `docs/`.

Précédent : 43.21.77 / webOS 11.2 (`docs/incidents-ecriture.md` § 5).

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
