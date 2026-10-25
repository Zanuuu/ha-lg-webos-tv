"""Historique, retour arrière et presets, au niveau du cœur (restauration)."""

import time

import pytest

from custom_components.lg_webos_tv import restauration
from custom_components.lg_webos_tv.presets import (PresetExistant, PresetInconnu,
                                                   capturer_snapshot)

from .conftest import attendre

ID_NETTETE = "image.parametres-avances.clarte.ajuster-nettete"
ID_CONTRASTE = "image.parametres-avances.luminosite.ajuster-le-contraste"
ID_EARC = "son.parametres-avances.compatibilite-earc"


@pytest.fixture
async def tv(televiseur):
    await televiseur.demarrer()
    assert await attendre(lambda: televiseur.etat_connexion == "connecte")
    yield televiseur
    await televiseur.arreter()


def changer_mode(tv, faux_client, mode):
    # Comme une notification du téléviseur après un changement à la télécommande.
    faux_client.valeurs["picture"]["pictureMode"] = mode
    tv.etat["picture"]["pictureMode"] = mode


async def creer_preset(tv, presets, nom, entrees=None):
    return await presets.sauvegarder(nom, capturer_snapshot(tv.etat, tv.mode_image, entrees))


# --------------------------------------------------------------- historique

async def test_annuler_ecriture(tv, historique):
    await restauration.ecrire_par_entree(tv, historique, ID_NETTETE, 25, "panneau")
    id_ecriture = (await historique.lister())[0]["id"]

    resultat = await restauration.annuler_ecriture(tv, historique, id_ecriture)
    assert resultat["ok"] is True
    assert resultat["nouvelle"] == 10

    histo = await historique.lister()
    assert len(histo) == 2
    assert histo[0]["ancienne"] == 25 and histo[0]["nouvelle"] == 10
    assert [h["origine"] for h in histo] == ["annulation", "panneau"]


async def test_ecriture_sans_historique(tv, historique):
    """Pas intermédiaire d'une rampe : écrit et confirmé, non historisé."""
    resultat = await restauration.ecrire_par_entree(tv, historique, ID_NETTETE, 25,
                                                    "luminosite_adaptative",
                                                    historiser=False)
    assert resultat["ok"] is True and resultat["nouvelle"] == 25
    assert await historique.lister() == []


async def test_annuler_refuse_si_mode_image_different(tv, historique, faux_client):
    await restauration.ecrire_par_entree(tv, historique, ID_NETTETE, 25, "panneau")
    id_ecriture = (await historique.lister())[0]["id"]
    changer_mode(tv, faux_client, "expert1")

    resultat = await restauration.annuler_ecriture(tv, historique, id_ecriture)
    assert resultat["ok"] is False
    assert "expert2" in resultat["raison"] and "expert1" in resultat["raison"]
    assert faux_client.valeurs["picture"]["sharpness"] == 25


async def test_annuler_entree_inconnue(tv, historique):
    resultat = await restauration.annuler_ecriture(tv, historique, 999)
    assert resultat == {"ok": False, "raison": "entrée d'historique introuvable"}


async def test_revenir_a_un_instant(tv, historique):
    repere = time.time()
    await restauration.ecrire_par_entree(tv, historique, ID_NETTETE, 20, "panneau")
    await restauration.ecrire_par_entree(tv, historique, ID_CONTRASTE, 90, "panneau")
    await restauration.ecrire_par_entree(tv, historique, ID_NETTETE, 30, "panneau")

    resultats = await restauration.revenir_a(tv, historique, repere)
    assert len(resultats) == 3
    assert all(r["ok"] for r in resultats)
    assert tv.etat["picture"]["sharpness"] == 10
    assert tv.etat["picture"]["contrast"] == 100


async def test_ecriture_refusee_non_historisee(tv, historique, faux_client):
    faux_client.refuser.add(("picture", "sharpness"))
    resultat = await restauration.ecrire_par_entree(tv, historique, ID_NETTETE, 12, "panneau")
    assert resultat["ok"] is False
    assert "refusée par le téléviseur" in resultat["raison"]
    assert await historique.lister() == []


# ------------------------------------------------------------------ presets

