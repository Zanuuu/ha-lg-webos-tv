"""Orchestration des écritures vers le téléviseur : validation par l'arbre,
garde sur le mode d'image pour les réglages qui en dépendent, et
historisation. Utilisée par les routes d'écriture directe, l'annulation
d'une entrée d'historique, le retour à un instant donné, et l'application
d'un preset.
"""

from typing import Any

from . import arbre
from .historique import Historique
from .presets import PresetInconnu, Presets
from .televiseur import (ConnexionTvPerdue, EcritureImpossible, EcritureRefusee,
                         Televiseur)

# Raison renvoyée quand le téléviseur n'accorde pas l'écriture (webOS 11).
RAISON_ECRITURE_IMPOSSIBLE = ("modification impossible : le téléviseur n'autorise "
                              "plus l'écriture des réglages par l'API (webOS 11)")


async def ecrire(tv: Televiseur, historique: Historique, entree_id: str | None,
                 categorie: str, cle: str, valeur: Any, origine: str,
                 mode_attendu: str | None = None) -> dict:
    """Écrit un réglage et historise l'écriture réussie avec son `origine`
    (historique.ORIGINES).

    `mode_attendu`, s'il est fourni, exige que ce mode d'image soit actif
    pour les réglages qui en dépendent (`arbre.mode_dependant`) : utilisé par
    l'annulation, le retour à un instant donné, et l'application de presets,
    dont les valeurs proviennent d'un instant où un mode particulier était
    actif. Les écritures directes (mode_attendu=None) ne sont jamais gardées :
    elles s'appliquent toujours au mode actif, comme une action manuelle.
    """
    base = {"entree_id": entree_id, "categorie": categorie, "cle": cle}
    if mode_attendu is not None and arbre.mode_dependant(categorie, cle) \
            and tv.mode_image != mode_attendu:
        return {
            **base, "ok": False,
            "raison": (f"réglage propre au mode d'image « {mode_attendu} », "
                      f"mode actif : « {tv.mode_image} »"),
        }
    try:
        resultat = await tv.ecrire(categorie, cle, valeur)
    except ConnexionTvPerdue:
        return {**base, "ok": False, "raison": "téléviseur injoignable"}
    except EcritureImpossible:
        return {**base, "ok": False, "raison": RAISON_ECRITURE_IMPOSSIBLE}
    except EcritureRefusee as exc:
        return {**base, "ok": False, "raison": f"refusée par le téléviseur : {exc}"}
    if not resultat["confirme"]:
        return {**base, "ok": False, "raison": "valeur non confirmée après relecture",
                **resultat}
    await historique.enregistrer(entree_id, categorie, cle,
                                 resultat["ancienne"], resultat["nouvelle"],
                                 resultat["mode_image"], origine)
    return {**base, "ok": True, **resultat}


async def ecrire_par_entree(tv: Televiseur, historique: Historique,
                            entree_id: str, valeur: Any, origine: str,
                            mode_attendu: str | None = None) -> dict:
    """Écriture directe (entité, action, panneau), validée par l'arbre :
    bornes, choix."""
    categorie, cle, valeur = arbre.preparer_ecriture(entree_id, valeur)
    return await ecrire(tv, historique, entree_id, categorie, cle, valeur,
                        origine, mode_attendu)


async def annuler_ecriture(tv: Televiseur, historique: Historique, id_: int) -> dict:
    """Retour arrière d'une modification : réécrit son ancienne valeur."""
    ligne = await historique.recuperer(id_)
    if ligne is None:
        return {"ok": False, "raison": "entrée d'historique introuvable"}
    return await ecrire(tv, historique, ligne["entree_id"], ligne["categorie"],
                        ligne["cle"], ligne["ancienne"], "annulation",
                        mode_attendu=ligne["mode_image"])


async def revenir_a(tv: Televiseur, historique: Historique, horodatage: float) -> list[dict]:
    """Retour à un instant donné : réécrit, de la plus récente à la plus
    ancienne, l'ancienne valeur de chaque écriture postérieure à
    `horodatage`. Rejoué dans cet ordre, chaque réglage modifié depuis
    converge vers l'état qu'il avait à cet instant."""
    lignes = await historique.lister_depuis(horodatage)
    resultats = []
    for ligne in lignes:
        resultats.append(await ecrire(
            tv, historique, ligne["entree_id"], ligne["categorie"], ligne["cle"],
            ligne["ancienne"], "annulation", mode_attendu=ligne["mode_image"]))
    return resultats


async def appliquer_preset(tv: Televiseur, historique: Historique,
                           presets: Presets, nom: str) -> dict:
    """Applique un preset : la sélection du mode d'image (s'il fait partie
    du preset) est écrite en premier, pour que les réglages qui en dépendent
    retrouvent le mode capturé et s'appliquent sans être refusés."""
    preset = await presets.recuperer(nom)
    if preset is None:
        raise PresetInconnu(nom)

    entrees = sorted(preset["entrees"], key=lambda e: e["cle"] != "pictureMode")
    appliques, echecs = [], []
    for item in entrees:
        entree_id = item.get("entree_id")
        try:
            categorie, cle, valeur = (
                arbre.preparer_ecriture(entree_id, item["valeur"]) if entree_id
                else (item["categorie"], item["cle"], item["valeur"])
            )
        except (arbre.EntreeInconnue, arbre.EntreeNonPilotable, arbre.ValeurInvalide) as exc:
            echecs.append({**item, "raison": f"{type(exc).__name__} : {exc}"})
            continue
        resultat = await ecrire(tv, historique, entree_id, categorie, cle, valeur,
                                "preset", mode_attendu=item.get("mode_image"))
        if resultat["ok"]:
            appliques.append(item)
        else:
            echecs.append({**item, "raison": resultat["raison"]})

    return {"nom": nom, "appliques": appliques, "echecs": echecs}
