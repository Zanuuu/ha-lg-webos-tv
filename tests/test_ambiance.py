"""Ambiance de la pièce (entité « Ambiance ») : seuils tirés de la courbe ou
figés, hystérésis et durée minimale."""

import pytest

from custom_components.lg_webos_tv.ambiance import (DUREE_MIN_S, HYSTERESIS,
                                                    SuiviAmbiance, nommer,
                                                    seuils, seuils_courbe)

COURBE = {"lux_min": 5, "lux_max": 300}
# Tiers de ln(5)…ln(300) : 19,57 et 76,63 lx.
SEUILS = seuils_courbe(COURBE)


def test_seuils_tires_de_la_courbe_ou_figes():
    assert SEUILS == pytest.approx((19.574, 76.631), abs=1e-3)
    # Ils suivent la courbe (ancrage, suggestion)…
    assert seuils({"lux_min": 10, "lux_max": 600}) == pytest.approx((39.15, 153.26), abs=0.01)
    # … sauf s'ils sont figés, un seul ou les deux.
    assert seuils({**COURBE, "ambiance_claire": 200}) == pytest.approx((SEUILS[0], 200))
    assert seuils({**COURBE, "ambiance_sombre": 10, "ambiance_claire": 150}) == (10, 150)


def test_nommer_sans_hysteresis():
    assert [nommer(lux, SEUILS) for lux in (0, 5, 19.5, 19.6, 76.6, 76.7, 1000)] == [
        "sombre", "sombre", "sombre", "intermediaire", "intermediaire", "claire", "claire"]


def test_premiere_valeur_immediate():
    suivi = SuiviAmbiance()
    assert suivi.mesurer(0, 40, SEUILS)
    assert (suivi.valeur, suivi.depuis, suivi.echeance) == ("intermediaire", 0, None)


def test_dix_minutes_avant_de_changer():
    suivi = SuiviAmbiance()
    suivi.mesurer(0, 40, SEUILS)
    assert not suivi.mesurer(100, 300, SEUILS)
    assert suivi.valeur == "intermediaire" and suivi.echeance == 100 + DUREE_MIN_S
    assert not suivi.mesurer(100 + DUREE_MIN_S - 2, 300, SEUILS)
    # Échéance atteinte sans nouvelle mesure du capteur : le même lux,
    # présenté par la minuterie de la fonction.
    assert suivi.mesurer(100 + DUREE_MIN_S, 300, SEUILS)
    assert (suivi.valeur, suivi.depuis, suivi.echeance) == ("claire", 100 + DUREE_MIN_S, None)


def test_retour_avant_dix_minutes_annule():
    suivi = SuiviAmbiance()
    suivi.mesurer(0, 40, SEUILS)
    suivi.mesurer(100, 300, SEUILS)
    assert not suivi.mesurer(400, 40, SEUILS)
    assert suivi.echeance is None
    # La lampe rallumée : les 10 minutes repartent.
    suivi.mesurer(500, 300, SEUILS)
    assert not suivi.mesurer(500 + DUREE_MIN_S - 2, 300, SEUILS)
    assert suivi.mesurer(500 + DUREE_MIN_S, 300, SEUILS)


def test_hysteresis_autour_du_seuil():
    suivi = SuiviAmbiance()
    suivi.mesurer(0, 40, SEUILS)
    juste_au_dessus = SEUILS[1] * 1.1
    assert not suivi.mesurer(10, juste_au_dessus, SEUILS)
    assert suivi.echeance is None
    assert not suivi.mesurer(20, SEUILS[1] * HYSTERESIS, SEUILS)
    assert suivi.echeance == 20 + DUREE_MIN_S
    suivi.mesurer(20 + DUREE_MIN_S, SEUILS[1] * HYSTERESIS, SEUILS)
    assert suivi.valeur == "claire"
    # Redescendre juste sous le seuil ne suffit pas non plus.
    assert not suivi.mesurer(2000, SEUILS[1] * 0.9, SEUILS)
    assert suivi.echeance is None


def test_saut_de_deux_ambiances():
    suivi = SuiviAmbiance()
    suivi.mesurer(0, 2, SEUILS)
    suivi.mesurer(10, 1000, SEUILS)
    suivi.mesurer(10 + DUREE_MIN_S, 1000, SEUILS)
    assert suivi.valeur == "claire"


def test_restauree_tient_jusqu_a_preuve_du_contraire():
    suivi = SuiviAmbiance()
    suivi.mesurer(0, 300, SEUILS)
    # L'entité restaure l'ambiance d'avant le redémarrage, après la
    # première mesure : elle la remplace, sans changement d'état parasite.
    suivi.restaurer("intermediaire", -50)
    assert (suivi.valeur, suivi.depuis) == ("intermediaire", -50)
    assert not suivi.mesurer(1, 300, SEUILS)
    assert suivi.mesurer(1 + DUREE_MIN_S, 300, SEUILS)
    suivi.restaurer("inconnue", 0)
    assert suivi.valeur == "claire"
