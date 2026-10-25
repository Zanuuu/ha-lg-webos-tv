"""Santé de l'installation : statistiques et diagnostics sur séries
synthétiques horodatées, sans Home Assistant (logique pure, sante.py)."""

import math

import pytest

from custom_components.lg_webos_tv.const import (CONF_EMPLACEMENT, CONF_LUX_MAX,
                                                 CONF_LUX_MIN,
                                                 OPTIONS_LUMINOSITE_DEFAUT)
from custom_components.lg_webos_tv.sante import (
    Accumulateur, Contexte, Inversions, Retroaction, StatsJour, arrondi,
    centile_lux, evaluer, part_au_dessus, resume, tranche_lux)
from custom_components.lg_webos_tv.signal_lux import PROFILS

JOUR = "2026-10-25"


def contexte(**options) -> Contexte:
    autres = {cle: options.pop(cle) for cle in list(options)
              if cle in ("profil", "plateforme", "conflit", "fige", "ecriture_possible",
                         "piece_capteur", "piece_televiseur", "secours")}
    return Contexte(options={**OPTIONS_LUMINOSITE_DEFAUT, **options},
                    constantes=PROFILS["rapide"], **{"profil": "rapide", **autres})


def diagnostic(jours, id_, **options):
    return next(d for d in evaluer(jours, JOUR, contexte(**options)) if d.id == id_)


def serie(valeurs, pas_s, jour=JOUR, allume=True, actif=True) -> StatsJour:
    """Un rapport du capteur toutes les `pas_s` secondes, chacun suivi d'un
    échantillon de l'état ; le lux filtré vaut le brut."""
    accumulateur = Accumulateur(StatsJour(jour))
    for i, lux in enumerate(valeurs):
        t = i * pas_s
        accumulateur.rapport(t, lux, allume)
        accumulateur.echantillon(t, jour, allume, actif, lux, lux)
    return accumulateur.stats


def heures(lux, nb_heures, jour=JOUR, **etat) -> StatsJour:
    """`nb_heures` à lux constant, un rapport par minute."""
    return serie([lux] * (int(nb_heures * 60) + 1), 60, jour, **etat)


# -------------------------------------------------------------- outils
def test_tranches_et_centiles():
    assert tranche_lux(0) == tranche_lux(0.5) == 0
    assert tranche_lux(1) == 1
    assert tranche_lux(300) == 1 + int(10 * math.log10(300))
    histogramme = [0.0] * 60
    histogramme[tranche_lux(100)] = 1.0
    # Au milieu (logarithmique) de la tranche [100 ; 125,9[.
    assert centile_lux(histogramme, 0.5) == pytest.approx(100 * 10 ** 0.05, rel=1e-6)
    assert part_au_dessus(histogramme, 10) == 1
    assert part_au_dessus(histogramme, 1000) == 0
    assert centile_lux([0.0] * 60, 0.5) is None


def test_arrondi():
    assert arrondi(3177.4) == 3200
    assert arrondi(4.96) == 5.0
    assert arrondi(2.54) == 2.5


# ------------------------------------------------------------ agrégats
def test_temps_attribue_a_l_etat_precedent():
    accumulateur = Accumulateur(StatsJour(JOUR))
    accumulateur.echantillon(0, JOUR, True, True, 20, 20)
    accumulateur.echantillon(600, JOUR, True, False, 20, 20)  # 10 min actives
    accumulateur.echantillon(900, JOUR, False, False, None, None)  # 5 min allumée
    accumulateur.echantillon(2000, JOUR, False, False, None, None)
    stats = accumulateur.stats
    assert (stats.allume_s, stats.actif_s) == (900, 600)
    assert stats.lux_actif[tranche_lux(20)] == 600


def test_changement_de_jour_rend_le_jour_fini():
    accumulateur = Accumulateur(StatsJour("2026-10-24"))
    accumulateur.echantillon(0, "2026-10-24", True, True, 10, 10)
    fini = accumulateur.echantillon(60, JOUR, True, True, 10, 10)
    assert fini.jour == "2026-10-24" and fini.actif_s == 60
    assert accumulateur.stats.jour == JOUR and accumulateur.stats.actif_s == 0
    accumulateur.echantillon(120, JOUR, True, True, 10, 10)
    assert accumulateur.stats.actif_s == 60


