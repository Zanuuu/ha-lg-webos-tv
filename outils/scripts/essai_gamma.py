"""Essai P5 bis (docs/essais-lot7.md) : correspondance entre les valeurs API
de `gamma` et les libellés du menu Image › Paramètres avancés › Luminosité ›
Gamma.

Pour chaque mode d'image demandé (Standard puis Expert par défaut), le
script passe dans ce mode, écrit chaque valeur API par le même chemin que
l'intégration (`Televiseur`), puis vous demande le libellé affiché dans le
menu. Rien n'est supposé : une écriture refusée ou non confirmée est notée
comme telle.

Usage (venv racine ; luminosité adaptative désactivée dans Home Assistant) :
  LG_TV_HOST=<ip> .venv/bin/python outils/scripts/essai_gamma.py
  ... --modes normal expert1 expert2
  ... --avec-medium-having-level   # valeur documentée par le téléviseur

Relevé CSV dans outils/data/mesures/ (hors git) et tableau Markdown à coller
dans docs/essais-lot7.md. Le gamma de chaque mode visité, puis le mode
initial, sont restaurés à la fin, Ctrl-C compris.
"""

import argparse
import asyncio
import csv
from datetime import datetime

from common import DOSSIER_MESURES, demander, televiseur_connecte

CATEGORIE = "picture"
VALEURS = ["low", "medium", "high1", "high2"]
# Le changement de mode fait rappeler au téléviseur une rafale de valeurs.
ATTENTE_MODE_S = 2.0


async def changer_mode(tv, mode: str) -> bool:
    if tv.mode_image == mode:
        return True
    resultat = await tv.ecrire(CATEGORIE, "pictureMode", mode)
    await asyncio.sleep(ATTENTE_MODE_S)
    if not resultat["confirme"]:
        print(f"  passage en mode {mode} non confirmé (relu : {resultat['nouvelle']})")
    return resultat["confirme"]


async def essayer(tv, mode: str, valeur: str) -> dict:
    ligne = {"mode": mode, "valeur_api": valeur, "confirmee": False, "relue": None,
             "libelle_menu": "", "erreur": ""}
    try:
        resultat = await tv.ecrire(CATEGORIE, "gamma", valeur)
        ligne["confirmee"], ligne["relue"] = resultat["confirme"], resultat["nouvelle"]
    except Exception as exc:  # noqa: BLE001 — relevé, l'essai continue
        ligne["erreur"] = f"{type(exc).__name__} : {exc}"
    etat = "confirmée" if ligne["confirmee"] else f"NON confirmée {ligne['erreur']}".strip()
    print(f"  gamma = {valeur} : {etat} (relu : {ligne['relue']})")
    ligne["libelle_menu"] = await demander(
        "  Libellé affiché dans Gamma (tel quel ; vide si rien ne change) : ")
    return ligne


def tableau(lignes: list[dict]) -> str:
    texte = ["| Mode | Valeur API | Confirmée | Relue | Libellé du menu |",
             "|---|---|---|---|---|"]
    texte += [f"| {ligne['mode']} | `{ligne['valeur_api']}` | "
              f"{'oui' if ligne['confirmee'] else 'non'} | `{ligne['relue']}` | "
              f"{ligne['libelle_menu'] or '—'} |" for ligne in lignes]
    return "\n".join(texte)


def enregistrer(lignes: list[dict]):
    DOSSIER_MESURES.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER_MESURES / f"{datetime.now():%Y%m%d-%H%M%S}-gamma.csv"
    with chemin.open("w", newline="", encoding="utf-8") as fichier:
        sortie = csv.DictWriter(fichier, fieldnames=list(lignes[0]))
        sortie.writeheader()
        sortie.writerows(lignes)
    return chemin


async def principal(args) -> None:
    tv = await televiseur_connecte()
    mode_initial = tv.mode_image
    gamma_initial: dict[str, str] = {}
    lignes: list[dict] = []
    print(f"mode d'image initial : {mode_initial} ; voie d'écriture : {tv.voie_ecriture}")
    print("Ouvrez Image › Paramètres avancés › Luminosité sur le téléviseur. Si le menu se "
          "ferme à chaque écriture (voie « alerte »), rouvrez-le avant de répondre.\n")
    valeurs = VALEURS + (["mediumHavingLevel"] if args.avec_medium_having_level else [])
    try:
        for mode in args.modes:
            print(f"Mode {mode}")
            if not await changer_mode(tv, mode):
                continue
            gamma_initial[mode] = (await tv.lire(CATEGORIE, ["gamma"])).get("gamma")
            print(f"  gamma initial : {gamma_initial[mode]}")
            for valeur in valeurs:
                lignes.append(await essayer(tv, mode, valeur))
    finally:
        for mode, valeur in gamma_initial.items():
            if valeur is not None and await changer_mode(tv, mode):
                await tv.ecrire(CATEGORIE, "gamma", valeur)
                print(f"gamma du mode {mode} restauré à {valeur}")
        if mode_initial is not None:
            await changer_mode(tv, mode_initial)
            print(f"mode d'image restauré : {mode_initial}")
        await tv.arreter()
    if lignes:
        print(f"\nrelevé : {enregistrer(lignes)}\n")
        print(tableau(lignes))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--modes", nargs="+", default=["normal", "expert1"],
                        help="valeurs API des modes d'image (normal = Standard)")
    parser.add_argument("--avec-medium-having-level", action="store_true",
                        help="essaie aussi la valeur mediumHavingLevel")
    try:
        asyncio.run(principal(parser.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
