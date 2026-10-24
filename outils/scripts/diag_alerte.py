"""Diagnostic du pont createAlert → luna (firmware 43.x / webOS 11).

webOS 11 refuse `settings/setSystemSettings` aux manifestes non signés
(WRITE_SETTINGS est SECURE). `system.notifications/createAlert` et
`closeAlert` n'exigent en revanche que WRITE_NOTIFICATION_TOAST, de niveau
PROTECTED (interfaces com.webos.service.apiadapter*.interface du firmware) :
une alerte dont le `onclose` pointe vers
`luna://com.webos.settingsservice/setSystemSettings` fait exécuter
l'écriture par le téléviseur lui-même. La réponse de l'appel luna n'est pas
renvoyée : seule une relecture confirme l'effet.

Usage :
  python scripts/diag_alerte.py              # sonde + contraste ±1 puis restauré
  python scripts/diag_alerte.py --hors-plage # en plus : contraste à 999,
                                             # pour voir si le refus est muet

Écriture réversible sur le mode d'image en cours uniquement (affiché).
Clé d'appairage : celle de l'app (data/bscpylgtv.sqlite). Si une demande
d'appairage apparaît sur le téléviseur (permission ajoutée au manifeste),
l'accepter.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import websockets
from bscpylgtv.storage_sqlitedict import StorageSqliteDict

from common import KEY_DB, MANIFESTE, TV_IP
from diag_enregistrement import contexte_ssl, recevoir, requete

LUNA_SET = "luna://com.webos.settingsservice/setSystemSettings"
CLE = "contrast"
# L'appel luna est asynchrone : on relit plusieurs fois avant de conclure.
RELECTURES = 6
INTERVALLE_RELECTURE_S = 0.5


def manifeste() -> dict:
    m = json.loads(Path(MANIFESTE).read_text(encoding="utf-8"))
    m["permissions"] = sorted(set(m["permissions"]) | {"WRITE_NOTIFICATION_TOAST"})
    return m


async def lire(ws, t0, ident: str) -> dict:
    rep = await requete(ws, t0, ident, "settings/getSystemSettings",
                        {"category": "picture", "keys": ["pictureMode", CLE]})
    return rep.get("payload", {}).get("settings", {})


async def ecrire_par_alerte(ws, t0, ident: str, valeur) -> None:
    # Même charge que bscpylgtv.luna_request : bouton, onclose et onfail
    # pointent tous vers l'appel luna, par redondance.
    params = {"category": "picture", "settings": {CLE: valeur}}
    action = {"uri": LUNA_SET, "params": params}
    charge = {"message": " ",
              "buttons": [{"label": "", "onClick": LUNA_SET, "params": params}],
              "onclose": action, "onfail": action}
    rep = await requete(ws, t0, f"{ident}-crea", "system.notifications/createAlert", charge)
    alerte = rep.get("payload", {}).get("alertId")
    if alerte is None:
        print("=== createAlert refusé ou sans alertId")
        return
    await requete(ws, t0, f"{ident}-ferm", "system.notifications/closeAlert",
                  {"alertId": alerte})


async def attendre_valeur(ws, t0, ident: str, attendue) -> bool:
    for i in range(RELECTURES):
        await asyncio.sleep(INTERVALLE_RELECTURE_S)
        lu = await lire(ws, t0, f"{ident}-r{i}")
        if str(lu.get(CLE)) == str(attendue):
            print(f"=== Valeur {attendue} constatée après ~{(i + 1) * INTERVALLE_RELECTURE_S:.1f} s")
            return True
    print(f"=== Valeur {attendue} NON constatée après {RELECTURES * INTERVALLE_RELECTURE_S:.1f} s")
    return False


async def main(hors_plage: bool) -> None:
    stockage = await StorageSqliteDict.create(KEY_DB)
    cle = await stockage.get_key(TV_IP)
    print(f"Clé stockée : {'aucune' if cle is None else cle[:6] + '…'}")

    async with websockets.connect(
        f"wss://{TV_IP}:3001", ssl=contexte_ssl(), ping_interval=None, max_size=None,
    ) as ws:
        t0 = time.monotonic()
        await ws.send(json.dumps({
            "type": "register", "id": "register_0",
            "payload": {"client-key": cle, "forcePairing": False,
                        "manifest": manifeste(), "pairingType": "PROMPT"},
        }))
        while True:
            msg = await recevoir(ws, t0)
            if msg.get("type") == "registered":
                nouvelle = msg["payload"].get("client-key")
                if nouvelle and nouvelle != cle:
                    await stockage.set_key(TV_IP, nouvelle)
                    print("Nouvelle clé enregistrée")
                break
            if msg.get("type") == "error":
                print("=== Enregistrement : ÉCHEC")
                return
            print("En attente : accepter la demande sur le téléviseur si elle s'affiche.")

        # alertId inexistant : un refus de permission (401) signifie voie
        # fermée ; toute autre erreur, que la requête a atteint l'adaptateur.
        await requete(ws, t0, "sonde", "system.notifications/closeAlert",
                      {"alertId": "sondeDiagInexistante"})

        initial = await lire(ws, t0, "init")
        origine = initial.get(CLE)
        print(f"=== Mode d'image : {initial.get('pictureMode')} — {CLE} = {origine}")
        if origine is None:
            return
        cible = int(origine) + 1 if int(origine) < 100 else int(origine) - 1

        await ecrire_par_alerte(ws, t0, "ecr", cible)
        ok = await attendre_valeur(ws, t0, "ecr", cible)

        if hors_plage:
            await ecrire_par_alerte(ws, t0, "hp", 999)
            await attendre_valeur(ws, t0, "hp", 999)

        if ok or hors_plage:
            await ecrire_par_alerte(ws, t0, "rest", int(origine))
            await attendre_valeur(ws, t0, "rest", origine)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hors-plage", action="store_true",
                        help="tente aussi une valeur hors plage (999)")
    asyncio.run(main(parser.parse_args().hors_plage))