def test_intervalles_seulement_televiseur_allume():
    accumulateur = Accumulateur(StatsJour(JOUR))
    for t in (0, 30, 60):
        accumulateur.rapport(t, 10, allume=False)
    for t in (90, 120, 150):
        accumulateur.rapport(t, 10, allume=True)
    assert accumulateur.stats.rapports == 3
    # L'intervalle 60 → 90 commence téléviseur éteint : écarté.
    assert sum(accumulateur.stats.intervalles) == 2


def test_json_aller_retour_tolere_les_champs_inconnus():
    stats = serie([3, 4, 3, 1000], 60)
    stats.tv = [["allumage", 5, 11]]
    donnees = stats.en_dict()
    assert StatsJour.depuis_dict(donnees) == stats
    plus_tard = {**donnees, "champ_futur": 1, "lux_actif": [0] * 3}
    del plus_tard["rampes"]
    relu = StatsJour.depuis_dict(plus_tard)
    assert relu.rampes == [] and relu.lux_actif == StatsJour(JOUR).lux_actif
    assert relu.vmax == 1000


def test_fusion_d_un_jour_relu_et_du_jour_commence():
    relu = serie([5, 1000, 1000], 60)
    commence = serie([5, 6, 800], 60)
    relu.tv, commence.tv = [["allumage", 5, 11]], [["extinction", 11, 5]]
    relu.fusionner(commence)
    assert relu.rapports == 6
    assert (relu.vmax, relu.vmax_rapports) == (1000, 2)
    assert relu.sombre_pas_min == 1
    assert len(relu.tv) == 2
    autre = serie([2000], 60)
    relu.fusionner(autre)
    assert (relu.vmax, relu.vmax_rapports) == (2000, 1)


# ---------------------------------------------------------- diagnostics
def test_fenetre_de_sept_jours():
    ancien = heures(0, 4, jour="2026-10-18")
    assert diagnostic([ancien], "plancher").niveau == "attente"
    recent = heures(0, 4, jour="2026-10-19")
    assert diagnostic([recent], "plancher").niveau == "info"


def test_conflit_et_capteur_fige_bloquants():
    jours = [StatsJour(JOUR)]
    assert diagnostic(jours, "conflit").niveau == "ok"
    assert diagnostic(jours, "conflit", conflit="economie_energie").niveau == "bloquant"
    assert diagnostic(jours, "capteur_fige", fige=True).niveau == "bloquant"


def test_capteur_trop_lent():
    lent = serie([10] * 25, 720)
    d = diagnostic([lent], "capteur_lent", plateforme="zwave_js")
    assert d.niveau == "avertissement" and d.valeurs["intervalle_s"] == 720
    assert diagnostic([serie([10] * 25, 5)], "capteur_lent").niveau == "ok"
    assert diagnostic([serie([10] * 10, 720)], "capteur_lent").niveau == "attente"


def test_capteur_sur_variation_seulement_informe():
    """Une pièce stable ne fait rien publier à un capteur Zigbee sur
    variation : un long intervalle n'y prouve pas la lenteur."""
    d = diagnostic([serie([10] * 25, 720)], "capteur_lent", plateforme="zha")
    assert d.niveau == "info" and d.valeurs["sur_variation"]


def test_capteur_grossier_en_piece_sombre():
    valeurs = [2, 3] * 15  # entiers, pas de 1 lx autour de 2,5 lx
    d = diagnostic([serie(valeurs, 60)], "capteur_grossier", lux_min=1)
    assert d.niveau == "avertissement"
    assert d.valeurs["pas"] == 1 and d.valeurs["entiers"]
    assert d.proposition == {CONF_LUX_MIN: 5}


def test_pas_grossier_sans_effet_sous_piece_sombre():
    """Sous « Pièce sombre » (5 lx par défaut) la courbe est plate : un pas
    de 1 lx n'y change rien."""
    d = diagnostic([serie([2, 3] * 15, 60)], "capteur_grossier")
    assert d.niveau == "ok" and d.valeurs["reference"] == 5
    fin = diagnostic([serie([2.1, 2.2] * 15, 60)], "capteur_grossier", lux_min=1)
    assert fin.niveau == "ok" and not fin.valeurs["entiers"]
    assert diagnostic([serie([2, 3] * 5, 60)], "capteur_grossier").niveau == "attente"


