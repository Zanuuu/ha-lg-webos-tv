"""Configuration du service : options de l'app Home Assistant si présentes,
surchargées par variables d'environnement (priorité : env > options > défaut)."""

import json
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent

# En mode app Home Assistant, le Superviseur dépose les options utilisateur
# dans /data/options.json ; hors HA ce fichier n'existe pas. Le chemin est
# surchargeable pour les tests.
OPTIONS_HA = Path(os.environ.get("LG_OPTIONS_HA", "/data/options.json"))


def _charger_options_ha() -> dict:
    if not OPTIONS_HA.is_file():
        return {}
    try:
        return json.loads(OPTIONS_HA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_options = _charger_options_ha()

# Vrai quand le service tourne en app Home Assistant (options déposées par le
# Superviseur) : active le filtrage Ingress dans main.py.
MODE_APP_HA = OPTIONS_HA.is_file()

TV_HOST = os.environ.get("LG_TV_HOST") or _options.get("lg_tv_host") or "192.168.1.50"

# Autorise l'accès hors Ingress (utilisateur ayant mappé le port direct).
ACCES_LAN = bool(_options.get("acces_lan", False))

# IP du proxy Ingress du Superviseur : seule source acceptée en mode app.
INGRESS_PROXY_IP = "172.30.32.2"

DATA_DIR = Path(os.environ.get("LG_DATA_DIR", RACINE / "data"))
CLE_TV_DB = DATA_DIR / "bscpylgtv.sqlite"
HISTORIQUE_DB = DATA_DIR / "historique.sqlite"
PRESETS_DB = DATA_DIR / "presets.sqlite"

MENU_TREE_DIR = Path(os.environ.get("LG_MENU_TREE_DIR", RACINE / "menu-tree"))
INVENTAIRE = RACINE / "docs" / "inventaire-api.json"

# Reconnexion : première tentative rapide puis repli progressif.
RECONNEXION_DELAI_MIN_S = 5
RECONNEXION_DELAI_MAX_S = 30
