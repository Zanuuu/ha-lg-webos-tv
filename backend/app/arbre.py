"""Chargement de l'arbre des menus (menu-tree/) et validation des écritures.

L'arbre est assemblé d'après index.json : sections de premier niveau, la
section Général étant composée de branches. Le résultat est mis en cache au
premier accès.
"""

import json
from functools import lru_cache
from typing import Any

from . import config


@lru_cache(maxsize=1)
def charger() -> dict:
    index = json.loads((config.MENU_TREE_DIR / "index.json").read_text())
    sections = []
    for section in index["sections"]:
        if "fichier" in section:
            sections.append(json.loads(
                (config.MENU_TREE_DIR / section["fichier"]).read_text()))
        else:
            sections.append({
                "id": section["id"],
                "libelle": section["libelle"],
                "controle": "sous-menu",
                "enfants": [
                    json.loads((config.MENU_TREE_DIR / branche["fichier"]).read_text())
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


def preparer_ecriture(entree_id: str, valeur: Any) -> tuple[str, str, Any]:
    """Vérifie qu'une écriture est possible et valide, renvoie
    (catégorie API, clé API, valeur)."""
    entree = par_id().get(entree_id)
    if entree is None:
        raise EntreeInconnue(entree_id)
    api = entree.get("api") or {}
    if api.get("acces") != "lecture_ecriture" or not api.get("cle"):
        raise EntreeNonPilotable(entree_id)
    if "<" in api["cle"]:
        # Clé générique (ex. whiteBalance<Couleur>) : l'écriture directe par
        # entrée n'est pas possible, passer par l'API catégorie/clé.
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

    if entree.get("controle") == "interrupteur" and isinstance(valeur, bool):
        # L'API webOS attend "on"/"off" pour les interrupteurs.
        valeur = "on" if valeur else "off"

    return api["categorie"], api["cle"], valeur