def test_plafond_du_capteur():
    jours = [serie([1000] * 30, 60, jour=jour) for jour in ("2026-10-24", JOUR)]
    d = diagnostic(jours, "plafond")
    # Au-delà de « Pièce lumineuse » (300 lx), sans effet sur la luminosité.
    assert d.niveau == "info" and d.valeurs["vmax"] == 1000
    assert diagnostic(jours, "plafond", lux_max=2000).niveau == "avertissement"
    # Valeurs qui fluctuent près du maximum : pas un plafond.
    variees = [serie([900, 950, 1000, 980] * 8, 60, jour=jour) for jour in ("2026-10-24", JOUR)]
    assert diagnostic(variees, "plafond").niveau == "ok"
    # Un seul jour : pas assez.
    assert diagnostic(jours[1:], "plafond").niveau == "ok"


def test_plancher_a_zero():
    assert diagnostic([heures(0, 4)], "plancher").niveau == "info"
    assert diagnostic([heures(5, 4)], "plancher").niveau == "ok"
    assert diagnostic([heures(0, 2)], "plancher").niveau == "attente"


def _repartis(debut, fin, nb_heures, jour=JOUR):
    """Lux réparti uniformément en logarithme entre `debut` et `fin`."""
    n = int(nb_heures * 60)
    return serie([debut * (fin / debut) ** (i / (n - 1)) for i in range(n + 1)], 60, jour)


def test_courbe_calee_trop_bas_et_correction():
    jour = _repartis(400, 4000, 12)
    d = diagnostic([jour], "courbe")
    assert d.niveau == "avertissement" and d.valeurs["borne"] == "haute"
    assert d.valeurs["part_haute"] > 0.8
    # 90ᵉ centile : 400 × 10^0,9 ≈ 3 177 lx.
    assert d.proposition == {CONF_LUX_MAX: 3200}
    # Proposition appliquée : le diagnostic disparaît aussitôt.
    assert diagnostic([jour], "courbe", lux_max=3200).niveau == "ok"


def test_courbe_lumiere_constante_sans_proposition():
    d = diagnostic([heures(1000, 12)], "courbe")
    assert d.niveau == "avertissement" and d.proposition is None


def test_courbe_a_la_borne_basse_informe_seulement():
    d = diagnostic([heures(2, 12)], "courbe")
    assert d.niveau == "info" and d.valeurs["borne"] == "basse"
    assert d.proposition is None and d.valeurs["luminosite_min"] == 40
    assert diagnostic([heures(2, 8)], "courbe").niveau == "attente"


def test_inversions_et_episodes():
    inversions = Inversions()
    sens = [1, -1, 1, -1]
    resultats = [inversions.transition(t, s) for t, s in zip((0, 120, 240, 360), sens)]
    assert resultats == [(False, False), (True, False), (True, False), (True, True)]
    espacees = Inversions()
    resultats = [espacees.transition(t, s) for t, s in zip((0, 400, 800, 1200), sens)]
    assert [episode for _, episode in resultats] == [False] * 4


def test_allers_retours():
    jour = StatsJour(JOUR, allers_retours=3, inversions=9)
    d = diagnostic([jour], "allers_retours")
    assert d.niveau == "avertissement"
    assert d.proposition == {"hysteresis_montee": 20, "hysteresis_descente": 30,
                             "lissage_descente_s": 30}
    assert diagnostic([StatsJour(JOUR, allers_retours=2)], "allers_retours").niveau == "ok"


# ----------------------------------------------------------- rétroaction
def cycles_televiseur(retroaction, lux_eteint, lux_allume, nombre, pas_s=5,
                      eteint_s=600, allume_s=1200, perturbations=None):
    """Alternance téléviseur éteint / allumé, rapports du capteur toutes les
    `pas_s` ; `perturbations` : {n° de cycle: lux ajouté par une lampe à
    partir de l'allumage (> 0) ou de l'extinction (< 0 en indice)}."""
    perturbations = perturbations or {}
    resultats = []
    t = 0.0
    retroaction.televiseur(t, False)
    lampe = 0
    for cycle in range(nombre):
        for etape, (duree, allume) in enumerate(((eteint_s, False), (allume_s, True))):
            if etape == 1:
                retroaction.televiseur(t, True)
                lampe += perturbations.get(cycle, 0)
            for _ in range(int(duree / pas_s)):
                retroaction.rapport(t, (lux_allume if allume else lux_eteint) + lampe)
                resultats += retroaction.resoudre(t)
                t += pas_s
        retroaction.televiseur(t, False)
        lampe += perturbations.get(-cycle - 1, 0)
    for _ in range(int(300 / pas_s)):
        retroaction.rapport(t, lux_eteint + lampe)
        resultats += retroaction.resoudre(t)
        t += pas_s
    return resultats


