"""Socle commun des scripts d'exploration de la phase 1.

La clé client est conservée dans data/bscpylgtv.sqlite (hors git) : le premier
appairage demande une confirmation sur l'écran du téléviseur, les exécutions
suivantes sont silencieuses.
"""

from pathlib import Path

from bscpylgtv import WebOsClient

TV_IP = "192.168.1.50"
KEY_DB = str(Path(__file__).resolve().parent.parent.parent / "data" / "bscpylgtv.sqlite")


async def make_client() -> WebOsClient:
    # states=[] : pas d'abonnements d'état automatiques, on ne veut que des
    # requêtes explicites pendant l'exploration.
    client = await WebOsClient.create(TV_IP, states=[], key_file_path=KEY_DB)
    await client.connect()
    return client
