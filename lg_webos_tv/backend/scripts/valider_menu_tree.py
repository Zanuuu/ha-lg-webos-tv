"""Valide les fichiers menu-tree/*.json contre menu-tree/schema.json :
conformité au schéma, unicité des id, cohérence id/chemin."""

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[3] / "custom_components" / "lg_webos_tv" / "menu_tree"


def iter_entrees(entree, parents=()):
    yield entree, parents
    for enfant in entree.get("enfants", []):
        yield from iter_entrees(enfant, parents + (entree,))


def main() -> int:
    schema = json.loads((ROOT / "schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    erreurs = 0
    ids: dict[str, str] = {}

    fichiers = sorted(p for p in ROOT.rglob("*.json") if p.name not in ("schema.json", "index.json"))
    for path in fichiers:
        data = json.loads(path.read_text())
        for err in validator.iter_errors(data):
            print(f"{path.name}: {'/'.join(map(str, err.absolute_path))}: {err.message}")
            erreurs += 1
        for entree, parents in iter_entrees(data):
            eid = entree.get("id", "")
            if eid in ids:
                print(f"{path.name}: id en double : {eid} (déjà dans {ids[eid]})")
                erreurs += 1
            ids[eid] = path.name
            if parents and not eid.startswith(parents[-1].get("id", "") + "."):
                print(f"{path.name}: id {eid} n'est pas préfixé par celui de son parent {parents[-1].get('id')}")
                erreurs += 1

    n = len(ids)
    if erreurs:
        print(f"{erreurs} erreur(s), {n} entrées, {len(fichiers)} fichier(s)")
        return 1
    print(f"OK : {n} entrées valides dans {len(fichiers)} fichier(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
