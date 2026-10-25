"""Statistiques journalières de la luminosité adaptative en SQLite locale
(docs/etude-luminosite-adaptative.md, § 3.9 et 5.1, lot 3).

Une ligne par jour et par capteur : changer de capteur ne mélange pas les
mesures (cadence, résolution, rétroaction lui sont propres). Les agrégats
sont en JSON (sante.StatsJour) : un champ ajouté plus tard ne demande pas de
migration. Même fichier que l'historique des écritures, donc dans les
sauvegardes de Home Assistant ; calculées par la fonction elle-même, sans
dépendre du recorder, que l'utilisateur peut avoir restreint.

Même base, le rapport appris entre le capteur principal et son secours
(secours.RapportCapteurs, lot 6) : une ligne par paire, pour qu'un
redémarrage ne fasse pas tout réapprendre, ni le retour à une paire déjà
vue.
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
CREATE TABLE IF NOT EXISTS rapport_capteurs (
    principal TEXT NOT NULL,
    secours TEXT NOT NULL,
    echantillons TEXT NOT NULL,
    maj REAL NOT NULL,
    PRIMARY KEY (principal, secours)
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

    def _enregistrer_rapport_sync(self, principal: str, secours: str,
                                  echantillons: list) -> None:
        with self._connexion() as co:
            co.execute(
                "INSERT INTO rapport_capteurs (principal, secours, echantillons, maj)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT (principal, secours) DO UPDATE SET"
                " echantillons = excluded.echantillons, maj = excluded.maj",
                (principal, secours, json.dumps(echantillons), time.time()))

    async def enregistrer_rapport(self, principal: str, secours: str,
                                  echantillons: list) -> None:
        """Échantillons du rapport entre les deux capteurs
        (secours.RapportCapteurs.en_liste)."""
        await asyncio.to_thread(self._enregistrer_rapport_sync, principal, secours,
                                echantillons)

    def _charger_rapport_sync(self, principal: str, secours: str) -> list:
        with self._connexion() as co:
            ligne = co.execute(
                "SELECT echantillons FROM rapport_capteurs WHERE principal = ? AND secours = ?",
                (principal, secours)).fetchone()
        return json.loads(ligne[0]) if ligne else []

    async def charger_rapport(self, principal: str, secours: str) -> list:
        return await asyncio.to_thread(self._charger_rapport_sync, principal, secours)
