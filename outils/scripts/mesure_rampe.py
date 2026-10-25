"""Essai P4 (docs/etude-luminosite-adaptative.md, § 6) : écritures en rampe
de la luminosité OLED (`backlight`), par le même chemin que l'intégration.

Le téléviseur est piloté par `Televiseur` (verrou d'écriture, confirmation
par la notification, relecture de secours, voie directe ou pont
createAlert) et la cadence vient de `rampe.Rampe` : ce qui est mesuré ici
est ce que fera la luminosité adaptative.

Usage (venv racine, Home Assistant arrêté ou fonction désactivée) :
  LG_TV_HOST=<ip> .venv/bin/python outils/scripts/mesure_rampe.py
      --de 40 --a 100 --retour                   # 1 point / 0,25 s
  ... --de 40 --a 100 --retour --pas 2 --debit 4 # 2 points / 0,5 s
  ... --de 40 --a 100 --retour --pas 1 --debit 5 # 5 points par seconde
  ... --soutenu 4 --duree 120                    # 4 écritures/s pendant 2 min
  ... --soutenu 1 --duree 600                    # 1 écriture/s pendant 10 min

Relevé par pas : instant, valeur demandée, latence (demande → confirmation),
confirmée ou non. Résumé : non confirmées, déconnexions (un refus EWS 1008
ferme la connexion), changements de `backlight` qui ne viennent pas de nous
(ils mettraient la fonction en pause), latence médiane / p95 / max, débit
effectif. Le relevé complet va dans outils/data/mesures/ (hors git).

Écriture sur le mode d'image en cours uniquement (affiché) ; la valeur
initiale est restaurée à la fin, y compris sur Ctrl-C.
"""

import argparse
import asyncio
import csv
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from bscpylgtv.storage_sqlitedict import StorageSqliteDict

from common import KEY_DB, TV_IP

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE))
from custom_components.lg_webos_tv.rampe import Parametres, Rampe  # noqa: E402
from custom_components.lg_webos_tv.televiseur import Televiseur  # noqa: E402

CATEGORIE, CLE = "picture", "backlight"
DOSSIER_MESURES = RACINE / "outils" / "data" / "mesures"


class Releve:
    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.lignes: list[dict] = []
        self.deconnexions = 0
        self.exterieurs: list[tuple[float, dict, str]] = []

    async def sur_evenement(self, evenement: dict) -> None:
        instant = time.monotonic() - self.t0
        if evenement["type"] == "connexion" and evenement["etat"] != "connecte":
            self.deconnexions += 1
            print(f"[{instant:7.2f} s] connexion : {evenement['etat']}")
        elif (evenement["type"] == "changement" and CLE in evenement["reglages"]
              and evenement["origine"] != "application"):
            self.exterieurs.append((instant, evenement["reglages"], evenement["origine"]))
            print(f"[{instant:7.2f} s] changement extérieur : {evenement['reglages']} "
                  f"({evenement['origine']})")

    async def ecrire(self, tv: Televiseur, phase: str, valeur: int) -> bool:
        debut = time.monotonic()
        try:
            resultat = await tv.ecrire(CATEGORIE, CLE, valeur)
            confirme, erreur = resultat["confirme"], ""
        except Exception as exc:  # noqa: BLE001 — relevé, l'essai continue
            confirme, erreur = False, f"{type(exc).__name__} : {exc}"
        latence = time.monotonic() - debut
        ligne = {"phase": phase, "instant_s": round(debut - self.t0, 3), "valeur": valeur,
                 "latence_s": round(latence, 3), "confirme": confirme, "erreur": erreur}
        self.lignes.append(ligne)
        print(f"[{ligne['instant_s']:7.2f} s] {phase:8} {valeur:3}  "
              f"{latence * 1000:5.0f} ms  {'ok' if confirme else 'NON CONFIRMÉE ' + erreur}")
        return confirme

    def resume(self) -> None:
        latences = sorted(ligne["latence_s"] for ligne in self.lignes)
        if not latences:
            return
        duree = self.lignes[-1]["instant_s"] - self.lignes[0]["instant_s"]
        non = [ligne for ligne in self.lignes if not ligne["confirme"]]
        p95 = latences[min(len(latences) - 1, round(0.95 * (len(latences) - 1)))]
        print("\n=== Résumé")
        print(f"écritures : {len(self.lignes)}, non confirmées : {len(non)}, "
              f"déconnexions : {self.deconnexions}, changements extérieurs : "
              f"{len(self.exterieurs)}")
        print(f"latence : médiane {statistics.median(latences) * 1000:.0f} ms, "
              f"p95 {p95 * 1000:.0f} ms, max {latences[-1] * 1000:.0f} ms")
        if duree > 0:
            print(f"débit effectif : {(len(self.lignes) - 1) / duree:.2f} écritures/s")

    def enregistrer(self, nom: str) -> Path:
        DOSSIER_MESURES.mkdir(parents=True, exist_ok=True)
        chemin = DOSSIER_MESURES / f"{datetime.now():%Y%m%d-%H%M%S}-{nom}.csv"
        with chemin.open("w", newline="", encoding="utf-8") as fichier:
            sortie = csv.DictWriter(fichier, fieldnames=list(self.lignes[0]))
            sortie.writeheader()
            sortie.writerows(self.lignes)
        return chemin


