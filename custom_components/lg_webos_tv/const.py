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
# Capteur de secours facultatif : sert quand le principal est indisponible ou
# figé, une fois leur facteur relatif appris (secours.py).
CONF_CAPTEUR_SECOURS = "capteur_secours"
CONF_LUX_MIN = "lux_min"
CONF_LUX_MAX = "lux_max"
CONF_LUMINOSITE_MIN = "luminosite_min"
CONF_LUMINOSITE_MAX = "luminosite_max"
CONF_ECART_MINIMAL = "ecart_minimal"
CONF_PAUSE_MIN = "pause"
# La pause se lève aussi quand l'éclairage change nettement (lux filtré ×2 ou
# ÷2 depuis la reprise en main), sauf pause demandée depuis le panneau.
CONF_REPRISE_SUR_CHANGEMENT = "reprise_sur_changement"
CONF_MODES_EXCLUS = "modes_exclus"
# Point intermédiaire facultatif de la courbe, [lux, luminosité] ; absent,
# la courbe est une droite sur ln(lux) entre les deux extrémités.
CONF_POINT_INTERMEDIAIRE = "point_intermediaire"
# Points d'ancrage de la mise en route (au plus deux), de quoi caler la
# pente sur un deuxième réglage ; oubliés si la courbe est retouchée.
CONF_ANCRAGES = "ancrages"
CLES_COURBE = (CONF_LUX_MIN, CONF_LUX_MAX, CONF_LUMINOSITE_MIN, CONF_LUMINOSITE_MAX,
               CONF_POINT_INTERMEDIAIRE)
# Où se trouve le capteur (docs/etude-luminosite-adaptative.md, § 3.3) :
# A à G, ou inconnu.
CONF_EMPLACEMENT = "emplacement_capteur"
EMPLACEMENTS = ["inconnu", "a", "b", "c", "d", "e", "f", "g"]
# Options avancées du signal : absentes, elles suivent le profil du capteur
# et son emplacement (signal_lux.constantes).
CONF_LISSAGE_MONTEE = "lissage_montee_s"
CONF_LISSAGE_DESCENTE = "lissage_descente_s"
CONF_HYSTERESIS_MONTEE = "hysteresis_montee"
CONF_HYSTERESIS_DESCENTE = "hysteresis_descente"
CONF_CONFIRMATION_SAUT = "confirmation_saut_s"
CONF_GEL_ECRITURE = "gel_ecriture_s"
# Rampe de la luminosité (rampe.py) : taille des pas et vitesse en points par
# seconde.
CONF_RAMPE_PAS = "rampe_pas"
CONF_RAMPE_DEBIT = "rampe_debit"
# Options avancées, toutes facultatives : absentes, elles prennent leur
# valeur par défaut (écart minimal, rampe) ou celle du profil du capteur
# (signal).
OPTIONS_AVANCEES = (CONF_ECART_MINIMAL, CONF_LISSAGE_MONTEE, CONF_LISSAGE_DESCENTE,
                    CONF_HYSTERESIS_MONTEE, CONF_HYSTERESIS_DESCENTE, CONF_CONFIRMATION_SAUT,
                    CONF_GEL_ECRITURE, CONF_RAMPE_PAS, CONF_RAMPE_DEBIT)
# 3 jusqu'à la 2.5.0 : les rampes atteignent la cible exactement, l'écart
# minimal ne sert plus qu'à ignorer les dérives d'un point.
ECART_MINIMAL_DEFAUT = 2
ECART_MINIMAL_ANCIEN_DEFAUT = 3
# Seuils de l'entité « Ambiance » (lx), facultatifs : absents, ce sont les
# tiers de la courbe, qui suivent ses retouches (ambiance.py).
CONF_AMBIANCE_SOMBRE = "ambiance_sombre"
CONF_AMBIANCE_CLAIRE = "ambiance_claire"
OPTIONS_AMBIANCE = (CONF_AMBIANCE_SOMBRE, CONF_AMBIANCE_CLAIRE)
# Décalage pilotable de la luminosité adaptative (entité number), ajouté à la
# cible de la courbe.
DECALAGE_MIN, DECALAGE_MAX = -30, 30
# Option groupée des modes HDR et Dolby Vision (hdr*, dolbyHdr*) : leurs
# libellés français ne figurent pas dans l'arbre des menus.
MODES_HDR = "hdr"
OPTIONS_LUMINOSITE_DEFAUT = {
    CONF_LUX_MIN: 5,
    CONF_LUX_MAX: 300,
    CONF_LUMINOSITE_MIN: 40,
    CONF_LUMINOSITE_MAX: 100,
    CONF_PAUSE_MIN: 120,
    # 2.9.0 : vrai par défaut, y compris pour les installations existantes.
    CONF_REPRISE_SUR_CHANGEMENT: True,
    CONF_MODES_EXCLUS: ["filmMaker", "expert1", "expert2", MODES_HDR],
    CONF_EMPLACEMENT: "inconnu",
}
