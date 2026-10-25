"""Courbe de la luminosité adaptative (courbe.py) : point intermédiaire,
vecteurs partagés avec le panneau, point d'ancrage à un et deux points."""

import json
import math
import random
from pathlib import Path

import pytest

from custom_components.lg_webos_tv.courbe import (ancrer, calculer_cible,
                                                  conserver_ancrages)
from custom_components.lg_webos_tv.luminosite_adaptative import valider_options

VECTEURS = json.loads((Path(__file__).parent / "vecteurs_courbe.json").read_text())
DEFAUT = {"lux_min": 5, "lux_max": 300, "luminosite_min": 40, "luminosite_max": 100}
TROIS = {**DEFAUT, "point_intermediaire": [40, 80]}
HORODATAGE = "2026-10-25T20:00:00+00:00"


@pytest.mark.parametrize("cas", VECTEURS["cibles"], ids=lambda cas: cas["nom"])
def test_vecteurs_de_cible(cas):
    assert calculer_cible(cas["lux"], cas["options"], cas.get("decalage", 0)) == cas["cible"]


@pytest.mark.parametrize("cas", VECTEURS["validation"], ids=lambda cas: cas["nom"])
def test_vecteurs_de_validation(cas):
    _, erreurs = valider_options(cas["options"], [])
    assert sorted(erreurs) == cas["erreurs"]


def test_point_intermediaire_normalise_et_retire():
    options = {**DEFAUT, "pause": 120, "modes_exclus": []}
    valides, _ = valider_options({**options, "point_intermediaire": [40.0, 80.0]}, [])
    assert valides["point_intermediaire"] == [40.0, 80] and isinstance(
        valides["point_intermediaire"][1], int)
    valides, _ = valider_options({**options, "point_intermediaire": None}, [])
    assert "point_intermediaire" not in valides


def ancien_calcul(lux, options):
    """Calcul de la 2.7.0 : une droite sur ln(lux) entre les extrémités."""
    t = ((math.log(max(lux, 1)) - math.log(options["lux_min"]))
         / (math.log(options["lux_max"]) - math.log(options["lux_min"])))
    t = min(max(t, 0), 1)
    bas, haut = options["luminosite_min"], options["luminosite_max"]
    return int(math.floor(bas + t * (haut - bas) + 0.5))


def balayage():
    return [10 ** (i / 50) for i in range(-50, 276)]


def test_deux_points_identiques_a_la_2_7_0():
    for options in (DEFAUT, {"lux_min": 1, "lux_max": 100000, "luminosite_min": 0,
                             "luminosite_max": 100}):
        assert all(calculer_cible(lux, options) == ancien_calcul(lux, options)
                   for lux in balayage())


@pytest.mark.parametrize("options", [TROIS, {**DEFAUT, "point_intermediaire": [40, 40]},
                                     {**DEFAUT, "point_intermediaire": [10, 95]}])
def test_trois_points_monotone_et_bornee(options):
    cibles = [calculer_cible(lux, options) for lux in balayage()]
    assert cibles == sorted(cibles)
    assert min(cibles) == options["luminosite_min"]
    assert max(cibles) == options["luminosite_max"]
    lux, valeur = options["point_intermediaire"]
    assert calculer_cible(lux, options) == valeur


# ------------------------------------------------------------------ ancrage
def position(options):
    """Position du point intermédiaire entre les extrémités, en ln(lux)."""
    return (math.log(options["point_intermediaire"][0] / options["lux_min"])
            / math.log(options["lux_max"] / options["lux_min"]))


def test_un_point_decale_la_courbe_en_gardant_la_pente():
    options, ancrages, compte_rendu = ancrer(DEFAUT, None, 20, 70, HORODATAGE)
    assert calculer_cible(20, options) == 70
    # Mêmes luminosités, même rapport entre les lux des extrémités.
    assert (options["luminosite_min"], options["luminosite_max"]) == (40, 100)
    assert options["lux_max"] / options["lux_min"] == pytest.approx(60, rel=0.1)
    assert ancrages == [{"lux": 20, "luminosite": 70, "horodatage": HORODATAGE}]
    assert compte_rendu == {"points": 1, "borne_etendue": None, "coupee": False,
                            "approche": False, "remplace": False, "ancien_oublie": False,
                            "cible": 70}


