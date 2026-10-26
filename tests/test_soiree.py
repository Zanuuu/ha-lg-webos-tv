"""Soirée (soiree.py) : plages, sources, fin à la main, lumière bleue."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from custom_components.lg_webos_tv.soiree import (EtatSoiree, PiloteLumiereBleue,
                                                  Source, SuiviSoiree, occurrence,
                                                  prochaine, valider)

ZONE = ZoneInfo("Europe/Paris")
DEBUT, FIN = time(21), time(6)


def a(jour: int, heure: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, jour, heure, minute, tzinfo=ZONE)


# ----------------------------------------------------------------- plages
def test_plage_qui_passe_minuit():
    assert occurrence(a(20, 20, 59), DEBUT, FIN) is None
    assert occurrence(a(20, 21), DEBUT, FIN) == (a(20, 21), a(21, 6))
    assert occurrence(a(21, 2), DEBUT, FIN) == (a(20, 21), a(21, 6))
    assert occurrence(a(21, 6), DEBUT, FIN) is None


def test_plage_dans_la_journee_et_plage_vide():
    assert occurrence(a(20, 14), time(13), time(15)) == (a(20, 13), a(20, 15))
    assert occurrence(a(20, 16), time(13), time(15)) is None
    assert occurrence(a(20, 21), DEBUT, DEBUT) is None


def test_prochaine_heure_strictement_apres():
    assert prochaine(a(20, 21), DEBUT) == a(21, 21)
    assert prochaine(a(20, 20), DEBUT) == a(20, 21)


def test_changement_d_heure_garde_l_heure_murale():
    # Nuit du 24 au 25 octobre 2026 : passage à l'heure d'hiver à 3 h.
    depart, arrivee = occurrence(datetime(2026, 10, 25, 1, tzinfo=ZONE), DEBUT, FIN)
    assert (depart.hour, arrivee.hour) == (21, 6)
    assert arrivee.utcoffset() == timedelta(hours=1)


# ----------------------------------------------------------------- sources
def test_source_heure():
    suivi = SuiviSoiree()
    etat = suivi.evaluer(a(20, 20), Source(debut=DEBUT), FIN)
    assert etat == EtatSoiree(False, echeance=a(20, 21))
    etat = suivi.evaluer(a(20, 22), Source(debut=DEBUT), FIN)
    assert etat == EtatSoiree(True, fin=a(21, 6), echeance=a(21, 6))


def test_source_sans_heure_ne_commence_pas():
    assert SuiviSoiree().evaluer(a(20, 22), Source(debut=None), FIN) == EtatSoiree(False)


def test_source_interrupteur():
    suivi = SuiviSoiree()
    eteinte = Source(interrupteur=True, allumee=False, depuis=a(20, 19))
    assert suivi.evaluer(a(20, 22), eteinte, FIN) == EtatSoiree(False)
    allumee = Source(interrupteur=True, allumee=True, depuis=a(20, 22))
    assert suivi.evaluer(a(20, 22, 1), allumee, FIN) == EtatSoiree(True, fin=a(21, 6),
                                                                 echeance=a(21, 6))
    # Toujours à `on` après l'heure de fin : la Soirée est finie.
    assert not suivi.evaluer(a(21, 7), allumee, FIN).active
    indisponible = Source(interrupteur=True, allumee=None, depuis=a(20, 22))
    assert not suivi.evaluer(a(20, 23), indisponible, FIN).active


def test_terminee_jusqu_a_la_fin_de_la_plage():
    suivi = SuiviSoiree()
    source = Source(debut=DEBUT)
    suivi.terminer(suivi.evaluer(a(20, 22), source, FIN))
    etat = suivi.evaluer(a(20, 23), source, FIN)
    assert etat == EtatSoiree(False, terminee_jusqua=a(21, 6), echeance=a(21, 6))
    assert suivi.evaluer(a(21, 21, 30), source, FIN).active
    assert suivi.terminee_jusqua is None


def test_terminee_reste_terminee_si_l_interrupteur_repasse_a_on():
    suivi = SuiviSoiree()
    suivi.terminer(suivi.evaluer(
        a(20, 22), Source(interrupteur=True, allumee=True, depuis=a(20, 21)), FIN))
    relancee = Source(interrupteur=True, allumee=True, depuis=a(20, 23))
    assert not suivi.evaluer(a(20, 23, 1), relancee, FIN).active
    lendemain = Source(interrupteur=True, allumee=True, depuis=a(21, 21))
    assert suivi.evaluer(a(21, 21, 1), lendemain, FIN).active


def test_terminer_hors_soiree_ne_fait_rien():
    suivi = SuiviSoiree()
    suivi.terminer(EtatSoiree(False))
    assert suivi.terminee_jusqua is None


# ----------------------------------------------------------- lumière bleue
def test_lumiere_bleue_posee_puis_restauree():
    pilote = PiloteLumiereBleue()
    assert pilote.voulue(True, True, False, "off") == "on"
    pilote.avant_ecriture("on", "off")
    pilote.confirmee("on")
    assert pilote.voulue(True, True, False, "on") is None
    assert pilote.voulue(False, True, False, "on") == "off"
    pilote.confirmee("off")
    assert pilote == PiloteLumiereBleue()


def test_lumiere_bleue_option_desactivee_ou_valeur_inconnue():
    pilote = PiloteLumiereBleue()
    assert pilote.voulue(True, False, False, "off") is None
    assert pilote.voulue(True, True, False, None) is None


def test_lumiere_bleue_deja_active_n_est_ni_ecrite_ni_restauree():
    pilote = PiloteLumiereBleue()
    assert pilote.voulue(True, True, False, "on") is None
    assert pilote.voulue(False, True, False, "on") is None


def test_lumiere_bleue_mode_laisse_de_cote():
    pilote = PiloteLumiereBleue()
    pilote.avant_ecriture("on", "off")
    pilote.confirmee("on")
    assert pilote.voulue(True, True, True, "on") == "off"
    pilote.confirmee("off")
    # Sortie du mode laissé de côté : réactivée, la base relue à nouveau.
    assert pilote.voulue(True, True, False, "off") == "on"


def test_reprise_en_main_de_la_lumiere_bleue():
    pilote = PiloteLumiereBleue()
    pilote.avant_ecriture("on", "off")
    pilote.confirmee("on")
    assert pilote.reprendre_en_main(soiree=True)
    assert pilote.voulue(True, True, False, "off") is None
    # Ni restaurée à la fin, ni réactivée avant la Soirée suivante.
    assert pilote.voulue(False, True, False, "off") is None
    pilote.fin_soiree()
    assert pilote.voulue(True, True, False, "off") == "on"


def test_changement_hors_soiree_sans_rien_a_restaurer():
    pilote = PiloteLumiereBleue()
    assert not pilote.reprendre_en_main(soiree=False)
    assert pilote == PiloteLumiereBleue()


def test_persistance_du_pilote():
    pilote = PiloteLumiereBleue(base="off", posee=True)
    assert PiloteLumiereBleue.depuis_dict(pilote.en_dict()) == pilote
    assert PiloteLumiereBleue.depuis_dict(None) == PiloteLumiereBleue()


# ----------------------------------------------------------------- options
def test_validation_des_options():
    options, erreurs = valider({"soiree": True, "soiree_debut": "21:30:00",
                                "soiree_fin": "06:00"})
    assert erreurs == {} and options["soiree_debut"] == "21:30"
    assert valider({"soiree_debut": "25:00"})[1] == {"soiree_debut": "heure_invalide"}
    assert valider({"soiree_debut": "21:00", "soiree_fin": "21:00"})[1] == {
        "soiree_fin": "soiree_debut_egal_fin"}
    # Avec une entité, l'heure de début de l'option ne sert pas.
    assert valider({"soiree_debut": "21:00", "soiree_fin": "21:00",
                    "soiree_entite": "schedule.soir"})[1] == {}
    assert valider({"soiree_entite": "sensor.lux"})[1] == {
        "soiree_entite": "soiree_entite_invalide"}
    assert valider({"soiree": "oui"})[1] == {"soiree": "hors_bornes"}
