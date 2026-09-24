"""Diagnostic de l'enregistrement SSAP (incident firmware 43.21.77 / webOS 11).

bscpylgtv 0.5.2 ignore silencieusement un refus de la clé client au
`register` : il garde l'ancienne clé et la connexion « réussit » sur une
socket non enregistrée (toutes les requêtes répondent alors
`401 insufficient permissions (not registered)`). Ce script parle SSAP en
direct pour afficher les réponses brutes du téléviseur.

Usage :
  python scripts/diag_enregistrement.py            # register avec la clé stockée
  python scripts/diag_enregistrement.py --appairer # register sans clé : demande
                                                   # à accepter sur le téléviseur,
                                                   # nouvelle clé enregistrée dans
                                                   # data/bscpylgtv.sqlite
  python scripts/diag_enregistrement.py --non-signe
      manifeste sans partie signée (webOS 11 met en liste noire la signature
      de bscpylgtv) ; clé conservée à part dans data/diag-non-signe.sqlite.

Lecture seule côté réglages : seules des requêtes de lecture sont émises,
plus une sonde setSystemSettings sur une clé inexistante (rejetée avant
toute écriture) pour savoir si la permission WRITE_SETTINGS est accordée.
"""

import argparse
import asyncio
import json
import ssl
import time
from pathlib import Path

import websockets
from bscpylgtv.manifest import MANIFEST
from bscpylgtv.storage_sqlitedict import StorageSqliteDict

from common import KEY_DB, TV_IP

KEY_DB_NON_SIGNE = str(Path(KEY_DB).with_name("diag-non-signe.sqlite"))

ATTENTE_REPONSE_S = 180


def contexte_ssl() -> ssl.SSLContext:
    # Identique à bscpylgtv : certificat auto-signé du téléviseur.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def recevoir(ws, t0: float) -> dict:
    brut = await asyncio.wait_for(ws.recv(), timeout=ATTENTE_REPONSE_S)
    msg = json.loads(brut)
    print(f"[+{time.monotonic() - t0:6.1f} s] <- {json.dumps(msg, ensure_ascii=False)[:600]}")
    return msg


async def requete(ws, t0: float, ident: str, uri: str, charge: dict | None = None) -> dict:
    envoi = {"id": ident, "type": "request", "uri": f"ssap://{uri}"}
    if charge is not None:
        envoi["payload"] = charge
    print(f"-> {uri} {json.dumps(charge or {}, ensure_ascii=False)}")
    await ws.send(json.dumps(envoi))
    while True:
        msg = await recevoir(ws, t0)
        if msg.get("id") == ident:
            return msg


def manifeste_non_signe() -> dict:
    # Sans "signed"/"signatures", la passerelle ne garde que les permissions
    # non SECURE de la liste non signée (client-profile.js, loadUnsignedProperties).
    permissions = sorted(set(MANIFEST["permissions"])
                         | set(MANIFEST["signed"]["permissions"]))
    return {k: v for k, v in MANIFEST.items() if k not in ("signed", "signatures")} \
        | {"permissions": permissions}


async def main(appairer: bool, non_signe: bool) -> None:
    stockage = await StorageSqliteDict.create(KEY_DB_NON_SIGNE if non_signe else KEY_DB)
    manifeste = manifeste_non_signe() if non_signe else MANIFEST
    cle = None if appairer else await stockage.get_key(TV_IP)
    print(f"Clé stockée utilisée : {'aucune (appairage forcé)' if cle is None else cle[:6] + '…'}")

    async with websockets.connect(
        f"wss://{TV_IP}:3001", ssl=contexte_ssl(), ping_interval=None, max_size=None,
    ) as ws:
        t0 = time.monotonic()
        # webOS 11 (43.21.77) ne répond plus au hello : on ne l'attend pas
        # longtemps. bscpylgtv ne l'envoie pas par défaut (getHelloInfo).
        await ws.send(json.dumps({"id": "hello", "type": "hello"}))
        try:
            brut = await asyncio.wait_for(ws.recv(), timeout=3)
            print(f"hello <- {brut[:300]}")
        except asyncio.TimeoutError:
            print("hello : pas de réponse (3 s)")

        await ws.send(json.dumps({
            "type": "register", "id": "register_0",
            "payload": {"client-key": cle, "forcePairing": False,
                        "manifest": manifeste, "pairingType": "PROMPT"},
        }))
        if appairer:
            print("Demande d'appairage envoyée : l'accepter sur le téléviseur.")
        enregistre = False
        while True:
            msg = await recevoir(ws, t0)
            if msg.get("type") == "registered":
                nouvelle = msg["payload"].get("client-key")
                enregistre = True
                if nouvelle and nouvelle != cle:
                    await stockage.set_key(TV_IP, nouvelle)
                    print("Nouvelle clé enregistrée")
                break
            if msg.get("type") == "error":
                break
            # type "response" + pairingType PROMPT : on attend la décision.

        print(f"=== Enregistrement : {'OK' if enregistre else 'ÉCHEC'}")
        if not enregistre:
            return

        await requete(ws, t0, "sw", "com.webos.service.update/getCurrentSWInformation")
        await requete(ws, t0, "img", "settings/getSystemSettings",
                      {"category": "picture", "keys": ["pictureMode", "backlight"]})
        # Clé inexistante : la passerelle vérifie la permission avant de
        # transmettre ; si elle transmet, l'adaptateur rejette la clé.
        await requete(ws, t0, "ecr", "settings/setSystemSettings",
                      {"category": "picture", "settings": {"cleInexistanteDiag": 1}})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--appairer", action="store_true",
                        help="register sans clé : demande à accepter sur le téléviseur")
    parser.add_argument("--non-signe", action="store_true",
                        help="manifeste sans signature (clé stockée à part)")
    args = parser.parse_args()
    asyncio.run(main(args.appairer, args.non_signe))