def test_un_point_deplace_aussi_le_point_intermediaire():
    options, _, _ = ancrer(TROIS, None, 100, 70, HORODATAGE)
    assert calculer_cible(100, options) == 70
    assert options["point_intermediaire"][1] == 80
    assert position(options) == pytest.approx(position(TROIS), abs=0.02)


def test_un_point_dans_la_partie_plate_ne_change_rien():
    options, _, compte_rendu = ancrer(DEFAUT, None, 3, 40, HORODATAGE)
    assert {cle: options[cle] for cle in DEFAUT} == DEFAUT
    assert compte_rendu["borne_etendue"] is None


def test_borne_etendue_sans_deplacement_dans_le_noir():
    options, _, compte_rendu = ancrer(DEFAUT, None, 3, 30, HORODATAGE)
    assert options == {**DEFAUT, "luminosite_min": 30}
    assert compte_rendu["borne_etendue"] == "min"


def test_borne_etendue_puis_courbe_decalee():
    # 30 voulu à 50 lx : pièce sombre et luminosité minimale s'y placent,
    # la pièce lumineuse suit (même rapport de lux).
    options, _, _ = ancrer(DEFAUT, None, 50, 30, HORODATAGE)
    assert options == {"lux_min": 50, "lux_max": 3000, "luminosite_min": 30,
                       "luminosite_max": 100}
    assert all(isinstance(options[cle], int) for cle in ("lux_min", "lux_max"))
    options, _, compte_rendu = ancrer(DEFAUT, None, 200, 100, HORODATAGE)
    assert (options["lux_max"], options["luminosite_max"]) == (200, 100)
    assert compte_rendu["borne_etendue"] is None


def test_partie_sous_1_lx_coupee():
    options, _, compte_rendu = ancrer(DEFAUT, None, 1, 70, HORODATAGE)
    assert compte_rendu["coupee"] and not compte_rendu["approche"]
    assert (options["lux_min"], options["luminosite_min"]) == (1, 70)
    # Pour tout lux mesurable : la courbe décalée, intacte.
    decalage = math.sqrt(5 * 300)
    for lux in (2, 10, 7.75):
        attendu = 40 + 60 * min(math.log(lux * decalage / 5) / math.log(60), 1)
        assert abs(calculer_cible(lux, options) - attendu) <= 1


def test_partie_au_dela_du_plafond_coupee():
    large = {"lux_min": 1, "lux_max": 10000, "luminosite_min": 40, "luminosite_max": 100}
    options, _, compte_rendu = ancrer(large, None, 90000, 90, HORODATAGE)
    assert compte_rendu["coupee"]
    assert options["lux_max"] == 100000 and options["luminosite_max"] < 100
    assert calculer_cible(90000, options) == 90


def test_piece_sombre_ramenee_sous_sa_borne():
    options, _, compte_rendu = ancrer(DEFAUT, None, 50000, 50, HORODATAGE)
    assert compte_rendu["approche"] and options["lux_min"] == 1000


def test_deux_points_calent_la_pente():
    options, ancrages, _ = ancrer(DEFAUT, None, 200, 85, HORODATAGE)
    options, ancrages, compte_rendu = ancrer(options, ancrages, 2, 45, HORODATAGE)
    assert compte_rendu["points"] == 2 and len(ancrages) == 2
    assert calculer_cible(200, options) == pytest.approx(85, abs=1)
    assert calculer_cible(2, options) == pytest.approx(45, abs=1)
    assert [a["lux"] for a in ancrages] == [2, 200]


