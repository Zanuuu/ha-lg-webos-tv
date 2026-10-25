"""Reprise en main (logique pure) : levée de la pause sur changement
d'éclairage, corrections retenues, suggestions de courbe."""

import math

import pytest

from custom_components.lg_webos_tv.courbe import calculer_cible, valider_point_intermediaire
from custom_components.lg_webos_tv.reprise import (CORRECTION_DUREE_S, Correction,
                                                   SuiviCorrection, a_ecarter,
                                                   bornes_reprise, changement_net, ecart,
                                                   plage, suggestions)

DEFAUT = {"lux_min": 5, "lux_max": 300, "luminosite_min": 40, "luminosite_max": 100}
TROIS = {**DEFAUT, "point_intermediaire": [40, 80]}


# ------------------------------------------------------------------ levée
@pytest.mark.parametrize(("depart", "lux", "leve"), [
    (20, 40, True), (20, 10, True), (20, 30, False), (20, 13.4, False),
    (20, 39.7, True), (20, 10.1, True), (20, 39, False), (20, 10.3, False),
])
def test_levee_sur_facteur_deux(depart, lux, leve):
    assert changement_net(lux, lux, depart, DEFAUT) is leve


def test_filtre_et_mesure_retenue_d_accord():
    # Ombre passagère : la mesure a chuté, le filtre ne l'a pas suivie.
    assert not changement_net(18, 8, 20, DEFAUT)
    # Fin d'une transition en cours à la reprise en main : le filtre rejoint
    # la mesure retenue, qui n'a pas bougé.
    assert not changement_net(40, 300, 300, DEFAUT)
    # Sens contraires.
    assert not changement_net(45, 9, 20, DEFAUT)
    assert changement_net(9, 8, 20, DEFAUT)


def test_lux_ramenes_dans_la_plage_de_la_courbe():
    # Sous « Pièce sombre », la courbe est plate : 1 → 3 lx ne change rien.
    assert not changement_net(3, 3, 1, DEFAUT)
    assert not changement_net(9, 9, 1, DEFAUT)
    assert changement_net(10, 10, 1, DEFAUT)
    # Au-delà de « Pièce lumineuse » aussi.
    assert not changement_net(5000, 5000, 400, DEFAUT)
    assert changement_net(140, 140, 400, DEFAUT)


def test_bornes_affichees():
    assert bornes_reprise(20, DEFAUT) == (10, 40)
    # Dans la partie plate, une seule limite est atteignable.
    assert bornes_reprise(3, DEFAUT) == (None, 10)
    assert bornes_reprise(2000, DEFAUT) == (150, None)


# ------------------------------------------------------------ corrections
def suivi(lux=(20,), valeur=70, mode="vivid"):
    s = SuiviCorrection(0, valeur, mode, "manuel", lissage_s=15)
    for i, mesure in enumerate(lux):
        s.mesurer(60 + i, mesure)
    return s


def verdict(s, t=CORRECTION_DUREE_S, valeur=70, mode="vivid", connecte=True, en_pause=True):
    return s.verdict(t, valeur, mode, connecte, en_pause)


def test_correction_retenue_apres_dix_minutes():
    s = suivi(lux=(20, 22, 18))
    assert verdict(s, t=CORRECTION_DUREE_S - 2) == "trop_tot"
    assert verdict(s) is None
    correction = s.correction(CORRECTION_DUREE_S, DEFAUT)
    assert correction.lux == pytest.approx(math.sqrt(18 * 22), abs=0.05)
    assert (correction.valeur, correction.cible, correction.mode_image) == (70, 60, "vivid")


@pytest.mark.parametrize(("arguments", "raison"), [
    ({"valeur": 72}, "valeur_changee"),
    ({"mode": "standard"}, "mode"),
    ({"connecte": False}, "deconnecte"),
    ({"en_pause": False}, "pause_levee"),
])
def test_correction_ecartee(arguments, raison):
    assert verdict(suivi(), **arguments) == raison


def test_lux_instable_ecarte():
    assert verdict(suivi(lux=(20, 31))) == "lux_instable"
    assert verdict(suivi(lux=(20, 29))) is None
    # Plancher à 1 lx : 0 ↔ 1 lx dans le noir reste stable.
    assert verdict(suivi(lux=(0, 1, 0.2))) is None
    assert verdict(suivi(lux=())) == "lux_inconnu"


def test_fin_de_transition_ignoree():
    """Quatre constantes de temps du lissage : la fin d'une transition en
    cours à la reprise en main ne compte pas."""
    s = SuiviCorrection(0, 70, "vivid", "manuel", lissage_s=15)
    s.mesurer(10, 40)
    s.mesurer(59, 250)
    s.mesurer(60, 290)
    s.mesurer(400, 300)
    assert verdict(s) is None
    assert s.lux == pytest.approx(math.sqrt(290 * 300))


