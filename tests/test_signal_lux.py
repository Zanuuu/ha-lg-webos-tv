"""Signal du capteur de lux (signal_lux.py), sans Home Assistant : séries de
mesures horodatées."""

import math

import pytest

from custom_components.lg_webos_tv.signal_lux import (PROFILS, Cadence,
                                                      Constantes, SignalLux,
                                                      constantes, profil)

RAPIDE = PROFILS["rapide"]


def signal(**modifs) -> SignalLux:
    return SignalLux(Constantes(**{**vars(RAPIDE), **modifs}))


def suivre(s: SignalLux, mesures: list[tuple[float, float]], fin: float, pas=1.0):
    """Applique les mesures (instant, lux) et renvoie les instants où la
    décision d'appliquer serait prise, comme l'orchestrateur : évaluation à
    chaque pas, application si hors bande et non gelé, puis gel."""
    applications = []
    mesures = sorted(mesures)
    t = 0.0
    while t <= fin:
        while mesures and mesures[0][0] <= t:
            s.mesurer(*mesures.pop(0))
        if not s.gele(t) and s.hors_bande(t):
            lux = s.lux_filtre(t)
            applications.append((t, lux))
            s.noter_reference(lux)
            s.geler(t)
        t += pas
    return applications


# ------------------------------------------------------------------ filtre

def test_premiere_mesure_sans_retard():
    s = signal()
    s.mesurer(0, 20)
    assert s.lux_filtre(0) == pytest.approx(20)
    assert s.converge(0)


def test_asymetrie_montee_plus_rapide_que_descente():
    montee, descente = signal(), signal()
    for s, depart, arrivee in ((montee, 20, 40), (descente, 40, 20)):
        s.mesurer(0, depart)
        s.mesurer(1, arrivee)
    # Au bout d'une constante de temps, 63 % du chemin (en logarithme).
    ecart = math.log(2)
    assert math.log(montee.lux_filtre(6)) == pytest.approx(math.log(20) + 0.632 * ecart, abs=1e-3)
    assert math.log(descente.lux_filtre(16)) == pytest.approx(math.log(40) - 0.632 * ecart,
                                                              abs=1e-3)
    assert montee.lux_filtre(6) - 20 > 40 - descente.lux_filtre(6)


def test_reevaluation_entre_deux_mesures_independante_du_pas():
    """Un capteur qui ne publie que sur variation : le filtre rejoint la
    mesure sans nouvelle mesure, quel que soit le rythme des évaluations."""
    fin = []
    for pas in (0.1, 1.0, 7.0):
        s = signal()
        s.mesurer(0, 20)
        s.mesurer(0, 35)
        t = 0.0
        while t < 21:
            s.lux_filtre(t)
            t += pas
        fin.append(s.lux_filtre(21))
    assert fin[0] == pytest.approx(fin[1]) == pytest.approx(fin[2])
    s = signal()
    s.mesurer(0, 20)
    s.mesurer(0, 35)
    assert s.prochaine_echeance(0) == 1.0
    assert s.lux_filtre(100) == pytest.approx(35, rel=1e-3)
    assert s.prochaine_echeance(100) is None


@pytest.mark.parametrize("periode", [1, 60, 300])
def test_capteurs_periodiques_rejoignent_la_lumiere(periode):
    s = signal()
    mesures = [(t, 20) for t in range(0, 50, periode)]
    mesures += [(t, 40) for t in range(50, 50 + 6 * periode + 60, periode)]
    suivre(s, mesures, 50 + 6 * periode + 60)
    assert s.lux_filtre(50 + 6 * periode + 60) == pytest.approx(40, rel=0.01)


def test_profil_lent_sans_filtre():
    s = SignalLux(PROFILS["lent"])
    s.mesurer(0, 20)
    s.mesurer(300, 400)
    assert s.lux_filtre(300) == pytest.approx(400)


# -------------------------------------------------------------- hystérésis

def test_bruit_d_un_lux_en_piece_sombre_sans_application():
    s = signal()
    mesures = [(t, 5 + (t % 2) * 0.4) for t in range(0, 600)]
    applications = suivre(s, mesures, 600)
    assert len(applications) == 1  # la première, sans référence


def test_hysteresis_relative_memoire_du_sens():
    s = signal(lissage_montee_s=0, lissage_descente_s=0)
    s.mesurer(0, 100)
    s.noter_reference(100)
    for lux, attendu in ((109, False), (111, True), (81, False), (79, True)):
        s.mesurer(1, lux)
        assert s.hors_bande(1) is attendu, lux


def test_sans_reference_toujours_a_appliquer():
    s = signal()
    s.mesurer(0, 50)
    s.noter_reference(50)
    assert not s.hors_bande(0)
    s.oublier_reference()
    assert s.hors_bande(0)


# ------------------------------------------------------------------- sauts

def test_saut_isole_ecarte():
    s = signal()
    s.mesurer(0, 20)
    s.mesurer(10, 500)  # passage devant une lampe
    assert s.lux_filtre(11) == pytest.approx(20)
    s.mesurer(12, 21)
    assert s.evenements() == ["saut_ecarte"]
    assert s.lux_filtre(40) == pytest.approx(21, rel=1e-3)


