"""Statistiques journalières de la luminosité adaptative en SQLite locale
(docs/etude-luminosite-adaptative.md, § 3.9 et 5.1, lot 3).

Une ligne par jour et par capteur : changer de capteur ne mélange pas les
mesures (cadence, résolution, rétroaction lui sont propres). Les agrégats
sont en JSON (sante.StatsJour) : un champ ajouté plus tard ne demande pas de
migration. Même fichier que l'historique des écritures, donc dans les
sauvegardes de Home Assistant ; calculées par la fonction elle-même, sans
dépendre du recorder, que l'utilisateur peut avoir restreint.
"""

import asyncio
import json
import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stats_luminosite (
    jour TEXT NOT NULL,
    capteur TEXT NOT NULL,
    donnees TEXT NOT NULL,
    maj REAL NOT NULL,
    PRIMARY KEY (jour, capteur)
);
"""


class StatsLuminosite:
    def __init__(self, chemin: Path):
        self.chemin = chemin
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        with self._connexion() as co:
            co.executescript(_SCHEMA)

    def _connexion(self) -> sqlite3.Connection:
        return sqlite3.connect(self.chemin)

    def _enregistrer_sync(self, capteur: str, jours: list[dict]) -> None:
        with self._connexion() as co:
            co.executemany(
                "INSERT INTO stats_luminosite (jour, capteur, donnees, maj)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT (jour, capteur) DO UPDATE SET"
                " donnees = excluded.donnees, maj = excluded.maj",
                [(jour["jour"], capteur, json.dumps(jour, ensure_ascii=False), time.time())
                 for jour in jours])

    async def enregistrer(self, capteur: str, jours: list[dict]) -> None:
        """Remplace les agrégats de ces jours (dicts de StatsJour)."""
        await asyncio.to_thread(self._enregistrer_sync, capteur, jours)

    def _charger_sync(self, capteur: str, depuis: str) -> list[dict]:
        with self._connexion() as co:
            lignes = co.execute(
                "SELECT donnees FROM stats_luminosite WHERE capteur = ? AND jour >= ?"
                " ORDER BY jour", (capteur, depuis)).fetchall()
        return [json.loads(donnees) for (donnees,) in lignes]

    async def charger(self, capteur: str, depuis: str) -> list[dict]:
        return await asyncio.to_thread(self._charger_sync, capteur, depuis)

    def _purger_sync(self, avant: str) -> int:
        with self._connexion() as co:
            return co.execute("DELETE FROM stats_luminosite WHERE jour < ?", (avant,)).rowcount

    async def purger(self, avant: str) -> int:
        """Retire les jours antérieurs à `avant`, tous capteurs confondus ;
        renvoie le nombre de lignes retirées."""
        return await asyncio.to_thread(self._purger_sync, avant)
