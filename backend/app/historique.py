"""Historique des écritures en SQLite locale.

Chaque écriture réussie est enregistrée avec l'horodatage, l'entrée (id de
l'arbre si connue), la catégorie et la clé API, l'ancienne et la nouvelle
valeur (JSON), et le mode d'image actif au moment de l'écriture.
"""

import asyncio
import json
import sqlite3
import time
from pathlib import Path

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ecritures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    horodatage REAL NOT NULL,
    entree_id TEXT,
    categorie TEXT NOT NULL,
    cle TEXT NOT NULL,
    ancienne TEXT,
    nouvelle TEXT,
    mode_image TEXT
);
CREATE INDEX IF NOT EXISTS idx_ecritures_horodatage ON ecritures(horodatage);
"""


class Historique:
    def __init__(self, chemin: Path | None = None):
        self.chemin = chemin or config.HISTORIQUE_DB
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        with self._connexion() as co:
            co.executescript(_SCHEMA)

    def _connexion(self) -> sqlite3.Connection:
        co = sqlite3.connect(self.chemin)
        co.row_factory = sqlite3.Row
        return co

    def _enregistrer_sync(self, entree_id: str | None, categorie: str, cle: str,
                          ancienne, nouvelle, mode_image: str | None) -> int:
        with self._connexion() as co:
            cur = co.execute(
                "INSERT INTO ecritures (horodatage, entree_id, categorie, cle,"
                " ancienne, nouvelle, mode_image) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (time.time(), entree_id, categorie, cle,
                 json.dumps(ancienne, ensure_ascii=False),
                 json.dumps(nouvelle, ensure_ascii=False), mode_image),
            )
            return cur.lastrowid

    async def enregistrer(self, entree_id: str | None, categorie: str, cle: str,
                          ancienne, nouvelle, mode_image: str | None) -> int:
        return await asyncio.to_thread(
            self._enregistrer_sync, entree_id, categorie, cle,
            ancienne, nouvelle, mode_image)

    def _lister_sync(self, limite: int) -> list[dict]:
        with self._connexion() as co:
            lignes = co.execute(
                "SELECT * FROM ecritures ORDER BY id DESC LIMIT ?", (limite,)
            ).fetchall()
        return [
            {
                "id": ligne["id"],
                "horodatage": ligne["horodatage"],
                "entree_id": ligne["entree_id"],
                "categorie": ligne["categorie"],
                "cle": ligne["cle"],
                "ancienne": json.loads(ligne["ancienne"]),
                "nouvelle": json.loads(ligne["nouvelle"]),
                "mode_image": ligne["mode_image"],
            }
            for ligne in lignes
        ]

    async def lister(self, limite: int = 100) -> list[dict]:
        return await asyncio.to_thread(self._lister_sync, limite)
