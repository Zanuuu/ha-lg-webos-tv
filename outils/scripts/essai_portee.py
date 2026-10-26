"""Essai P10 (docs/essais-lot7.md) : réglages d'image propres au mode ou
communs à tous les modes, « Réduire la lumière bleue » en FILMMAKER MODE,
et luminosité notifiée quand « Protection des yeux » est active.

Portée, pour chaque réglage : valeurs lues en mode A puis en mode B ; si
elles diffèrent, le réglage est propre au mode (un réglage commun aurait la
même valeur partout). Sinon, une autre valeur est écrite en mode A, puis
relue en mode B : retrouvée, le réglage est commun ; sinon, propre au mode.
Tout passe par `Televiseur`, comme l'intégration.

Usage (venv racine ; luminosité adaptative désactivée dans Home Assistant) :
  LG_TV_HOST=<ip> .venv/bin/python outils/scripts/essai_portee.py
  ... --mode-a normal --mode-b cinema           # modes comparés
  ... --cles eyeComfortMode gamma                # sous-ensemble
  ... --filmmaker                                # lumière bleue en FILMMAKER
  ... --protection-yeux 5                        # 5 min de notifications

Relevé CSV dans outils/data/mesures/ (hors git) et tableau Markdown à coller
dans docs/essais-lot7.md. Chaque valeur écrite et le mode initial sont
restaurés à la fin, Ctrl-C compris.
"""

import argparse
import asyncio
import csv
import sys
import time
from datetime import datetime

from common import DOSSIER_MESURES, RACINE, demander, televiseur_connecte

CATEGORIE = "picture"
# Valeurs API connues (menu_tree, inventaire-api.json) ; la première qui
# diffère de la valeur lue est écrite.
VALEURS = {
    "eyeComfortMode": ["on", "off"],
    "motionEyeCare": ["on", "off"],
    "peakBrightness": ["high", "off"],
    "dynamicContrast": ["low", "medium", "off"],
    "gamma": ["high1", "high2", "medium"],
    "hdrDynamicToneMapping": ["off", "on"],
    # Rangé dans la catégorie picture, présenté dans Général : à trancher
    # aussi (étude, § 8.3). « min » baisse un peu la luminosité, sans plus.
    "energySaving": ["min", "off"],
}
ATTENTE_MODE_S = 2.0


class Seance:
    """Écritures faites, à défaire dans l'ordre inverse : (mode, clé, valeur
    d'avant)."""

    def __init__(self, tv) -> None:
        self.tv = tv
        self.mode_initial = tv.mode_image
        self.a_defaire: list[tuple[str, str, object]] = []

    async def mode(self, mode: str) -> bool:
        if self.tv.mode_image == mode:
            return True
        resultat = await self.tv.ecrire(CATEGORIE, "pictureMode", mode)
        await asyncio.sleep(ATTENTE_MODE_S)
        if not resultat["confirme"]:
            print(f"  passage en mode {mode} non confirmé (relu : {resultat['nouvelle']})")
        return resultat["confirme"]

    async def lire(self, cle: str):
        return (await self.tv.lire(CATEGORIE, [cle])).get(cle)

    async def ecrire(self, cle: str, valeur, avant) -> tuple[bool, str]:
        try:
            resultat = await self.tv.ecrire(CATEGORIE, cle, valeur)
        except Exception as exc:  # noqa: BLE001 — relevé, l'essai continue
            return False, f"{type(exc).__name__} : {exc}"
        if resultat["confirme"]:
            self.a_defaire.append((self.tv.mode_image, cle, avant))
            return True, ""
        return False, f"non confirmée (relu : {resultat['nouvelle']})"

    async def defaire(self) -> None:
        for mode, cle, valeur in reversed(self.a_defaire):
            if valeur is not None and await self.mode(mode):
                await self.tv.ecrire(CATEGORIE, cle, valeur)
                print(f"{cle} restauré à {valeur} (mode {mode})")
        self.a_defaire.clear()
        if self.mode_initial is not None:
            await self.mode(self.mode_initial)
            print(f"mode d'image restauré : {self.mode_initial}")