# ------------------------------------------------------------ suggestions
def corrections(lux, ecarts, options=DEFAUT, debut=0):
    """Une correction par écart, au lux donné (ou à chacun des lux)."""
    lux = lux if isinstance(lux, list) else [lux] * len(ecarts)
    return [Correction(horodatage=debut + i, lux=l_, valeur=calculer_cible(l_, options) + e,
                       cible=calculer_cible(l_, options), mode_image="vivid",
                       origine="manuel", id=debut + i)
            for i, (l_, e) in enumerate(zip(lux, ecarts, strict=True))]


def test_plages_en_demi_decades():
    assert [plage(v) for v in (0, 1, 3.1, 3.2, 9.9, 10, 31, 32, 100)] == [0, 0, 0, 1, 1, 2, 2, 3, 4]


def test_trois_corrections_au_moins():
    assert suggestions(corrections(2, [8, 8]), DEFAUT) == []
    [s] = suggestions(corrections(2, [8, 8, 8]), DEFAUT)
    assert (s.plage, s.nombre, s.ecart, s.ambiance) == (0, 3, 8, "sombre")


def test_mediane_d_au_moins_cinq_points():
    assert suggestions(corrections(2, [4, 4, 4, 30]), DEFAUT) == []
    assert suggestions(corrections(2, [5, 5, 5]), DEFAUT)[0].ecart == 5


def test_corrections_contradictoires():
    assert suggestions(corrections(2, [8, 8, -8, -8]), DEFAUT) == []
    # Médiane positive, mais seulement deux corrections dans ce sens.
    assert suggestions(corrections(2, [8, 8, 0]), DEFAUT) == []


def test_plages_voisines_ne_se_cumulent_pas():
    assert suggestions(corrections([2.5, 2.8, 4], [8, 8, 8]), DEFAUT) == []


def test_seules_les_dix_plus_recentes_comptent():
    anciennes = corrections(2, [0] * 10)
    recentes = corrections(2, [-10] * 6, debut=100)
    assert suggestions(anciennes + recentes, DEFAUT)[0].ecart == -10


def test_corrections_ecartees_ignorees():
    liste = corrections(2, [8, 8, 8, 8])
    [s] = suggestions(liste, DEFAUT)
    ids = a_ecarter(liste, s.plage)
    assert ids == [c.id for c in liste]
    for c in liste:
        c.ecartee = True
    assert suggestions(liste, DEFAUT) == []


def courbe_valide(options):
    lux = [options["lux_min"], *(options.get("point_intermediaire") or [])[:1], options["lux_max"]]
    assert lux == sorted(lux) and len(set(lux)) == len(lux)
    assert 0 <= options["luminosite_min"] <= options["luminosite_max"] <= 100
    assert valider_point_intermediaire(options)[1] is None
    # Monotone : la cible ne décroît jamais quand le lux augmente.
    cibles = [calculer_cible(10 ** (k / 10), options) for k in range(-10, 60)]
    assert cibles == sorted(cibles)


def test_pas_sur_le_plateau_sombre_releve_la_luminosite_minimale():
    [s] = suggestions(corrections(2, [6, 6, 6, 7]), DEFAUT)
    assert s.points == ["min"] and not s.ajout
    assert s.options == {**DEFAUT, "luminosite_min": 46}
    courbe_valide(s.options)


def test_plateau_lumineux_abaisse_la_luminosite_maximale():
    [s] = suggestions(corrections(1000, [-10, -10, -12]), DEFAUT)
    assert s.points == ["max"] and s.options["luminosite_max"] == 90
    courbe_valide(s.options)


def test_pres_d_une_extremite_seul_ce_point_bouge():
    # 7 lx : premier tiers du segment 5–300 lx.
    [s] = suggestions(corrections(7, [8, 8, 8]), DEFAUT)
    assert s.points == ["min"] and not s.ajout
    assert s.options["lux_min"] == 5 and s.options["lux_max"] == 300
    assert s.options["luminosite_max"] == 100
    assert abs(calculer_cible(7, s.options) - (calculer_cible(7, DEFAUT) + 8)) <= 1
    courbe_valide(s.options)


def test_au_milieu_d_une_courbe_a_deux_points_ajout_du_point_intermediaire():
    [s] = suggestions(corrections(40, [-10, -10, -10]), DEFAUT)
    assert s.ajout and s.points == ["intermediaire"]
    assert s.options["point_intermediaire"] == [40, calculer_cible(40, DEFAUT) - 10]
    assert {k: s.options[k] for k in DEFAUT} == DEFAUT
    assert s.cible == calculer_cible(40, DEFAUT) - 10
    courbe_valide(s.options)


