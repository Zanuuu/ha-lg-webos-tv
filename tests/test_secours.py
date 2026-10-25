"""Capteur de secours : facteur relatif appris, stabilité du rapport,
incohérences et choix du capteur qui sert."""

import math

import pytest

from custom_components.lg_webos_tv.secours import (DISPERSION_MAX,
                                                   ECHANTILLON_S,
                                                   ECHANTILLONS_MAX,
                                                   ECHANTILLONS_MIN,
                                                   RapportCapteurs, choisir)


def remplir(rapport, couples, debut=0):
    for i, (principal, secours) in enumerate(couples):
        assert rapport.noter(debut + i * ECHANTILLON_S, principal, secours)


def test_apprentissage_puis_facteur():
    rapport = RapportCapteurs()
    remplir(rapport, [(100, 50)] * (ECHANTILLONS_MIN - 1))
    assert (rapport.etat, rapport.facteur, rapport.utilisable) == ("apprentissage", None, False)
    remplir(rapport, [(100, 50)], debut=10_000)
    assert rapport.facteur == pytest.approx(2)
    assert rapport.etat == "stable" and rapport.utilisable
    assert rapport.resume() == {"etat": "stable", "facteur": 2.0, "echantillons": 30,
                                "requis": 30, "dispersion": 1.0,
                                "zeros": {"principal": 0, "secours": 0}}


def test_une_mesure_par_minute_au_plus():
    rapport = RapportCapteurs()
    assert rapport.noter(0, 10, 5)
    assert not rapport.noter(30, 10, 5)
    assert rapport.noter(ECHANTILLON_S, 10, 5)
    assert rapport.nombre == 2


def test_mediane_robuste_aux_transitions():
    """Une lampe allumée : le capteur lent a du retard sur quelques
    échantillons, la médiane n'en tient pas compte."""
    rapport = RapportCapteurs()
    couples = [(40, 20)] * 40 + [(400, 20)] * 4 + [(400, 200)] * 20
    remplir(rapport, couples)
    assert rapport.facteur == pytest.approx(2)
    assert rapport.utilisable


def test_sous_deux_lux_ignores():
    rapport = RapportCapteurs()
    remplir(rapport, [(1, 0)] * 50 + [(1.5, 3)] * 50)
    assert rapport.nombre == 0 and rapport.etat == "apprentissage"


def test_rapport_instable_ecarte():
    """Un capteur extérieur : le rapport à la pièce change avec l'heure."""
    rapport = RapportCapteurs()
    remplir(rapport, [(50, 50 * f) for f in (0.2, 1, 5, 0.5, 2, 10, 0.1) * 6])
    assert rapport.dispersion > DISPERSION_MAX
    assert rapport.etat == "instable" and not rapport.utilisable
    assert rapport.facteur is not None


def test_dispersion_tolere_le_bruit():
    rapport = RapportCapteurs()
    remplir(rapport, [(30 * f, 10) for f in (0.9, 1, 1.1, 1.2, 0.85) * 8])
    assert rapport.dispersion < DISPERSION_MAX and rapport.utilisable
    assert rapport.facteur == pytest.approx(3)


def test_l_un_a_zero_quand_l_autre_depasse_vingt_lux():
    rapport = RapportCapteurs()
    remplir(rapport, [(100, 50)] * 40 + [(100, 0)] * 5)
    assert rapport.zeros() == {"principal": 0, "secours": 5}
    assert rapport.etat == "incoherent" and not rapport.utilisable


def test_fenetre_glissante_et_serialisation():
    rapport = RapportCapteurs()
    remplir(rapport, [(100, 50)] * ECHANTILLONS_MAX + [(100, 25)] * ECHANTILLONS_MAX,
            debut=0)
    assert rapport.facteur == pytest.approx(4)
    relu = RapportCapteurs(rapport.en_liste())
    assert relu.nombre == ECHANTILLONS_MAX and relu.facteur == pytest.approx(4)
    # Les échantillons relus précèdent les nouveaux : la cadence continue.
    assert not relu.noter(rapport.en_liste()[-1][0] + 1, 100, 25)


def test_choix_du_capteur():
    assert choisir(True, True, True) == "principal"
    assert choisir(True, False, False) == "principal"
    assert choisir(False, True, True) == "secours"
    # Facteur pas encore appris, ou rapport instable : rien, luminosité
    # gardée.
    assert choisir(False, True, False) is None
    assert choisir(False, False, True) is None


def test_dispersion_exprimee_en_facteur():
    rapport = RapportCapteurs()
    remplir(rapport, [(30 * f, 10) for f in (0.9, 1, 1.1, 1.2, 0.85) * 8])
    assert rapport.resume()["dispersion"] == pytest.approx(math.exp(rapport.dispersion), abs=0.01)
