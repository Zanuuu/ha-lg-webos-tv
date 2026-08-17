"""Accès au téléviseur — SEUL module autorisé à importer bscpylgtv.

Responsabilités :
- connexion et reconnexion automatique (le téléviseur peut être éteint) ;
- abonnements aux changements de réglages par catégorie (validés en phase 1) ;
- cache de l'état courant, avec normalisation des types (les notifications
  livrent parfois les nombres sous forme de chaînes, cf. rapport phase 1) ;
- écriture d'un réglage puis relecture de confirmation ;
- diffusion des événements (changements, état de connexion) aux abonnés
  internes (canal WebSocket du frontend, historique).
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from bscpylgtv import WebOsClient
from bscpylgtv.exceptions import PyLGTVCmdException

from . import config

log = logging.getLogger(__name__)

# Événements diffusés aux abonnés internes :
#   {"type": "connexion", "etat": "connecte" | "deconnecte" | "connexion"}
#   {"type": "changement", "categorie": str, "reglages": {cle: valeur}}
Abonne = Callable[[dict], Awaitable[None]]


def _cles_lisibles_par_categorie() -> dict[str, list[str]]:
    """Clés lisibles par catégorie, depuis l'inventaire de la phase 1."""
    inventaire = json.loads(config.INVENTAIRE.read_text())
    return {
        categorie: sorted(entree["lisibles"].keys())
        for categorie, entree in inventaire["categories"].items()
        if entree["lisibles"]
    }


def _normaliser(ancienne: Any, nouvelle: Any) -> Any:
    """Aligne le type d'une valeur notifiée sur celui de la valeur en cache.

    Les notifications d'abonnement livrent les nombres en chaînes
    (`"contrast": "85"`), la lecture directe en entiers.
    """
    if isinstance(ancienne, int) and not isinstance(ancienne, bool) \
            and isinstance(nouvelle, str):
        try:
            return int(nouvelle)
        except ValueError:
            return nouvelle
    return nouvelle