def jour_tv(resultats) -> StatsJour:
    stats = StatsJour(JOUR)
    stats.tv = [valeur for nature, valeur in resultats if nature == "tv"]
    stats.rampes = [valeur for nature, valeur in resultats if nature == "rampe"]
    return stats


def test_retroaction_a_chaque_allumage():
    """Capteur face à l'écran : +6 lx à chaque allumage dans une pièce à
    5 lx."""
    resultats = cycles_televiseur(Retroaction(), 5, 11, 3)
    assert [valeur[0] for _, valeur in resultats] == ["allumage", "extinction"] * 3
    d = diagnostic([jour_tv(resultats)], "retroaction")
    assert d.niveau == "avertissement"
    assert d.valeurs["delta_lx"] == 6 and d.valeurs["part"] == pytest.approx(6 / 11, abs=1e-3)


def test_pas_de_fausse_alerte_sur_un_changement_d_eclairage():
    """Une lampe allumée en même temps que le téléviseur, une autre juste
    après l'extinction : la médiane les écarte."""
    resultats = cycles_televiseur(Retroaction(), 5, 5, 3, perturbations={1: 40, -3: 30})
    d = diagnostic([jour_tv(resultats)], "retroaction")
    assert d.valeurs["evenements"] >= 5
    assert d.niveau == "ok" and d.valeurs["delta_lx"] == 0


def test_retroaction_en_observation_sous_cinq_evenements():
    resultats = cycles_televiseur(Retroaction(), 5, 11, 2)
    d = diagnostic([jour_tv(resultats)], "retroaction")
    assert d.niveau == "attente" and d.valeurs["progression"] == [4, 5]


def test_piece_claire_ignoree():
    resultats = cycles_televiseur(Retroaction(), 200, 206, 3)
    assert diagnostic([jour_tv(resultats)], "retroaction").valeurs["evenements"] == 0


def test_redemarrage_et_coupure_breve_sans_evenement():
    retroaction = Retroaction()
    # Démarrage de Home Assistant, téléviseur déjà allumé.
    retroaction.televiseur(0, True)
    for t in range(0, 300, 5):
        retroaction.rapport(t, 11)
    assert retroaction.resoudre(300) == []
    # Coupure réseau d'une minute : ni extinction ni allumage.
    retroaction.televiseur(300, False)
    retroaction.televiseur(360, True)
    for t in range(360, 700, 5):
        retroaction.rapport(t, 11)
    assert retroaction.resoudre(700) == []


def test_capteur_trop_lent_pour_conclure():
    resultats = cycles_televiseur(Retroaction(), 5, 11, 3, pas_s=300)
    assert [r for r in resultats if r[0] == "tv"] == []


def test_reponse_aux_rampes():
    retroaction = Retroaction()
    resultats = []
    for i in range(5):
        t0 = i * 1000
        # Rampe de +10 points ; le capteur passe de 10 à 11 lx une fois
        # stabilisé (+10 %).
        retroaction.rampe(t0, 10, 10, gel_s=5)
        for t in range(t0, t0 + 60, 2):
            retroaction.rapport(t, 11)
        resultats += retroaction.resoudre(t0 + 60)
    assert resultats == [("rampe", 0.1)] * 5
    d = diagnostic([jour_tv(resultats)], "retroaction")
    assert d.niveau == "avertissement" and d.valeurs["r10"] == 0.1
    # Une reprise en main pendant la fenêtre l'écarte.
    retroaction.rampe(9000, 10, 10, gel_s=5)
    retroaction.perturbation(9010)
    for t in range(9000, 9060, 2):
        retroaction.rapport(t, 11)
    assert retroaction.resoudre(9060) == []


def test_emplacement_d_declare():
    vide = [StatsJour(JOUR)]
    d = diagnostic(vide, "retroaction", **{CONF_EMPLACEMENT: "d"})
    assert d.niveau == "avertissement" and d.valeurs["emplacement_d"]
    sans = jour_tv(cycles_televiseur(Retroaction(), 5, 5, 3))
    assert diagnostic([sans], "retroaction", **{CONF_EMPLACEMENT: "d"}).niveau == "info"


