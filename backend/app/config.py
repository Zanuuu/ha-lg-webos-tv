"""Configuration du service, surchargée par variables d'environnement."""

import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent

TV_HOST = os.environ.get("LG_TV_HOST", "192.168.1.50")

DATA_DIR = Path(os.environ.get("LG_DATA_DIR", RACINE / "data"))
CLE_TV_DB = DATA_DIR / "bscpylgtv.sqlite"
HISTORIQUE_DB = DATA_DIR / "historique.sqlite"
PRESETS_DB = DATA_DIR / "presets.sqlite"

MENU_TREE_DIR = Path(os.environ.get("LG_MENU_TREE_DIR", RACINE / "menu-tree"))
INVENTAIRE = RACINE / "docs" / "inventaire-api.json"

# Reconnexion : première tentative rapide puis repli progressif.
RECONNEXION_DELAI_MIN_S = 5
RECONNEXION_DELAI_MAX_S = 30
