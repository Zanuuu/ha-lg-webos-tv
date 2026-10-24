"""Vérifications préalables à l'intégration Home Assistant (phase 7, étape 0).

1. Connexion avec la seule clé client (`client_key=`), sans fichier de
   stockage : l'intégration gardera la clé dans son entrée de configuration,
   le stockage sqlitedict de bscpylgtv étant bloquant pour la boucle de HA.
2. Rafale d'écritures par le pont createAlert sur `backlight` : latence de
   chaque écriture confirmée par relecture, puis 10 écritures enchaînées sans
   attendre (aucune perdue ? valeur finale = dernière demandée ?). Calibre la
   file d'écriture coalescente.
3. Origine des changements : chaque notification d'abonnement est affichée
   avec son champ `caller`, pour distinguer nos écritures (alerte) d'un
   réglage fait à la télécommande ou par les réglages rapides, et repérer la
   cascade de valeurs qui suit un changement de mode d'image.

Usage :
  python scripts/diag_origine.py                    # tout
  python scripts/diag_origine.py --sans-rafale      # observation seule
  python scripts/diag_origine.py --observation 120  # durée d'observation (s)

Écritures réversibles, sur le mode d'image en cours uniquement : la valeur
initiale de `backlight` est restaurée en fin de rafale.
"""

import argparse
import asyncio
import json
import time

from bscpylgtv import WebOsClient
from bscpylgtv.storage_sqlitedict import StorageSqliteDict

from common import KEY_DB, MANIFESTE, TV_IP

LUNA_ECRITURE = "com.webos.settingsservice/setSystemSettings"
CLES = ["pictureMode", "backlight", "contrast", "brightness", "color", "sharpness"]
CLE = "backlight"
RELECTURES = 6
INTERVALLE_RELECTURE_S = 0.5
T0 = time.monotonic()


def horodatage() -> str:
    return f"[{time.monotonic() - T0:7.2f} s]"


async def lire(client) -> dict:
    rep = await client.request("settings/getSystemSettings",
                               {"category": "picture", "keys": CLES})
    return rep.get("settings", {})


async def ecrire(client, valeur: int) -> float:
    """Écriture par alerte ; renvoie la durée de l'appel createAlert/closeAlert."""
    debut = time.monotonic()
    try:
        await asyncio.wait_for(
            client.luna_request(LUNA_ECRITURE,
                                {"category": "picture", "settings": {CLE: valeur}}),
            timeout=5.0)
    except asyncio.TimeoutError:
        print(f"{horodatage()} closeAlert sans réponse en 5 s ({CLE}={valeur})")
    return time.monotonic() - debut


async def attendre(client, attendue: int) -> float | None:
    """Délai jusqu'à ce que la relecture retrouve la valeur, None sinon."""
    debut = time.monotonic()
    for _ in range(RELECTURES):
        await asyncio.sleep(INTERVALLE_RELECTURE_S)
        if str((await lire(client)).get(CLE)) == str(attendue):
            return time.monotonic() - debut
    return None


async def rafale(client, notifiees: list) -> None:
    initial = await lire(client)
    origine = int(initial[CLE])
    print(f"\n=== Rafale — mode d'image {initial.get('pictureMode')}, "
          f"{CLE} initial = {origine}")
    sens = 1 if origine <= 90 else -1

    print("--- 10 écritures confirmées une à une")
    for i in range(1, 11):
        cible = origine + sens * (i % 6)
        duree_appel = await ecrire(client, cible)
        delai = await attendre(client, cible)
        etat = f"relue après {delai:.1f} s" if delai is not None else "NON relue"
        print(f"{horodatage()} {CLE}={cible} : appel {duree_appel:.2f} s, {etat}")

    print("--- 10 écritures enchaînées sans attendre la relecture")
    notifiees.clear()
    cibles = [origine + sens * k for k in (1, 2, 3, 4, 5, 4, 3, 2, 1, 3)]
    debut = time.monotonic()
    for cible in cibles:
        await ecrire(client, cible)
    print(f"{horodatage()} 10 appels en {time.monotonic() - debut:.2f} s")
    delai = await attendre(client, cibles[-1])
    print(f"{horodatage()} valeur finale {cibles[-1]} "
          + (f"relue après {delai:.1f} s" if delai is not None else "NON relue"))
    await asyncio.sleep(2)
    print(f"Valeurs notifiées pendant l'enchaînement : {notifiees}")
    print(f"Valeurs demandées                         : {cibles}")

    await ecrire(client, origine)
    delai = await attendre(client, origine)
    print(f"{horodatage()} restauration {CLE}={origine} : "
          + ("OK" if delai is not None else "NON confirmée, à vérifier sur la TV"))


async def main(sans_rafale: bool, duree_observation: int) -> None:
    stockage = await StorageSqliteDict.create(KEY_DB)
    cle = await stockage.get_key(TV_IP)
    if cle is None:
        raise SystemExit("Aucune clé client : lancer d'abord diag_alerte.py pour appairer.")

    # Sans key_file_path : bscpylgtv ne doit pas ouvrir son stockage quand
    # la clé est fournie.
    client = await WebOsClient.create(TV_IP, states=[], client_key=cle,
                                      manifest_file_path=MANIFESTE)
    await client.connect()
    lu = await lire(client)
    print(f"=== Connexion avec client_key seul : "
          f"{'OK' if lu else 'ÉCHEC'} (stockage ouvert : {client.storage is not None})")

    notifiees: list = []

    async def rappel(charge: dict) -> None:
        reglages = charge.get("settings") or {}
        if CLE in reglages:
            notifiees.append(reglages[CLE])
        autres = {k: v for k, v in charge.items() if k != "settings"}
        print(f"{horodatage()} notification {json.dumps(reglages, ensure_ascii=False)}"
              f" | hors settings : {json.dumps(autres, ensure_ascii=False)}")

    await client.subscribe(rappel, "settings/getSystemSettings",
                           {"category": "picture", "keys": CLES})

    try:
        if not sans_rafale:
            await rafale(client, notifiees)

        print(f"\n=== Observation pendant {duree_observation} s. Sur le téléviseur :")
        print("  1. changer la luminosité OLED à la télécommande (menu Image) ;")
        print("  2. changer le mode d'image par les réglages rapides ;")
        print("  3. remettre le mode d'image et la luminosité d'origine.")
        await asyncio.sleep(duree_observation)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sans-rafale", action="store_true")
    parser.add_argument("--observation", type=int, default=90,
                        help="durée d'observation des changements manuels (s)")
    args = parser.parse_args()
    asyncio.run(main(args.sans_rafale, args.observation))
