"""Constantes de l'intégration : identifiants, données embarquées, délais."""

from pathlib import Path

DOMAIN = "lg_webos_tv"

# Clé d'appairage SSAP, conservée dans l'entrée de configuration : le
# stockage sqlitedict de bscpylgtv ferait des accès disque bloquants dans la
# boucle de Home Assistant (docs/rapport-api.md, phase 7).
CONF_CLE_CLIENT = "client_key"

_DOSSIER = Path(__file__).resolve().parent
MENU_TREE_DIR = _DOSSIER / "menu_tree"
INVENTAIRE = _DOSSIER / "inventaire-api.json"
# Manifeste d'appairage SSAP non signé : webOS 11 met en liste noire la
# signature du manifeste par défaut de bscpylgtv (docs/incidents-ecriture.md).
MANIFESTE_SSAP = _DOSSIER / "manifeste-ssap.json"

# Reconnexion : première tentative rapide puis repli progressif.
RECONNEXION_DELAI_MIN_S = 5
RECONNEXION_DELAI_MAX_S = 30

# La demande d'appairage expire au bout de 120 s sur le téléviseur ; un peu
# de marge pour recevoir sa réponse.
APPAIRAGE_DELAI_S = 130