async def portee(seance: Seance, cle: str, mode_a: str, mode_b: str) -> dict:
    ligne = {"cle": cle, "mode_a": mode_a, "mode_b": mode_b, "valeur_a": None,
             "valeur_b": None, "ecrite_en_a": None, "relue_en_b": None, "verdict": "",
             "erreur": ""}
    await seance.mode(mode_a)
    ligne["valeur_a"] = va = await seance.lire(cle)
    await seance.mode(mode_b)
    ligne["valeur_b"] = vb = await seance.lire(cle)
    if va is None or vb is None:
        ligne["verdict"] = "illisible dans l'un des modes"
    elif str(va) != str(vb):
        ligne["verdict"] = "propre au mode (valeurs différentes)"
    else:
        x = next((v for v in VALEURS[cle] if v != str(va)), None)
        await seance.mode(mode_a)
        ok, erreur = await seance.ecrire(cle, x, va)
        ligne["ecrite_en_a"], ligne["erreur"] = x, erreur
        if not ok:
            ligne["verdict"] = "écriture refusée en mode A"
        else:
            await seance.mode(mode_b)
            ligne["relue_en_b"] = rb = await seance.lire(cle)
            ligne["verdict"] = ("commun à tous les modes" if str(rb) == x
                                else "propre au mode" if str(rb) == str(va)
                                else f"indéterminé (relu {rb})")
            # Remis tout de suite : la suite de la séance part des valeurs
            # de l'utilisateur.
            await seance.mode(mode_a)
            await seance.tv.ecrire(CATEGORIE, cle, va)
            seance.a_defaire.pop()
    print(f"{cle:22} A={ligne['valeur_a']!s:7} B={ligne['valeur_b']!s:7} → {ligne['verdict']}"
          + (f" ({ligne['erreur']})" if ligne["erreur"] else ""))
    return ligne


async def filmmaker(seance: Seance, mode_a: str) -> dict:
    """« Réduire la lumière bleue » activé hors FILMMAKER, puis passage en
    FILMMAKER : valeur relue, et ce que vous voyez."""
    ligne = {"cle": "eyeComfortMode", "mode_a": mode_a, "mode_b": "filmMaker",
             "valeur_a": None, "valeur_b": None, "ecrite_en_a": "on", "relue_en_b": None,
             "verdict": "", "erreur": ""}
    await seance.mode(mode_a)
    ligne["valeur_a"] = avant = await seance.lire("eyeComfortMode")
    if str(avant) != "on":
        ok, ligne["erreur"] = await seance.ecrire("eyeComfortMode", "on", avant)
        if not ok:
            ligne["verdict"] = "écriture refusée"
            return ligne
    await seance.mode("filmMaker")
    ligne["relue_en_b"] = await seance.lire("eyeComfortMode")
    menu = await demander("FILMMAKER : « Réduire la lumière bleue » dans le menu Image "
                          "(activé, désactivé, grisé, absent) ? ")
    teinte = await demander("L'image paraît-elle plus chaude qu'avec le réglage désactivé "
                            "(o/n/?) ? ")
    ligne["verdict"] = f"menu : {menu or '?'} ; teinte plus chaude : {teinte or '?'}"
    print(f"eyeComfortMode en FILMMAKER : relu {ligne['relue_en_b']} → {ligne['verdict']}")
    return ligne


async def protection_yeux(seance: Seance, minutes: float, notifications: list) -> dict:
    """Protection des yeux active sur un contenu variable : la valeur
    `backlight` notifiée change-t-elle, et avec quel `caller` ?"""
    ligne = {"cle": "motionEyeCare", "mode_a": seance.tv.mode_image, "mode_b": "",
             "valeur_a": None, "valeur_b": None, "ecrite_en_a": "on", "relue_en_b": None,
             "verdict": "", "erreur": ""}
    ligne["valeur_a"] = avant = await seance.lire("motionEyeCare")
    if str(avant) != "on":
        ok, ligne["erreur"] = await seance.ecrire("motionEyeCare", "on", avant)
        if not ok:
            ligne["verdict"] = "écriture refusée"
            return ligne
    print(f"Protection des yeux active : lancez un contenu variable (scènes claires et "
          f"sombres) ; observation {minutes:g} min.")
    debut = len(notifications)
    await asyncio.sleep(minutes * 60)
    vues = [n for n in notifications[debut:] if "backlight" in n[1]]
    for instant, reglages, caller in vues:
        print(f"  [{instant:7.1f} s] backlight = {reglages['backlight']} (caller : {caller})")
    ligne["verdict"] = (f"{len(vues)} notification(s) de backlight" if vues
                        else "aucune notification de backlight")
    print(ligne["verdict"])
    return ligne