async def rampe(tv: Televiseur, releve: Releve, phase: str, depart: int, cible: int,
                parametres: Parametres) -> None:
    """Comme l'orchestrateur : chaque pas attend sa confirmation, et une
    écriture non confirmée arrête la rampe."""
    r = Rampe(parametres, depart, time.monotonic())
    while (pas := r.prochain_pas(time.monotonic(), cible)) is not None:
        echeance, valeur = pas
        if (attente := echeance - time.monotonic()) > 0:
            await asyncio.sleep(attente)
        r.envoyer(time.monotonic(), valeur)
        if not await releve.ecrire(tv, phase, valeur):
            print("rampe arrêtée : écriture non confirmée")
            return
        r.confirmer(valeur)
    print(f"{phase} : {depart} → {cible} en {r.duree(time.monotonic()):.1f} s, "
          f"{r.pas_confirmes} pas")


async def soutenu(tv: Televiseur, releve: Releve, base: int, frequence: float,
                  duree: float) -> None:
    """±1 point autour de la valeur initiale, `frequence` écritures par
    seconde : charge d'une rampe longue, sans changement visible."""
    fin = time.monotonic() + duree
    prochaine, n = time.monotonic(), 0
    while time.monotonic() < fin:
        if (attente := prochaine - time.monotonic()) > 0:
            await asyncio.sleep(attente)
        valeur = base + 1 if n % 2 == 0 else base
        await releve.ecrire(tv, "soutenu", valeur)
        n += 1
        prochaine += 1 / frequence


async def principal(args) -> None:
    stockage = await StorageSqliteDict.create(KEY_DB)
    cle = await stockage.get_key(TV_IP)
    if not cle:
        sys.exit(f"Pas de clé d'appairage pour {TV_IP} dans {KEY_DB}.")
    tv = Televiseur(TV_IP, cle)
    releve = Releve()
    tv.abonner(releve.sur_evenement)
    await tv.demarrer()
    try:
        for _ in range(300):
            if tv.etat_connexion == "connecte" and tv.ecriture_possible is not None:
                break
            await asyncio.sleep(0.1)
        else:
            sys.exit("Téléviseur injoignable ou appairage refusé.")
        if not tv.ecriture_possible:
            sys.exit("Écriture refusée par le téléviseur (mode consultation).")
        initiale = int(tv.etat[CATEGORIE][CLE])
        print(f"mode d'image : {tv.mode_image} ; voie d'écriture : {tv.voie_ecriture} ; "
              f"{CLE} initial : {initiale}\n")
        try:
            if args.soutenu:
                await soutenu(tv, releve, min(initiale, 99), args.soutenu, args.duree)
                nom = f"soutenu-{args.soutenu:g}hz-{args.duree:g}s"
            else:
                parametres = Parametres(args.pas, args.debit)
                await releve.ecrire(tv, "position", args.de)
                await asyncio.sleep(2)
                await rampe(tv, releve, "montee", args.de, args.a, parametres)
                if args.retour:
                    await asyncio.sleep(2)
                    await rampe(tv, releve, "retour", args.a, args.de, parametres)
                nom = f"rampe-{args.de}-{args.a}-pas{args.pas}-debit{args.debit:g}"
        finally:
            await tv.ecrire(CATEGORIE, CLE, initiale)
            print(f"\n{CLE} restauré à {initiale}")
        releve.resume()
        if releve.lignes:
            print(f"relevé : {releve.enregistrer(nom)}")
    finally:
        await tv.arreter()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--de", type=int, default=40)
    parser.add_argument("--a", type=int, default=100)
    parser.add_argument("--retour", action="store_true", help="puis de --a à --de")
    parser.add_argument("--pas", type=int, default=1, help="points par pas")
    parser.add_argument("--debit", type=float, default=4, help="points par seconde")
    parser.add_argument("--soutenu", type=float, help="écritures par seconde, sans rampe")
    parser.add_argument("--duree", type=float, default=120, help="durée du mode soutenu (s)")
    try:
        asyncio.run(principal(parser.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
