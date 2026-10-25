"""Historique des écritures en SQLite locale.

Chaque écriture réussie est enregistrée avec l'horodatage, l'entrée (id de
l'arbre si connue), la catégorie et la clé API, l'ancienne et la nouvelle
valeur (JSON), le mode d'image actif au moment de l'écriture, et son
origine (ORIGINES).
"""

import asyncio
import json
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

# D'où vient une écriture : réglage depuis une entité ou une action Home
# Assistant, depuis le panneau, application d'un preset, retour arrière,
# luminosité adaptative.
ORIGINES = ("home_assistant", "panneau", "preset", "annulation",
            "luminosite_adaptative")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ecritures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    horodatage REAL NOT NULL,
    entree_id TEXT,
    categorie TEXT NOT NULL,
    cle TEXT NOT NULL,
    ancienne TEXT,
    nouvelle TEXT,
    mode_image TEXT,
    origine TEXT
);
CREATE INDEX IF NOT EXISTS idx_ecritures_horodatage ON ecritures(horodatage);
"""


class Historique:
    def __init__(self, chemin: Path):
        self.chemin = chemin
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        with self._connexion() as co:
            co.executescript(_SCHEMA)
        # Prévenus après chaque écriture enregistrée : seul point qui voit
        # toutes les écritures avec leur origine, presets et retours arrière
        # compris (luminosité adaptative).
        self._ecouteurs: list[Callable[[dict], None]] = []

    def ecouter(self, ecouteur: Callable[[dict], None]) -> Callable[[], None]:
        """Abonne `ecouteur` aux écritures enregistrées ; renvoie de quoi le
        désabonner."""
        self._ecouteurs.append(ecouteur)
        return lambda: self._ecouteurs.remove(ecouteur)

    def _connexion(self) -> sqlite3.Connection:
        co = sqlite3.connect(self.chemin)
        co.row_factory = sqlite3.Row
        return co

    def _enregistrer_sync(self, entree_id: str | None, categorie: str, cle: str,
                          ancienne, nouvelle, mode_image: str | None,
                          origine: str) -> int:
        with self._connexion() as co:
            cur = co.execute(
                "INSERT INTO ecritures (horodatage, entree_id, categorie, cle,"
                " ancienne, nouvelle, mode_image, origine)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (time.time(), entree_id, categorie, cle,
                 json.dumps(ancienne, ensure_ascii=False),
                 json.dumps(nouvelle, ensure_ascii=False), mode_image, origine),
            )
            return cur.lastrowid

    async def enregistrer(self, entree_id: str | None, categorie: str, cle: str,
                          ancienne, nouvelle, mode_image: str | None,
                          origine: str) -> int:
        id_ = await asyncio.to_thread(
            self._enregistrer_sync, entree_id, categorie, cle,
            ancienne, nouvelle, mode_image, origine)
        ecriture = {"id": id_, "entree_id": entree_id, "categorie": categorie,
                    "cle": cle, "nouvelle": nouvelle, "mode_image": mode_image,
                    "origine": origine}
        for ecouteur in list(self._ecouteurs):
            ecouteur(ecriture)
        return id_

    def _completer_sync(self, id_: int, nouvelle) -> dict | None:
        with self._connexion() as co:
            co.execute("UPDATE ecritures SET nouvelle = ? WHERE id = ?",
                       (json.dumps(nouvelle, ensure_ascii=False), id_))
        return self._recuperer_sync(id_)

    async def completer(self, id_: int, nouvelle) -> None:
        """Nouvelle valeur d'une entrée : arrivée d'une rampe de la
        luminosité adaptative, dont seul le premier pas a été enregistré (à
        sa place parmi les autres écritures)."""
        ligne = await asyncio.to_thread(self._completer_sync, id_, nouvelle)
        if ligne is not None:
            for ecouteur in list(self._ecouteurs):
                ecouteur(ligne)

    def _lister_sync(self, limite: int) -> list[dict]:
        with self._connexion() as co:
            lignes = co.execute(
                "SELECT * FROM ecritures ORDER BY id DESC LIMIT ?", (limite,)
            ).fetchall()
        return [self._ligne_vers_dict(ligne) for ligne in lignes]

    async def lister(self, limite: int = 100) -> list[dict]:
        return await asyncio.to_thread(self._lister_sync, limite)

    @staticmethod
    def _ligne_vers_dict(ligne: sqlite3.Row) -> dict:
        return {
            "id": ligne["id"],
            "horodatage": ligne["horodatage"],
            "entree_id": ligne["entree_id"],
            "categorie": ligne["categorie"],
            "cle": ligne["cle"],
            "ancienne": json.loads(ligne["ancienne"]),
            "nouvelle": json.loads(ligne["nouvelle"]),
            "mode_image": ligne["mode_image"],
            "origine": ligne["origine"],
        }

    def _recuperer_sync(self, id_: int) -> dict | None:
        with self._connexion() as co:
            ligne = co.execute(
                "SELECT * FROM ecritures WHERE id = ?", (id_,)
            ).fetchone()
        return self._ligne_vers_dict(ligne) if ligne else None

    async def recuperer(self, id_: int) -> dict | None:
        return await asyncio.to_thread(self._recuperer_sync, id_)

    def _lister_depuis_sync(self, horodatage: float) -> list[dict]:
        with self._connexion() as co:
            lignes = co.execute(
                "SELECT * FROM ecritures WHERE horodatage > ? ORDER BY horodatage DESC",
                (horodatage,),
            ).fetchall()
        return [self._ligne_vers_dict(ligne) for ligne in lignes]

    async def lister_depuis(self, horodatage: float) -> list[dict]:
        """Écritures postérieures à `horodatage`, les plus récentes d'abord —
        base du retour à un instant donné (restauration.revenir_a)."""
        return await asyncio.to_thread(self._lister_depuis_sync, horodatage)