def tableau(lignes: list[dict]) -> str:
    texte = ["| Réglage | Mode A | Mode B | Valeur A | Valeur B | Essayée en A | Relue en B "
             "| Verdict |", "|---|---|---|---|---|---|---|---|"]
    texte += [f"| `{ligne['cle']}` | {ligne['mode_a']} | {ligne['mode_b']} | "
              f"`{ligne['valeur_a']}` | `{ligne['valeur_b']}` | `{ligne['ecrite_en_a']}` | "
              f"`{ligne['relue_en_b']}` | {ligne['verdict']}"
              f"{' — ' + ligne['erreur'] if ligne['erreur'] else ''} |" for ligne in lignes]
    return "\n".join(texte)


def enregistrer(lignes: list[dict]):
    DOSSIER_MESURES.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER_MESURES / f"{datetime.now():%Y%m%d-%H%M%S}-portee.csv"
    with chemin.open("w", newline="", encoding="utf-8") as fichier:
        sortie = csv.DictWriter(fichier, fieldnames=list(lignes[0]))
        sortie.writeheader()
        sortie.writerows(lignes)
    return chemin


async def principal(args) -> None:
    from custom_components.lg_webos_tv.televiseur import Televiseur

    t0 = time.monotonic()
    notifications: list[tuple[float, dict, str | None]] = []

    class TeleviseurNote(Televiseur):
        """Garde le `caller` brut de chaque notification de l'image."""

        async def _sur_notification(self, categorie, charge):
            if categorie == CATEGORIE and charge.get("settings"):
                notifications.append((time.monotonic() - t0, charge["settings"],
                                      charge.get("caller")))
            await super()._sur_notification(categorie, charge)

    tv = await televiseur_connecte(classe=TeleviseurNote)
    seance = Seance(tv)
    lignes: list[dict] = []
    print(f"mode d'image initial : {seance.mode_initial} ; voie d'écriture : "
          f"{tv.voie_ecriture} ; modes comparés : {args.mode_a} et {args.mode_b}\n")
    try:
        for cle in args.cles:
            lignes.append(await portee(seance, cle, args.mode_a, args.mode_b))
        if args.filmmaker:
            lignes.append(await filmmaker(seance, args.mode_a))
            await seance.defaire()
        if args.protection_yeux:
            await seance.mode(args.mode_a)
            lignes.append(await protection_yeux(seance, args.protection_yeux, notifications))
    finally:
        await seance.defaire()
        await tv.arreter()
    if lignes:
        print(f"\nrelevé : {enregistrer(lignes)}\n")
        print(tableau(lignes))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode-a", default="normal", help="valeur API (normal = Standard)")
    parser.add_argument("--mode-b", default="cinema", help="valeur API (cinema = Cinéma)")
    parser.add_argument("--cles", nargs="*", default=list(VALEURS), choices=list(VALEURS))
    parser.add_argument("--filmmaker", action="store_true",
                        help="« Réduire la lumière bleue » en FILMMAKER MODE")
    parser.add_argument("--protection-yeux", type=float, metavar="MIN",
                        help="minutes d'observation de backlight, Protection des yeux active")
    # La sous-classe de Televiseur importe l'intégration avant
    # televiseur_connecte, qui ajoute sinon la racine du dépôt au chemin.
    sys.path.insert(0, str(RACINE))
    try:
        asyncio.run(principal(parser.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
