"""Presets : instantané nommé des réglages accessibles en écriture, stocké en
SQLite, exportable/importable en JSON (GET/POST renvoient et acceptent
directement la structure stockée).

Les réglages de la catégorie picture (hors sélection du mode elle-même) sont
propres au mode d'image actif au moment de la capture : ce mode est
enregistré avec chacun (`mode_image`), et l'application du preset ne les
réécrit que si ce même mode est actif au moment de la restauration — voir
`restauration.appliquer_preset`.
"""

import asyncio
import json
import sqlite3
import time
from pathlib import Path

from . import arbre, config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS presets (
    nom TEXT PRIMARY KEY,
    cree_le REAL NOT NULL,
    donnees TEXT NOT NULL
);
"""


class PresetExistant(Exception):
    pass


class PresetInconnu(Exception):
    pass


def capturer_snapshot(reglages: dict, mode_image: str | None,
                      entree_ids: list[str] | None = None) -> list[dict]:
    """Instantané des entrées pilotables dont la valeur est actuellement
    connue. `entree_ids` restreint la capture à un sous-ensemble choisi ;
    None capture l'ensemble des entrées pilotables de l'arbre.

    `arbre.entrees_pilotables()` n'inclut que les clés dont l'écriture a été
    confirmée sûre (cf. docs/incidents-ecriture.md pour les clés retirées
    après un effet de bord constaté, ex. `option.country`)."""
    pilotables = arbre.entrees_pilotables()
    if entree_ids is not None:
        voulues = set(entree_ids)
        pilotables = [e for e in pilotables if e["id"] in voulues]

    snapshot = []
    for entree in pilotables:
        api = entree["api"]
        valeur = reglages.get(api["categorie"], {}).get(api["cle"])
        if valeur is None:
            continue
        mode = mode_image if arbre.mode_dependant(api["categorie"], api["cle"]) else None
        snapshot.append({
            "entree_id": entree["id"], "categorie": api["categorie"],
            "cle": api["cle"], "valeur": valeur, "mode_image": mode,
        })
    return snapshot


class Presets:
    def __init__(self, chemin: Path | None = None):
        self.chemin = chemin or config.PRESETS_DB
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        with self._connexion() as co:
            co.executescript(_SCHEMA)

    def _connexion(self) -> sqlite3.Connection:
        co = sqlite3.connect(self.chemin)
        co.row_factory = sqlite3.Row
        return co

    def _sauvegarder_sync(self, nom: str, entrees: list[dict], remplacer: bool) -> dict:
        with self._connexion() as co:
            if not remplacer:
                existe = co.execute("SELECT 1 FROM presets WHERE nom = ?", (nom,)).fetchone()
                if existe:
                    raise PresetExistant(nom)
            cree_le = time.time()
            co.execute(
                "INSERT INTO presets (nom, cree_le, donnees) VALUES (?, ?, ?)"
                " ON CONFLICT(nom) DO UPDATE SET cree_le = excluded.cree_le,"
                " donnees = excluded.donnees",
                (nom, cree_le, json.dumps({"entrees": entrees}, ensure_ascii=False)),
            )
            return {"nom": nom, "cree_le": cree_le, "entrees": entrees}

    async def sauvegarder(self, nom: str, entrees: list[dict], remplacer: bool = False) -> dict:
        return await asyncio.to_thread(self._sauvegarder_sync, nom, entrees, remplacer)

    def _lister_sync(self) -> list[dict]:
        with self._connexion() as co:
            lignes = co.execute(
                "SELECT nom, cree_le, donnees FROM presets ORDER BY nom"
            ).fetchall()
        return [
            {"nom": l["nom"], "cree_le": l["cree_le"],
             "nombre_reglages": len(json.loads(l["donnees"])["entrees"])}
            for l in lignes
        ]

    async def lister(self) -> list[dict]:
        return await asyncio.to_thread(self._lister_sync)

    def _recuperer_sync(self, nom: str) -> dict | None:
        with self._connexion() as co:
            ligne = co.execute(
                "SELECT nom, cree_le, donnees FROM presets WHERE nom = ?", (nom,)
            ).fetchone()
        if ligne is None:
            return None
        return {"nom": ligne["nom"], "cree_le": ligne["cree_le"],
                **json.loads(ligne["donnees"])}

    async def recuperer(self, nom: str) -> dict | None:
        return await asyncio.to_thread(self._recuperer_sync, nom)

    def _supprimer_sync(self, nom: str) -> bool:
        with self._connexion() as co:
            return co.execute("DELETE FROM presets WHERE nom = ?", (nom,)).rowcount > 0

    async def supprimer(self, nom: str) -> bool:
        return await asyncio.to_thread(self._supprimer_sync, nom)
