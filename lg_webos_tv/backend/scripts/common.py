"""Socle commun des scripts d'exploration de la phase 1.

La clé client est conservée dans data/bscpylgtv.sqlite (hors git) : le premier
appairage demande une confirmation sur l'écran du téléviseur, les exécutions
suivantes sont silencieuses.
"""

import os
import sys
from pathlib import Path

from bscpylgtv import WebOsClient

TV_IP = os.environ.get("LG_TV_HOST") or sys.exit(
    "Renseigner l'adresse du téléviseur : LG_TV_HOST=<ip> python scripts/<script>.py")
KEY_DB = str(Path(__file__).resolve().parent.parent.parent / "data" / "bscpylgtv.sqlite")
# Manifeste non signé de l'app : webOS 11 met en liste noire la signature du
# manifeste par défaut de bscpylgtv (cf. docs/incidents-ecriture.md).
MANIFESTE = str(Path(__file__).resolve().parents[3] / "custom_components" / "lg_webos_tv" / "manifeste-ssap.json")


async def make_client() -> WebOsClient:
    # states=[] : pas d'abonnements d'état automatiques, on ne veut que des
    # requêtes explicites pendant l'exploration.
    client = await WebOsClient.create(TV_IP, states=[], key_file_path=KEY_DB,
                                      manifest_file_path=MANIFESTE)
    await client.connect()
    return client
