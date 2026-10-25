"""Corrections de la luminosité adaptative en SQLite locale
(docs/etude-luminosite-adaptative.md, § 3.8 et 5.1, lot 5).

Une ligne par correction retenue (reprise.SuiviCorrection), rattachée au
capteur : le lux d'un autre capteur n'est pas comparable. Même fichier que
l'historique des écritures, donc dans les sauvegardes de Home Assistant.
Conservées un an, 500 au plus.

L'entrée HDMI n'est pas enregistrée : l'intégration ne la connaît pas (il
faudrait un abonnement de plus au téléviseur). Une colonne s'ajoutera le
jour où elle sera suivie.
"""

import asyncio
import sqlite3
import time
from pathlib import Path

from .reprise import CONSERVATION_JOURS, CORRECTIONS_MAX, Correction

_SCHEMA = """
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    horodatage REAL NOT NULL,
    capteur TEXT NOT NULL,
    lux REAL NOT NULL,
    valeur INTEGER NOT NULL,
    cible INTEGER NOT NULL,
    mode_image TEXT,
    origine TEXT,
    ecartee INTEGER NOT NULL DEFAULT 0,
    decalage INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_corrections_capteur ON corrections(capteur, horodatage);
"""


class CorrectionsLuminosite:
    def __init__(self, chemin: Path):
        self.chemin = chemin
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        with self._connexion() as co:
            co.executescript(_SCHEMA)
            # Base de la 2.9.0 : le décalage pilotable n'existait pas (0).
            colonnes = {ligne["name"] for ligne in co.execute("PRAGMA table_info(corrections)")}
            if "decalage" not in colonnes:
                co.execute("ALTER TABLE corrections"
                           " ADD COLUMN decalage INTEGER NOT NULL DEFAULT 0")

    def _connexion(self) -> sqlite3.Connection:
        co = sqlite3.connect(self.chemin)
        co.row_factory = sqlite3.Row
        return co

    def _ajouter_sync(self, capteur: str, c: Correction) -> int:
        with self._connexion() as co:
            return co.execute(
                "INSERT INTO corrections (horodatage, capteur, lux, valeur, cible,"
                " mode_image, origine, ecartee, decalage) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (c.horodatage, capteur, c.lux, c.valeur, c.cible, c.mode_image, c.origine,
                 int(c.ecartee), c.decalage)).lastrowid

    async def ajouter(self, capteur: str, correction: Correction) -> int:
        return await asyncio.to_thread(self._ajouter_sync, capteur, correction)

    def _charger_sync(self, capteur: str) -> list[Correction]:
        with self._connexion() as co:
            lignes = co.execute(
                "SELECT * FROM corrections WHERE capteur = ? ORDER BY horodatage",
                (capteur,)).fetchall()
        return [Correction(horodatage=ligne["horodatage"], lux=ligne["lux"],
                           valeur=ligne["valeur"], cible=ligne["cible"],
                           mode_image=ligne["mode_image"], origine=ligne["origine"],
                           id=ligne["id"], ecartee=bool(ligne["ecartee"]),
                           decalage=ligne["decalage"]) for ligne in lignes]

    async def charger(self, capteur: str) -> list[Correction]:
        return await asyncio.to_thread(self._charger_sync, capteur)

    def _oublier_sync(self, id_: int) -> bool:
        with self._connexion() as co:
            return co.execute("DELETE FROM corrections WHERE id = ?", (id_,)).rowcount > 0

    async def oublier(self, id_: int) -> bool:
        """Retire une correction ; renvoie False si elle n'existe pas."""
        return await asyncio.to_thread(self._oublier_sync, id_)

    def _ecarter_sync(self, ids: list[int]) -> None:
        with self._connexion() as co:
            co.executemany("UPDATE corrections SET ecartee = 1 WHERE id = ?",
                           [(id_,) for id_ in ids])

    async def ecarter(self, ids: list[int]) -> None:
        """Corrections écartées des suggestions (« Ignorer »), gardées à
        l'affichage."""
        await asyncio.to_thread(self._ecarter_sync, ids)

    def _purger_sync(self, maintenant: float) -> int:
        with self._connexion() as co:
            retirees = co.execute("DELETE FROM corrections WHERE horodatage < ?",
                                  (maintenant - CONSERVATION_JOURS * 86400,)).rowcount
            retirees += co.execute(
                "DELETE FROM corrections WHERE id NOT IN (SELECT id FROM corrections"
                " ORDER BY horodatage DESC, id DESC LIMIT ?)", (CORRECTIONS_MAX,)).rowcount
        return retirees

    async def purger(self, maintenant: float | None = None) -> int:
        """Au-delà d'un an, puis au-delà des 500 plus récentes, tous capteurs
        confondus ; renvoie le nombre de lignes retirées."""
        return await asyncio.to_thread(
            self._purger_sync, time.time() if maintenant is None else maintenant)