def test_saut_confirme_par_une_deuxieme_mesure():
    s = signal()
    s.mesurer(0, 20)
    s.mesurer(10, 300)
    s.mesurer(11, 310)
    # Confirmé à 11 s, sans attendre le délai de 8 s.
    assert s.lux_filtre(12) > 30
    assert s.lux_filtre(60) == pytest.approx(310, rel=1e-2)
    assert s.evenements() == []


def test_saut_confirme_par_le_delai():
    """Capteur sur variation : aucune deuxième mesure ne viendra."""
    s = signal()
    s.mesurer(0, 20)
    s.mesurer(10, 300)
    assert s.prochaine_echeance(10) == 18
    assert s.lux_filtre(17.9) == pytest.approx(20)
    assert s.lux_filtre(18.5) > 20
    assert s.lux_filtre(60) == pytest.approx(300, rel=1e-2)


def test_saut_sans_confirmation_si_le_profil_l_exclut():
    s = signal(confirmation_saut_s=0)
    s.mesurer(0, 20)
    s.mesurer(10, 300)
    assert s.lux_filtre(11) > 20


# --------------------------------------------------------------------- gel

def test_gel_differe_la_derniere_mesure():
    s = signal(lissage_montee_s=0, lissage_descente_s=0)
    s.mesurer(0, 20)
    s.geler(1)
    s.mesurer(2, 30)  # l'écran éclaire le capteur pendant la transition
    s.mesurer(4, 25)
    assert s.lux_filtre(5) == pytest.approx(20)
    assert s.prochaine_echeance(5) == 6
    assert s.lux_filtre(6) == pytest.approx(25)


def test_gel_espace_les_applications():
    """Grand saut : quelques écritures espacées du gel, pas une par seconde."""
    s = signal()
    applications = suivre(s, [(0, 20), (30, 300), (31, 300)], 120)
    instants = [t for t, _ in applications]
    assert 3 <= len(applications) <= 8
    assert all(b - a >= RAPIDE.gel_s for a, b in zip(instants, instants[1:]))
    assert applications[-1][1] == pytest.approx(300, rel=0.1)


def test_flux_rapide_n_affame_pas_l_application():
    """Un capteur à 0,5 s : la décision est prise sans attendre la fin du
    flux (défaut du rebond glissant de la 2.4.0)."""
    s = signal()
    mesures = [(i * 0.5, 20) for i in range(20)] + [(10 + i * 0.5, 40) for i in range(200)]
    applications = suivre(s, mesures, 60, pas=0.5)
    assert any(10 < t < 20 for t, _ in applications)


def test_capteur_indisponible_repart_de_zero():
    s = signal()
    s.mesurer(0, 20)
    s.noter_reference(20)
    s.oublier()
    assert s.lux_filtre(1) is None
    assert not s.hors_bande(1)
    s.mesurer(2, 400)  # pas de saut : aucune valeur de comparaison
    assert s.lux_filtre(2) == pytest.approx(400)
    assert s.hors_bande(2)


# ---------------------------------------------------------------- profils

@pytest.mark.parametrize(("plateforme", "intervalle", "attendu"), [
    ("esphome", None, "inconnu"),
    ("esphome", 2, "rapide"),
    ("esphome", 60, "periodique"),
    ("zha", None, "sur_variation"),
    ("mqtt", 120, "sur_variation"),
    ("mqtt", 1, "rapide"),
    ("zwave_js", None, "lent"),
    ("zwave_js", 3600, "lent"),
    ("hue", 900, "lent"),
    (None, None, "inconnu"),
])
def test_profil(plateforme, intervalle, attendu):
    assert profil(plateforme, intervalle) == attendu


def test_constantes_emplacement_et_options_avancees():
    assert constantes({}, "rapide", "a") == RAPIDE
    assert constantes({}, "rapide", "d").gel_s == 20
    personnalisees = constantes({"lissage_descente_s": 30, "hysteresis_montee": 15,
                                 "gel_ecriture_s": 8}, "sur_variation", "d")
    assert personnalisees.lissage_descente_s == 30
    assert personnalisees.hysteresis_montee == pytest.approx(0.15)
    assert personnalisees.gel_s == 8  # l'option prime sur l'emplacement
    assert personnalisees.lissage_montee_s == 0  # du profil


# ---------------------------------------------------------------- cadence

def test_cadence_intervalle_median():
    cadence = Cadence()
    for t in (0, 60, 120, 180, 240):
        cadence.noter(t)
    assert cadence.intervalle() is None  # 4 intervalles : trop peu
    cadence.noter(300)
    cadence.noter(1000)  # un rapport tardif ne déplace pas la médiane
    assert cadence.intervalle() == 60


def test_capteur_fige_au_dela_de_deux_heures_au_moins():
    cadence = Cadence()
    for t in range(0, 360, 60):
        cadence.noter(t)
    dernier = 300
    assert not cadence.fige(dernier + 3 * 60 + 1)  # 3 × l'intervalle < 2 h
    assert not cadence.fige(dernier + 7200)
    assert cadence.fige(dernier + 7201)


def test_capteur_sur_variation_jamais_fige_sans_intervalle_connu():
    cadence = Cadence()
    cadence.noter(0)
    cadence.noter(5000)
    assert cadence.silence_max() is None
    assert not cadence.fige(10 ** 6)
