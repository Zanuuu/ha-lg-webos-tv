"""Chargement de l'arbre des menus (menu_tree/) et validation des écritures.

L'arbre est assemblé d'après index.json : sections de premier niveau, la
section Général étant composée de branches. Le résultat est mis en cache au
premier accès.
"""

import json
from functools import lru_cache
from typing import Any

from .const import MENU_TREE_DIR


@lru_cache(maxsize=1)
def charger() -> dict:
    index = json.loads((MENU_TREE_DIR / "index.json").read_text())
    sections = []
    for section in index["sections"]:
        if "fichier" in section:
            sections.append(json.loads(
                (MENU_TREE_DIR / section["fichier"]).read_text()))
        else:
            sections.append({
                "id": section["id"],
                "libelle": section["libelle"],
                "controle": "sous-menu",
                "enfants": [
                    json.loads((MENU_TREE_DIR / branche["fichier"]).read_text())
                    for branche in section["branches"]
                ],
            })
    return {"sections": sections}


@lru_cache(maxsize=1)
def par_id() -> dict[str, dict]:
    entrees: dict[str, dict] = {}

    def visiter(entree: dict) -> None:
        entrees[entree["id"]] = entree
        for enfant in entree.get("enfants", []):
            visiter(enfant)

    for section in charger()["sections"]:
        visiter(section)
    return entrees


class ValeurInvalide(Exception):
    pass


class EntreeInconnue(Exception):
    pass


class EntreeNonPilotable(Exception):
    pass


def _est_pilotable_api(api: dict | None) -> bool:
    return bool(
        api and api.get("acces") == "lecture_ecriture" and api.get("cle")
        and "<" not in api["cle"]  # clé générique (whiteBalance<Couleur>…)
    )


def entrees_pilotables() -> list[dict]:
    """Entrées de l'arbre accessibles en écriture par l'API, base des presets."""
    return [e for e in par_id().values() if _est_pilotable_api(e.get("api"))]


def mode_dependant(categorie: str, cle: str) -> bool:
    """Les réglages d'image sont propres au mode d'image actif — sauf la
    sélection du mode elle-même, qui n'est pas propre à un mode."""
    return categorie == "picture" and cle != "pictureMode"


# Clés dont l'API attend un booléen JSON natif plutôt que "on"/"off" : écrire
# "off" y est silencieusement refusé par le téléviseur (constaté le
# 17/08/2026 sur parentalControl : « No matched extended item »).
CLES_BOOLEENNES_NATIVES = {("lock", "parentalControl")}


def preparer_ecriture(entree_id: str, valeur: Any) -> tuple[str, str, Any]:
    """Vérifie qu'une écriture est possible et valide, renvoie
    (catégorie API, clé API, valeur)."""
    entree = par_id().get(entree_id)
    if entree is None:
        raise EntreeInconnue(entree_id)
    api = entree.get("api") or {}
    if not _est_pilotable_api(api):
        raise EntreeNonPilotable(entree_id)

    bornes = entree.get("bornes")
    if bornes is not None:
        if not isinstance(valeur, (int, float)) or isinstance(valeur, bool):
            raise ValeurInvalide(f"valeur numérique attendue, reçu {valeur!r}")
        if not bornes["min"] <= valeur <= bornes["max"]:
            raise ValeurInvalide(
                f"{valeur} hors bornes [{bornes['min']}, {bornes['max']}]")

    choix = entree.get("choix")
    if choix and entree.get("controle") == "liste":
        valeurs_api = [c["valeur_api"] for c in choix if "valeur_api" in c]
        if valeurs_api and valeur not in valeurs_api:
            raise ValeurInvalide(
                f"{valeur!r} absent des choix {valeurs_api}")

    if entree.get("controle") == "interrupteur" and isinstance(valeur, bool) \
            and (api["categorie"], api["cle"]) not in CLES_BOOLEENNES_NATIVES:
        # L'API webOS attend "on"/"off" pour la plupart des interrupteurs —
        # sauf les quelques clés (ci-dessous) dont la valeur est un booléen
        # JSON natif, confirmé par test contre le téléviseur.
        valeur = "on" if valeur else "off"

    return api["categorie"], api["cle"], valeur