class Televiseur:
    def __init__(self, hote: str | None = None,
                 fabrique_client: Callable[..., Awaitable] | None = None):
        self.hote = hote or config.TV_HOST
        # Point d'injection pour les tests : les vrais appels passent par
        # WebOsClient.create.
        self._fabrique_client = fabrique_client or self._creer_client
        self.client = None
        self.etat_connexion = "deconnecte"
        self.etat: dict[str, dict[str, Any]] = {}
        self._abonnes: list[Abonne] = []
        self._cles = _cles_lisibles_par_categorie()
        self._tache: asyncio.Task | None = None
        self._verrou_ecriture = asyncio.Lock()

    # ------------------------------------------------------------------ cycle
    async def _creer_client(self):
        client = await WebOsClient.create(
            self.hote, states=[], key_file_path=str(config.CLE_TV_DB),
        )
        await client.connect()
        return client

    async def demarrer(self) -> None:
        self._tache = asyncio.create_task(self._boucle_connexion())

    async def arreter(self) -> None:
        if self._tache:
            self._tache.cancel()
            try:
                await self._tache
            except asyncio.CancelledError:
                pass
        await self._deconnecter()

    async def _deconnecter(self) -> None:
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:  # noqa: BLE001 — la fermeture ne doit pas lever
                pass
            self.client = None
        await self._changer_etat("deconnecte")

    async def _boucle_connexion(self) -> None:
        delai = config.RECONNEXION_DELAI_MIN_S
        while True:
            await self._changer_etat("connexion")
            try:
                self.client = await self._fabrique_client()
            except Exception as exc:  # noqa: BLE001 — TV éteinte, réseau…
                log.info("Connexion au téléviseur impossible : %s", exc)
                self.client = None
                await self._changer_etat("deconnecte")
                await asyncio.sleep(delai)
                delai = min(delai * 2, config.RECONNEXION_DELAI_MAX_S)
                continue

            delai = config.RECONNEXION_DELAI_MIN_S
            try:
                await self._souscrire_tout()
                await self._changer_etat("connecte")
                # La tâche de connexion du client vit tant que le lien tient ;
                # sa fin signale la déconnexion.
                tache_lien = getattr(self.client, "connect_task", None)
                if tache_lien is not None:
                    await asyncio.wait([tache_lien])
                else:  # client de test sans tâche de fond
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("Connexion au téléviseur perdue : %s", exc)
            await self._deconnecter()
            await asyncio.sleep(config.RECONNEXION_DELAI_MIN_S)

    # ------------------------------------------------------------- diffusion
    def abonner(self, abonne: Abonne) -> None:
        self._abonnes.append(abonne)

    def desabonner(self, abonne: Abonne) -> None:
        if abonne in self._abonnes:
            self._abonnes.remove(abonne)

    async def _diffuser(self, evenement: dict) -> None:
        for abonne in list(self._abonnes):
            try:
                await abonne(evenement)
            except Exception:  # noqa: BLE001 — un abonné défaillant n'arrête pas les autres
                log.exception("Abonné en erreur")

    async def _changer_etat(self, etat: str) -> None:
        if etat != self.etat_connexion:
            self.etat_connexion = etat
            await self._diffuser({"type": "connexion", "etat": etat})

    # ---------------------------------------------------------- abonnements
    async def _souscrire_tout(self) -> None:
        for categorie, cles in self._cles.items():
            async def rappel(charge: dict, categorie=categorie) -> None:
                await self._sur_notification(categorie, charge)
            try:
                premiere = await self.client.subscribe(
                    rappel, "settings/getSystemSettings",
                    {"category": categorie, "keys": cles},
                )
                self.etat[categorie] = dict(premiere.get("settings", {}))
            except Exception as exc:  # noqa: BLE001
                log.warning("Abonnement %s impossible : %s", categorie or '""', exc)

    async def _sur_notification(self, categorie: str, charge: dict) -> None:
        reglages = charge.get("settings") or {}
        if not reglages:
            return
        cache = self.etat.setdefault(categorie, {})
        delta: dict[str, Any] = {}
        for cle, valeur in reglages.items():
            valeur = _normaliser(cache.get(cle), valeur)
            if cache.get(cle) != valeur:
                cache[cle] = valeur
                delta[cle] = valeur
        if delta:
            await self._diffuser({
                "type": "changement", "categorie": categorie, "reglages": delta,
            })

    # ------------------------------------------------------ lecture/écriture
    @property
    def mode_image(self) -> str | None:
        return self.etat.get("picture", {}).get("pictureMode")

    def instantane(self) -> dict:
        return {
            "connexion": self.etat_connexion,
            "mode_image": self.mode_image,
            "reglages": self.etat,
        }

    async def lire(self, categorie: str, cles: list[str]) -> dict[str, Any]:
        if self.client is None:
            raise ConnexionTvPerdue
        res = await self.client.request(
            "settings/getSystemSettings", {"category": categorie, "keys": cles},
        )
        valeurs = res.get("settings", {})
        cache = self.etat.setdefault(categorie, {})
        cache.update(valeurs)
        return valeurs

    async def ecrire(self, categorie: str, cle: str, valeur: Any) -> dict:
        """Écrit un réglage puis relit pour confirmer.

        Renvoie {"ancienne": …, "nouvelle": …, "confirme": bool,
        "mode_image": …}. Lève ConnexionTvPerdue si le téléviseur est
        injoignable.
        """
        if self.client is None or self.etat_connexion != "connecte":
            raise ConnexionTvPerdue
        async with self._verrou_ecriture:
            mode_image = self.mode_image
            try:
                ancienne = self.etat.get(categorie, {}).get(cle)
                if ancienne is None:
                    lu = await self.lire(categorie, [cle])
                    ancienne = lu.get(cle)
                await self.client.request(
                    "settings/setSystemSettings",
                    {"category": categorie, "settings": {cle: valeur}},
                )
                relue = (await self.lire(categorie, [cle])).get(cle)
            except PyLGTVCmdException as exc:
                # Refus applicatif du téléviseur (valeur hors plage, clé non
                # acceptée dans ce contexte…) : à distinguer d'une perte de
                # connexion, l'appelant doit pouvoir continuer sur d'autres
                # écritures (application de preset, retour arrière en lot).
                message = getattr(exc, "message", exc)
                if isinstance(message, dict):
                    message = message.get("payload", {}).get("errorText", str(message))
                raise EcritureRefusee(str(message)) from exc
            return {
                "ancienne": ancienne,
                "nouvelle": relue,
                "confirme": relue == valeur,
                "mode_image": mode_image,
            }


class ConnexionTvPerdue(Exception):
    """Le téléviseur n'est pas joignable."""


class EcritureRefusee(Exception):
    """Le téléviseur a refusé l'écriture (valeur hors plage, clé non
    acceptée dans ce contexte, etc.)."""