# ---------------------------------------------------------- utilisation
def test_pauses_frequentes():
    accumulateur = Accumulateur(StatsJour(JOUR))
    for _ in range(6):
        accumulateur.reprise("sombre", 8)
    accumulateur.reprise("claire", -4)
    # Deuxième appui sur la télécommande pendant la même pause.
    accumulateur.corriger_reprise("claire", -2)
    accumulateur.pause_manuelle()
    d = diagnostic([accumulateur.stats], "pauses_frequentes")
    assert d.niveau == "info" and d.valeurs["reprises"] == 7
    assert (d.valeurs["ambiance"], d.valeurs["correction_moyenne"]) == ("sombre", 8)
    assert d.valeurs["par_ambiance"]["claire"]["correction_moyenne"] == -6
    assert d.valeurs["pauses_manuelles"] == 1
    moins = StatsJour(JOUR, reprises={"sombre": [6, 48], "intermediaire": [0, 0],
                                      "claire": [0, 0]})
    assert diagnostic([moins], "pauses_frequentes").niveau == "ok"


def test_ecritures_refusees():
    assert diagnostic([StatsJour(JOUR, transitions=10, non_confirmees=3)],
                      "ecritures_refusees").niveau == "avertissement"
    assert diagnostic([StatsJour(JOUR, transitions=100, non_confirmees=3)],
                      "ecritures_refusees").niveau == "ok"


def test_pieces_differentes():
    jours = [StatsJour(JOUR)]
    d = diagnostic(jours, "pieces_differentes", piece_capteur="Bureau",
                   piece_televiseur="Salon")
    assert d.niveau == "info" and d.valeurs == {"capteur": "Bureau", "televiseur": "Salon"}
    assert diagnostic(jours, "pieces_differentes", piece_capteur="Salon",
                      piece_televiseur="Salon").niveau == "ok"
    assert "pieces_differentes" not in [d.id for d in evaluer(jours, JOUR, contexte())]


def test_resume_des_sept_jours():
    jours = [_repartis(10, 100, 2, jour="2026-10-24"), heures(5, 1)]
    jours[1].transitions = 4
    statistiques = resume(jours, JOUR)
    assert statistiques["jours"] == 2 and statistiques["depuis"] == "2026-10-24"
    assert statistiques["transitions"] == 4
    assert statistiques["intervalle_s"] == 60
    assert statistiques["actif_s"] == pytest.approx(3 * 3600, abs=1)
    # Centiles à une tranche près (±12 %).
    assert 4 <= statistiques["lux_p10"] <= statistiques["lux_p90"] <= 100
    assert resume([], JOUR)["intervalle_s"] is None


def test_options_actuelles_utilisees():
    """La courbe se juge avec les options du moment (lux_max changé)."""
    jour = _repartis(400, 4000, 12)
    assert diagnostic([jour], "courbe", **{CONF_LUX_MAX: 5000}).niveau != "avertissement"


# ------------------------------------------------------------- secours
def secours(**valeurs) -> dict:
    return {"etat": "stable", "facteur": 2.0, "echantillons": 120, "requis": 30,
            "dispersion": 1.1, "zeros": {"principal": 0, "secours": 0}, "fige": False,
            "disponible": True, "actif": False, **valeurs}


def test_sans_secours_pas_de_diagnostic():
    assert all(d.id != "secours" for d in evaluer([StatsJour(JOUR)], JOUR, contexte()))


@pytest.mark.parametrize(("valeurs", "niveau"), [
    ({}, "ok"),
    ({"etat": "apprentissage", "echantillons": 12, "facteur": None}, "attente"),
    ({"etat": "instable"}, "avertissement"),
    ({"etat": "incoherent"}, "avertissement"),
    ({"fige": True}, "avertissement"),
    ({"disponible": False}, "avertissement"),
    ({"actif": True}, "info"),
])
def test_diagnostic_du_secours(valeurs, niveau):
    d = diagnostic([StatsJour(JOUR)], "secours", secours=secours(**valeurs))
    assert d.niveau == niveau
    if niveau == "attente":
        assert d.valeurs["progression"] == [12, 30]


def test_principal_fige_relaye_par_le_secours():
    jours = [StatsJour(JOUR)]
    d = diagnostic(jours, "capteur_fige", fige=True, secours=secours(actif=True))
    assert (d.niveau, d.valeurs) == ("avertissement", {"relais": True})
    # Un seul message pour le relais.
    ids = [d.id for d in evaluer(jours, JOUR, contexte(fige=True, secours=secours(actif=True)))]
    assert "secours" not in ids
    d = diagnostic(jours, "capteur_fige", fige=True, secours=secours(etat="apprentissage"))
    assert (d.niveau, d.valeurs) == ("bloquant", {"relais": False})
