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

# Luminosité adaptative : options de l'entrée et valeurs par défaut (celles
# de l'ancien blueprint).
CONF_CAPTEUR_LUX = "capteur_lux"
CONF_LUX_MIN = "lux_min"
CONF_LUX_MAX = "lux_max"
CONF_LUMINOSITE_MIN = "luminosite_min"
CONF_LUMINOSITE_MAX = "luminosite_max"
CONF_ECART_MINIMAL = "ecart_minimal"
CONF_PAUSE_MIN = "pause"
CONF_MODES_EXCLUS = "modes_exclus"
# Option groupée des modes HDR et Dolby Vision (hdr*, dolbyHdr*) : leurs
# libellés français ne figurent pas dans l'arbre des menus.
MODES_HDR = "hdr"
OPTIONS_LUMINOSITE_DEFAUT = {
    CONF_LUX_MIN: 5,
    CONF_LUX_MAX: 300,
    CONF_LUMINOSITE_MIN: 40,
    CONF_LUMINOSITE_MAX: 100,
    CONF_ECART_MINIMAL: 3,
    CONF_PAUSE_MIN: 120,
    CONF_MODES_EXCLUS: ["filmMaker", "expert1", "expert2", MODES_HDR],
}