def test_deux_points_et_point_intermediaire():
    options, ancrages, _ = ancrer(TROIS, None, 300, 90, HORODATAGE)
    options, _, compte_rendu = ancrer(options, ancrages, 10, 60, HORODATAGE)
    assert compte_rendu["points"] == 2 and not compte_rendu["coupee"]
    assert calculer_cible(300, options) == pytest.approx(90, abs=1)
    assert calculer_cible(10, options) == pytest.approx(60, abs=1)
    assert position(options) == pytest.approx(position(TROIS), abs=0.02)


def test_ambiance_voisine_remplace_l_ancrage():
    options, ancrages, _ = ancrer(DEFAUT, None, 200, 85, HORODATAGE)
    options, ancrages, compte_rendu = ancrer(options, ancrages, 100, 80, HORODATAGE)
    assert compte_rendu["points"] == 1 and compte_rendu["remplace"]
    assert [a["lux"] for a in ancrages] == [100]


def test_point_incoherent_seul_le_nouveau_retenu():
    options, ancrages, _ = ancrer(DEFAUT, None, 200, 70, HORODATAGE)
    options, ancrages, compte_rendu = ancrer(options, ancrages, 2, 75, HORODATAGE)
    assert compte_rendu["points"] == 1 and compte_rendu["ancien_oublie"]
    assert ancrages == [{"lux": 2, "luminosite": 75, "horodatage": HORODATAGE}]
    assert calculer_cible(2, options) == 75


def test_troisieme_ancrage_remplace_le_plus_proche():
    options, ancrages, _ = ancrer(DEFAUT, None, 200, 85, HORODATAGE)
    options, ancrages, _ = ancrer(options, ancrages, 2, 45, HORODATAGE)
    options, ancrages, compte_rendu = ancrer(options, ancrages, 1000, 95, HORODATAGE)
    assert compte_rendu["points"] == 2 and compte_rendu["remplace"]
    assert [a["lux"] for a in ancrages] == [2, 1000]


@pytest.mark.parametrize("depart", [DEFAUT, TROIS])
def test_ancrage_respecte_a_un_point_pres(depart):
    hasard = random.Random(4)
    for _ in range(300):
        lux = 10 ** hasard.uniform(0, 4.3)
        valeur = hasard.randint(0, 100)
        options, ancrages, compte_rendu = ancrer(depart, None, lux, valeur, HORODATAGE)
        if not compte_rendu["approche"]:
            assert abs(calculer_cible(lux, options) - valeur) <= 1, (lux, valeur, options)
        # Second point dans une autre ambiance, cohérent avec le premier.
        lux2 = lux / hasard.uniform(5, 50)
        valeur2 = hasard.randint(0, valeur - 1) if valeur > 0 else None
        if valeur2 is None:
            continue
        options, _, compte_rendu = ancrer(options, ancrages, lux2, valeur2, HORODATAGE)
        if not compte_rendu["approche"]:
            assert abs(calculer_cible(lux2, options) - valeur2) <= 1
            if compte_rendu["points"] == 2:
                assert abs(calculer_cible(lux, options) - valeur) <= 1
        cibles = [calculer_cible(lx, options) for lx in balayage()]
        assert cibles == sorted(cibles)


def test_ancrages_conserves_tant_que_la_courbe_ne_change_pas():
    ancrages = [{"lux": 20, "luminosite": 70, "horodatage": HORODATAGE}]
    anciennes = {**TROIS, "pause": 120, "ancrages": ancrages}
    assert conserver_ancrages(anciennes, {**TROIS, "pause": 60})["ancrages"] == ancrages
    assert conserver_ancrages(anciennes, {**TROIS, "point_intermediaire": (40, 80)})[
        "ancrages"] == ancrages
    assert "ancrages" not in conserver_ancrages(anciennes, {**TROIS, "lux_min": 6})
    assert "ancrages" not in conserver_ancrages(anciennes, DEFAUT)
    # Les ancrages ne viennent jamais de la saisie.
    assert "ancrages" not in conserver_ancrages(DEFAUT, {**DEFAUT, "ancrages": ancrages})
