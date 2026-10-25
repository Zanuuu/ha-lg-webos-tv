"""Rampe de la luminosité (rampe.py), sans Home Assistant : séries
horodatées, téléviseur simulé par une latence fixe."""

import pytest

from custom_components.lg_webos_tv.rampe import (DEBIT_DEFAUT, PAS_DEFAUT,
                                                 Parametres, Rampe, parametres)


def derouler(rampe: Rampe, cible, latence=0.0, fin=120.0):
    """Écrit chaque pas à son instant, confirmé après `latence` ; `cible`
    est une valeur ou une fonction du temps. Renvoie [(instant, valeur)]."""
    pas, t = [], 0.0
    while t <= fin:
        c = cible(t) if callable(cible) else cible
        prochain = rampe.prochain_pas(t, c)
        if prochain is None:
            if not callable(cible):
                break
            t += 0.05
            continue
        instant, valeur = prochain
        t = instant
        rampe.envoyer(t, valeur)
        t += latence
        rampe.confirmer(valeur)
        pas.append((instant, valeur))
    return pas


def test_parametres_par_defaut_et_options():
    assert parametres({}) == Parametres(PAS_DEFAUT, DEBIT_DEFAUT)
    assert parametres({"rampe_pas": 2, "rampe_debit": 8}).intervalle_s == 0.25


def test_40_a_100_par_pas_de_un():
    pas = derouler(Rampe(parametres({}), 40, 0), 100)
    assert len(pas) == 60
    assert [v for _, v in pas] == list(range(41, 101))
    assert pas[-1][0] == pytest.approx(14.75)


def test_pas_de_deux_toutes_les_demi_secondes():
    pas = derouler(Rampe(Parametres(2, 4), 40, 0), 100)
    assert len(pas) == 30
    assert all(b - a == 2 for (_, a), (_, b) in zip(pas, pas[1:]))
    assert pas[-1][0] == pytest.approx(14.5)


def test_latence_rattrapee_sans_saut():
    """Pas confirmés en 0,4 s pour un intervalle de 0,25 s : la durée tient
    à peu près, aucun pas ne dépasse deux points."""
    pas = derouler(Rampe(parametres({}), 40, 0), 100, latence=0.4)
    amplitudes = [abs(b - a) for (_, a), (_, b) in zip([(0, 40), *pas], pas)]
    assert max(amplitudes) == 2
    assert pas[-1][1] == 100
    assert pas[-1][0] < 20


def test_cible_qui_change_et_s_inverse():
    rampe = Rampe(parametres({}), 40, 0)
    pas = derouler(rampe, lambda t: 100 if t < 5 else 50, fin=20)
    valeurs = [v for _, v in pas]
    sommet = max(valeurs)
    assert 58 <= sommet <= 61
    assert valeurs[-1] == 50
    # Descente à la même cadence que la montée.
    assert valeurs[valeurs.index(sommet) + 1] == sommet - 1


def test_arrivee_seulement_filtre_arrive():
    rampe = Rampe(parametres({}), 59, 0)
    rampe.envoyer(0, 60)
    rampe.confirmer(60)
    assert rampe.prochain_pas(1, 60) is None
    assert not rampe.arrivee(60, 58)
    assert rampe.arrivee(60, 60)


def test_valeur_inconnue_un_seul_pas():
    rampe = Rampe(parametres({}), None, 0)
    assert rampe.prochain_pas(0, 70) == (0, 70)


def test_premiere_interruption_retenue():
    rampe = Rampe(parametres({}), 40, 0)
    rampe.interrompre("mode")
    rampe.interrompre("reprise_en_main")
    assert rampe.interruption == "mode"