async def test_creer_lister_obtenir_preset(tv, presets):
    cree = await creer_preset(tv, presets, "mon-preset")
    ids = {e["entree_id"] for e in cree["entrees"]}
    assert ID_NETTETE in ids and ID_EARC in ids

    # Les réglages d'image portent le mode capturé, les autres non.
    par_id = {e["entree_id"]: e for e in cree["entrees"]}
    assert par_id[ID_NETTETE]["mode_image"] == "expert2"
    assert par_id[ID_EARC]["mode_image"] is None

    assert await presets.lister() == [{
        "nom": "mon-preset", "cree_le": cree["cree_le"],
        "nombre_reglages": len(cree["entrees"])}]
    assert await presets.recuperer("mon-preset") == cree


async def test_creer_preset_nom_existant_refuse(tv, presets):
    await creer_preset(tv, presets, "double")
    with pytest.raises(PresetExistant):
        await creer_preset(tv, presets, "double")


async def test_preset_sous_ensemble_choisi(tv, presets):
    cree = await creer_preset(tv, presets, "partiel", [ID_NETTETE])
    assert [e["entree_id"] for e in cree["entrees"]] == [ID_NETTETE]


async def test_supprimer_preset(tv, presets):
    await creer_preset(tv, presets, "a-supprimer")
    assert await presets.supprimer("a-supprimer") is True
    assert await presets.recuperer("a-supprimer") is None
    assert await presets.supprimer("a-supprimer") is False


async def test_appliquer_preset_inconnu(tv, historique, presets):
    with pytest.raises(PresetInconnu):
        await restauration.appliquer_preset(tv, historique, presets, "inconnu")


async def test_importer_preset_remplacer(presets):
    entrees = [{"entree_id": ID_NETTETE, "categorie": "picture", "cle": "sharpness",
                "valeur": 15, "mode_image": "expert2"}]
    await presets.sauvegarder("importe", entrees)
    assert (await presets.recuperer("importe"))["entrees"] == entrees
    with pytest.raises(PresetExistant):
        await presets.sauvegarder("importe", entrees)
    await presets.sauvegarder("importe", entrees, remplacer=True)


async def test_appliquer_preset_complet_bascule_le_mode_si_necessaire(
        tv, historique, presets, faux_client):
    await creer_preset(tv, presets, "expert2-tel-quel")
    changer_mode(tv, faux_client, "expert1")
    faux_client.valeurs["picture"]["sharpness"] = 5
    tv.etat["picture"]["sharpness"] = 5

    resultat = await restauration.appliquer_preset(tv, historique, presets, "expert2-tel-quel")
    assert resultat["echecs"] == []
    assert {"pictureMode", "sharpness"} <= {e["cle"] for e in resultat["appliques"]}
    assert tv.mode_image == "expert2"
    assert tv.etat["picture"]["sharpness"] == 10
    assert {h["origine"] for h in await historique.lister()} == {"preset"}


async def test_preset_avec_une_entree_refusee_continue(tv, historique, presets, faux_client):
    await creer_preset(tv, presets, "avec-refus", [ID_NETTETE, ID_CONTRASTE])
    faux_client.refuser.add(("picture", "sharpness"))
    # Les deux valeurs diffèrent des valeurs capturées, sinon l'écriture
    # n'a rien à changer d'observable.
    for cle in ("sharpness", "contrast"):
        tv.etat["picture"][cle] = 1
        faux_client.valeurs["picture"][cle] = 1

    resultat = await restauration.appliquer_preset(tv, historique, presets, "avec-refus")
    assert [e["cle"] for e in resultat["appliques"]] == ["contrast"]
    assert [e["cle"] for e in resultat["echecs"]] == ["sharpness"]
    assert "refusée par le téléviseur" in resultat["echecs"][0]["raison"]
    assert faux_client.valeurs["picture"]["contrast"] == 100


async def test_appliquer_preset_partiel_echoue_si_mode_different(
        tv, historique, presets, faux_client):
    # Preset partiel : ne capture pas pictureMode, seulement la netteté.
    await creer_preset(tv, presets, "nettete-seule", [ID_NETTETE])
    changer_mode(tv, faux_client, "expert1")

    resultat = await restauration.appliquer_preset(tv, historique, presets, "nettete-seule")
    assert resultat["appliques"] == []
    assert "expert2" in resultat["echecs"][0]["raison"]

    changer_mode(tv, faux_client, "expert2")
    resultat = await restauration.appliquer_preset(tv, historique, presets, "nettete-seule")
    assert len(resultat["appliques"]) == 1 and resultat["echecs"] == []