def test_courbe_a_trois_points_le_point_le_plus_proche_bouge():
    # 30 lx : segment 5–40 lx, près du point intermédiaire (40 lx).
    [s] = suggestions(corrections(30, [8, 8, 8], TROIS), TROIS)
    assert s.points == ["intermediaire"] and not s.ajout
    assert s.options["point_intermediaire"][0] == 40
    assert s.options["point_intermediaire"][1] > 80
    assert abs(calculer_cible(30, s.options) - (calculer_cible(30, TROIS) + 8)) <= 1
    assert (s.options["luminosite_min"], s.options["luminosite_max"]) == (40, 100)
    courbe_valide(s.options)


def test_trois_points_au_milieu_d_un_segment_pas_d_ajout():
    # 14 lx : milieu du segment 5–40 lx (en ln) ; pas de quatrième point, le
    # segment monte d'un bloc.
    [s] = suggestions(corrections(14, [8, 8, 8], TROIS), TROIS)
    assert not s.ajout and s.points == ["min", "intermediaire"]
    assert (s.options["luminosite_min"], s.options["point_intermediaire"]) == (48, [40, 88])
    assert s.options["luminosite_max"] == 100
    assert abs(calculer_cible(14, s.options) - (calculer_cible(14, TROIS) + 8)) <= 1
    courbe_valide(s.options)


def test_voisins_pousses_pour_rester_monotone():
    # Plus lumineux que le maximum en pièce intermédiaire : le maximum suit.
    options = {**DEFAUT, "luminosite_max": 70}
    [s] = suggestions(corrections(40, [20, 20, 20], options), options)
    assert s.pousses and s.options["luminosite_max"] >= s.options["point_intermediaire"][1]
    assert s.cible == calculer_cible(40, options) + 20
    courbe_valide(s.options)


def test_luminosite_bornee_a_cent():
    [s] = suggestions(corrections(1000, [5, 5, 5], {**DEFAUT, "luminosite_max": 98}),
                      {**DEFAUT, "luminosite_max": 98})
    assert s.options["luminosite_max"] == 100
    courbe_valide(s.options)
    # Déjà au maximum : rien à proposer.
    assert suggestions(corrections(1000, [5, 5, 5]), DEFAUT) == []


def test_suggestion_appliquee_disparait():
    liste = corrections(2, [8, 8, 8, 9])
    [s] = suggestions(liste, DEFAUT)
    assert suggestions(liste, s.options) == []


def test_ancrages_retires_de_la_courbe_proposee():
    options = {**DEFAUT, "ancrages": [{"lux": 20, "luminosite": 60, "horodatage": "x"}]}
    [s] = suggestions(corrections(2, [8, 8, 8]), options)
    assert "ancrages" not in s.options


def test_lux_au_dixieme_du_point_ajoute():
    [s] = suggestions(corrections([37.33, 37.4, 37.2], [-10, -10, -10]), DEFAUT)
    assert s.options["point_intermediaire"][0] == 37.3


# ------------------------------------------------------------- décalage
def test_ecart_mesure_a_la_courbe_plus_decalage():
    """Avec un décalage de −10, la courbe donnait 50 à 20 lx ; l'utilisateur
    a choisi 53 : la courbe seule est 3 points trop basse… pour ce
    décalage, pas 7 points trop haute."""
    c = Correction(horodatage=0, lux=20, valeur=53, cible=50, mode_image="vivid",
                   origine="manuel", decalage=-10)
    assert ecart(c, DEFAUT) == 3


def test_suggestion_corrige_la_courbe_seule():
    # Trois corrections à 2 lx, +8 au-dessus de la courbe décalée de −10.
    cs = [Correction(horodatage=i, lux=2, valeur=calculer_cible(2, DEFAUT) - 10 + 8, cible=30,
                     mode_image="vivid", origine="manuel", id=i, decalage=-10)
          for i in range(3)]
    [s] = suggestions(cs, DEFAUT)
    assert s.ecart == 8
    # La courbe monte de 8 : avec le même décalage, elle redonne la valeur.
    assert calculer_cible(2, s.options, -10) == cs[0].valeur


def test_correction_retenue_porte_le_decalage():
    s = SuiviCorrection(0, valeur=45, mode_image="vivid", origine="manuel", decalage=-10)
    s.mesurer(400, 20)
    c = s.correction(600, DEFAUT)
    assert (c.decalage, c.cible) == (-10, 50)
