"""Socle commun des scripts d'exploration de la phase 1.

La clé client est conservée dans data/bscpylgtv.sqlite (hors git) : le premier
appairage demande une confirmation sur l'écran du téléviseur, les exécutions
suivantes sont silencieuses.
"""

import asyncio
import os
import sys
from pathlib import Path

from bscpylgtv import WebOsClient
from bscpylgtv.storage_sqlitedict import StorageSqliteDict

TV_IP = os.environ.get("LG_TV_HOST") or sys.exit(
    "Renseigner l'adresse du téléviseur : LG_TV_HOST=<ip> python scripts/<script>.py")
KEY_DB = str(Path(__file__).resolve().parent.parent / "data" / "bscpylgtv.sqlite")
# Manifeste non signé de l'app : webOS 11 met en liste noire la signature du
# manifeste par défaut de bscpylgtv (cf. docs/incidents-ecriture.md).
MANIFESTE = str(Path(__file__).resolve().parents[2] / "custom_components" / "lg_webos_tv" / "manifeste-ssap.json")


async def make_client() -> WebOsClient:
    # states=[] : pas d'abonnements d'état automatiques, on ne veut que des
    # requêtes explicites pendant l'exploration.
    client = await WebOsClient.create(TV_IP, states=[], key_file_path=KEY_DB,
                                      manifest_file_path=MANIFESTE)
    await client.connect()
    return client


# Séance d'essais du lot 7 (docs/essais-lot7.md) : même chemin que
# l'intégration (`Televiseur` : voie directe ou pont createAlert, écriture
# confirmée par la notification ou par relecture).
RACINE = Path(__file__).resolve().parents[2]
DOSSIER_MESURES = RACINE / "outils" / "data" / "mesures"


async def televiseur_connecte(abonne=None, classe=None):
    """`Televiseur` connecté avec la clé de data/bscpylgtv.sqlite, écriture
    accordée ; `abonne` reçoit ses événements. Quitte sinon."""
    # Import tardif : la racine du dépôt n'est pas dans le chemin des
    # scripts de la phase 1.
    if str(RACINE) not in sys.path:
        sys.path.insert(0, str(RACINE))
    from custom_components.lg_webos_tv.televiseur import Televiseur

    stockage = await StorageSqliteDict.create(KEY_DB)
    cle = await stockage.get_key(TV_IP)
    if not cle:
        sys.exit(f"Pas de clé d'appairage pour {TV_IP} dans {KEY_DB}.")
    tv = (classe or Televiseur)(TV_IP, cle)
    if abonne is not None:
        tv.abonner(abonne)
    await tv.demarrer()
    for _ in range(300):
        if tv.etat_connexion == "connecte" and tv.ecriture_possible is not None:
            break
        await asyncio.sleep(0.1)
    else:
        await tv.arreter()
        sys.exit("Téléviseur injoignable ou appairage refusé.")
    if not tv.ecriture_possible:
        await tv.arreter()
        sys.exit("Écriture refusée par le téléviseur (mode consultation).")
    return tv


async def demander(question: str) -> str:
    """Saisie de l'utilisateur sans bloquer la boucle (notifications reçues
    pendant ce temps)."""
    return (await asyncio.to_thread(input, question)).strip()
