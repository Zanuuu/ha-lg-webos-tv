"""File d'écriture coalescente vers le téléviseur.

Toutes les écritures venues de Home Assistant (entités, actions, panneau)
passent par une seule file : elles sont exécutées une à une, et pour une même
entrée de l'arbre seule la dernière valeur demandée est envoyée. Le
téléviseur applique sans perte des écritures enchaînées (docs/rapport-api.md,
phase 7) ; la coalescence évite seulement d'envoyer des valeurs
intermédiaires devenues inutiles quand un curseur ou une automatisation
change la valeur plus vite qu'elle ne s'écrit. Chaque demandeur reçoit le
résultat de l'écriture qui a effectivement eu lieu.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

# (entree_id, valeur, origine, mode_attendu) → résultat de restauration.ecrire
Ecrire = Callable[[str, Any, str, str | None], Awaitable[dict]]


class FileEcritures:
    def __init__(self, ecrire: Ecrire):
        self._ecrire = ecrire
        # Entrée → (paramètres de la dernière demande, futurs des
        # demandeurs), dans l'ordre d'arrivée de la première demande.
        self._en_attente: dict[str, tuple[tuple, list[asyncio.Future]]] = {}
        self._travailleur: asyncio.Task | None = None

    async def demander(self, entree_id: str, valeur: Any, origine: str,
                       mode_attendu: str | None = None) -> dict:
        """Écrit `valeur` (ou une valeur plus récente demandée entre-temps
        pour la même entrée) et renvoie le résultat de restauration.ecrire."""
        futur = asyncio.get_running_loop().create_future()
        parametres = (valeur, origine, mode_attendu)
        if entree_id in self._en_attente:
            _, futurs = self._en_attente[entree_id]
            self._en_attente[entree_id] = (parametres, [*futurs, futur])
        else:
            self._en_attente[entree_id] = (parametres, [futur])
        if self._travailleur is None or self._travailleur.done():
            self._travailleur = asyncio.create_task(self._travailler())
        return await futur

    async def _travailler(self) -> None:
        while self._en_attente:
            entree_id = next(iter(self._en_attente))
            parametres, futurs = self._en_attente.pop(entree_id)
            try:
                resultat = await self._ecrire(entree_id, *parametres)
            except asyncio.CancelledError:
                for futur in futurs:
                    futur.cancel()
                raise
            except Exception as exc:  # noqa: BLE001 — transmis aux demandeurs
                for futur in futurs:
                    if not futur.done():
                        futur.set_exception(exc)
                continue
            for futur in futurs:
                if not futur.done():
                    futur.set_result(resultat)

    async def arreter(self) -> None:
        if self._travailleur is not None:
            self._travailleur.cancel()
            try:
                await self._travailleur
            except asyncio.CancelledError:
                pass
        for _, futurs in self._en_attente.values():
            for futur in futurs:
                futur.cancel()
        self._en_attente.clear()
