from app import arbre

ID_CONTROLE_PARENTAL = "general.systeme.securite.activer-la-fonction"


def test_interrupteur_ordinaire_converti_en_on_off():
    categorie, cle, valeur = arbre.preparer_ecriture(
        "general.accessibilite.guide-audio.activer-la-fonction", True)
    assert (categorie, cle, valeur) == ("option", "audioGuidance", "on")


def test_parental_control_reste_booleen_natif():
    # Le téléviseur refuse "on"/"off" pour cette clé et attend un booléen
    # JSON natif (constaté le 17/08/2026, cf. docs/incidents-ecriture.md).
    categorie, cle, valeur = arbre.preparer_ecriture(ID_CONTROLE_PARENTAL, False)
    assert (categorie, cle, valeur) == ("lock", "parentalControl", False)
    assert valeur is False  # et non "off"


def test_pays_est_en_lecture_seule():
    entree = arbre.par_id()["general.systeme.lieu.pays"]
    assert entree["api"]["acces"] == "lecture_seule"


def test_black_level_et_white_balance_luminance_en_lecture_seule():
    assert arbre.par_id()["image.parametres-avances.luminosite.plage-video"] \
        ["api"]["acces"] == "lecture_seule"
    assert arbre.par_id()[
        "image.parametres-avances.couleur.balance-blancs.luminosite-signal-max"
    ]["api"]["acces"] == "lecture_seule"
