"""Accès au téléviseur — SEUL module autorisé à importer bscpylgtv.

Responsabilités :
- connexion et reconnexion automatique (le téléviseur peut être éteint) ;
- abonnements aux changements de réglages par catégorie (validés en phase 1) ;
- cache de l'état courant, avec normalisation des types (les notifications
  livrent parfois les nombres sous forme de chaînes, cf. rapport phase 1) ;
- écriture d'un réglage puis relecture de confirmation, directe ou, sous
  webOS 11, par le pont createAlert (setSystemSettings refusé aux clients
  non signés par LG) ;
- vérification, à chaque connexion, de l'appairage et de la voie
  d'écriture disponible ;
- diffusion des événements (changements, état de connexion) aux abonnés
  internes (entités, panneau, historique) ;
- appairage initial (`appairer`), mené par le flux de configuration.

Le module ne dépend pas de Home Assistant : il est testable seul, et la clé
d'appairage lui est fournie par l'entrée de configuration.
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from bscpylgtv import WebOsClient
from bscpylgtv.exceptions import PyLGTVCmdException

from .const import (APPAIRAGE_DELAI_S, INVENTAIRE, MANIFESTE_SSAP,
                    RECONNEXION_DELAI_MAX_S, RECONNEXION_DELAI_MIN_S)

log = logging.getLogger(__name__)

# Événements diffusés aux abonnés internes :
#   {"type": "connexion",
#    "etat": "connecte" | "deconnecte" | "connexion" | "appairage_requis"}
#   {"type": "ecriture", "possible": bool}
#   {"type": "changement", "categorie": str, "reglages": {cle: valeur},
#    "origine": "application" | "manuel" | "autre_application" | "cascade"
#               | "relecture"}
Abonne = Callable[[dict], Awaitable[None]]

# Clé absente de la liste des clés modifiables du firmware : l'adaptateur
# settings la rejette avant toute écriture (« Some keys are not allowed »),
# ce qui permet de tester la permission WRITE_SETTINGS sans rien modifier.
CLE_SONDE_ECRITURE = "sondePermissionEcriture"

# webOS 11 refuse WRITE_SETTINGS aux manifestes non signés, mais accorde
# WRITE_NOTIFICATION_TOAST (PROTECTED), seule permission exigée par
# createAlert/closeAlert : une alerte dont le `onclose` appelle le service de
# réglages fait écrire le téléviseur lui-même (docs/incidents-ecriture.md § 7).
LUNA_ECRITURE = "com.webos.settingsservice/setSystemSettings"
# alertId mal formé : sans la permission, la passerelle répond 401 ; avec,
# l'adaptateur rejette l'identifiant sans rien fermer.
ALERTE_SONDE = "sondePermissionAlerte"
# closeAlert est resté une fois sans réponse sur 43.21.71 (bscpylgtv PR #9) ;
# la relecture tranche de toute façon.
DELAI_ALERTE_S = 5.0
# L'appel luna est muet et asynchrone. La notification d'abonnement portant
# la nouvelle valeur arrive ≈ 0,1 s après l'appel (43.21.77, docs/rapport-
# api.md phase 7) : c'est elle qui confirme. Sans notification (valeur
# identique à l'actuelle, ou refusée car hors plage), la relecture tranche.
DELAI_NOTIFICATION_S = 1.0
RELECTURES_ALERTE = 6

# Origine d'un changement d'après le champ `caller` des notifications
# (43.21.77, docs/rapport-api.md phase 7) : écritures par l'API (directe ou
# pont d'alerte) d'un côté ; menu Réglages et réglages rapides, c'est-à-dire
# la télécommande, de l'autre ; sans `caller`, les valeurs que le téléviseur
# envoie de lui-même après un changement de mode d'image.
CALLERS_API = {"com.webos.service.apiadapter", "com.webos.app.starfish_flutter_systemui"}
# Une notification de nos écritures peut arriver après leur confirmation par
# relecture : elle reste reconnue comme nôtre pendant ce délai.
MEMOIRE_ECRITURES_S = 2.0
INTERVALLE_RELECTURE_S = 0.5


def _texte_erreur(exc: Exception) -> str:
    message = getattr(exc, "message", exc)
    if isinstance(message, dict):
        return str(message.get("error") or message.get("payload", {}).get("errorText")
                   or message)
    return str(message)


def _non_enregistre(exc: Exception) -> bool:
    return "not registered" in _texte_erreur(exc)


def _permission_refusee(exc: Exception) -> bool:
    return "401 insufficient permissions" in _texte_erreur(exc)


def _cles_lisibles_par_categorie() -> dict[str, list[str]]:
    """Clés lisibles par catégorie, depuis l'inventaire de la phase 1."""
    inventaire = json.loads(INVENTAIRE.read_text())
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


async def _construire_client(hote: str, **options) -> WebOsClient:
    # Le constructeur crée un contexte SSL et lit le manifeste sur disque :
    # hors de la boucle d'événements, qui ne doit jamais bloquer.
    client = await asyncio.to_thread(
        WebOsClient, hote, states=[], manifest_file_path=str(MANIFESTE_SSAP),
        **options)
    await client.async_init()
    return client


class _CleEnMemoire:
    """Stockage de clé (protocole StorageProto de bscpylgtv) sans disque :
    la clé obtenue à l'appairage finit dans l'entrée de configuration."""

    def __init__(self):
        self.cles: dict[str, str] = {}

    async def set_key(self, key, val):
        self.cles[key] = val

    async def get_key(self, key):
        return self.cles.get(key)


async def appairer(hote: str) -> str:
    """Demande l'appairage (acceptation sur l'écran du téléviseur) et renvoie
    la clé client. Lève AppairageEchoue si la demande est refusée, expire ou
    si le téléviseur est injoignable."""
    client = None
    try:
        client = await _construire_client(hote, storage=_CleEnMemoire())
        await asyncio.wait_for(client.connect(), APPAIRAGE_DELAI_S)
        if not client.client_key:
            raise AppairageEchoue("aucune clé reçue")
        # bscpylgtv peut se déclarer connecté sans être enregistré (refus
        # muet) : une lecture tranche.
        await client.request("settings/getSystemSettings",
                             {"category": "picture", "keys": ["pictureMode"]})
        return client.client_key
    except AppairageEchoue:
        raise
    except Exception as exc:  # noqa: BLE001 — refus, expiration, réseau…
        raise AppairageEchoue(_texte_erreur(exc)) from exc
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001 — la fermeture ne doit pas lever
                pass


class Televiseur:
    def __init__(self, hote: str, client_key: str | None,
                 fabrique_client: Callable[[], Awaitable] | None = None):
        self.hote = hote
        self.client_key = client_key
        # Point d'injection pour les tests : les vrais appels passent par
        # WebOsClient.
        self._fabrique_client = fabrique_client or self._creer_client
        self.client = None
        self.etat_connexion = "deconnecte"
        self.etat: dict[str, dict[str, Any]] = {}
        self._abonnes: list[Abonne] = []
        self._cles = _cles_lisibles_par_categorie()
        self._tache: asyncio.Task | None = None
        self._verrou_ecriture = asyncio.Lock()
        # None tant qu'aucune connexion n'a permis de le vérifier.
        self.ecriture_possible: bool | None = None
        # "ssap" (setSystemSettings direct) ou "alerte" (pont createAlert).
        self.voie_ecriture: str | None = None
        self.intervalle_relecture = INTERVALLE_RELECTURE_S
        self.delai_notification = DELAI_NOTIFICATION_S
        # Écritures en cours, en attente de leur notification : (catégorie,
        # clé) → [(valeur attendue, futur)].
        self._attentes: dict[tuple[str, str], list[tuple[Any, asyncio.Future]]] = {}
        # Écritures récentes : (catégorie, clé) → (valeur en texte, échéance).
        self._recentes: dict[tuple[str, str], tuple[str, float]] = {}

    # ------------------------------------------------------------------ cycle
    async def _creer_client(self):
        client = await _construire_client(self.hote, client_key=self.client_key)
        await client.connect()
        return client

    async def demarrer(self, creer_tache=asyncio.create_task) -> None:
        """Lance la boucle de connexion. `creer_tache` permet à Home
        Assistant d'en faire une tâche de fond de l'entrée de configuration
        (annulée au déchargement)."""
        self._tache = creer_tache(self._boucle_connexion())

    async def arreter(self) -> None:
        if self._tache:
            self._tache.cancel()
            try:
                await self._tache
            except asyncio.CancelledError:
                pass
        await self._deconnecter()

    async def _fermer_client(self) -> None:
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:  # noqa: BLE001 — la fermeture ne doit pas lever
                pass
            self.client = None

    async def _deconnecter(self) -> None:
        await self._fermer_client()
        await self._changer_etat("deconnecte")

    async def _verifier_acces(self) -> None:
        """Vérifie l'enregistrement du client, puis la permission d'écriture.

        Lève AppairageRequis si le téléviseur ne reconnaît pas le client.
        """
        try:
            await self.client.request(
                "settings/getSystemSettings",
                {"category": "picture", "keys": ["pictureMode"]},
            )
        except PyLGTVCmdException as exc:
            if _non_enregistre(exc):
                raise AppairageRequis from exc
            raise
        try:
            await self.client.request(
                "settings/setSystemSettings",
                {"category": "picture", "settings": {CLE_SONDE_ECRITURE: 0}},
            )
            await self._changer_ecriture("ssap")  # improbable : clé sonde acceptée
            return
        except PyLGTVCmdException as exc:
            # Toute autre erreur que le refus de permission signifie que la
            # requête a atteint l'adaptateur, qui a rejeté la clé sonde.
            if not _permission_refusee(exc):
                await self._changer_ecriture("ssap")
                return
        try:
            await self.client.request("system.notifications/closeAlert",
                                      {"alertId": ALERTE_SONDE})
            voie = "alerte"
        except PyLGTVCmdException as exc:
            voie = None if _permission_refusee(exc) else "alerte"
        await self._changer_ecriture(voie)

    async def _changer_ecriture(self, voie: str | None) -> None:
        if voie != self.voie_ecriture:
            log.info("Voie d'écriture des réglages : %s", voie or "aucune")
        self.voie_ecriture = voie
        possible = voie is not None
        if possible != self.ecriture_possible:
            self.ecriture_possible = possible
            if not possible:
                log.warning("Le téléviseur refuse l'écriture des réglages à ce "
                            "client (ni setSystemSettings ni alertes "
                            "autorisés) : mode consultation")
            await self._diffuser({"type": "ecriture", "possible": possible})

    async def _boucle_connexion(self) -> None:
        delai = RECONNEXION_DELAI_MIN_S
        while True:
            await self._changer_etat("connexion")
            try:
                self.client = await self._fabrique_client()
                await self._verifier_acces()
            except AppairageRequis:
                # bscpylgtv n'échoue pas quand le téléviseur refuse la clé :
                # la socket reste ouverte mais non enregistrée. Un nouvel
                # appairage exige l'utilisateur devant l'écran : la boucle
                # s'arrête et Home Assistant ouvre la réauthentification.
                log.warning("Clé d'appairage refusée par le téléviseur : "
                            "nouvel appairage nécessaire")
                await self._fermer_client()
                await self._changer_etat("appairage_requis")
                return
            except Exception as exc:  # noqa: BLE001 — TV éteinte, réseau…
                log.info("Connexion au téléviseur impossible : %s", exc)
                await self._fermer_client()
                await self._changer_etat("deconnecte")
                await asyncio.sleep(delai)
                delai = min(delai * 2, RECONNEXION_DELAI_MAX_S)
                continue

            delai = RECONNEXION_DELAI_MIN_S
            try:
                if not await self._souscrire_tout():
                    raise ConnexionTvPerdue("aucun abonnement n'a abouti")
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
            await asyncio.sleep(RECONNEXION_DELAI_MIN_S)

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
    async def _souscrire_tout(self) -> bool:
        """Renvoie False si aucun abonnement n'a abouti."""
        reussis = 0
        for categorie, cles in self._cles.items():
            async def rappel(charge: dict, categorie=categorie) -> None:
                await self._sur_notification(categorie, charge)
            try:
                premiere = await self.client.subscribe(
                    rappel, "settings/getSystemSettings",
                    {"category": categorie, "keys": cles},
                )
                self.etat[categorie] = dict(premiere.get("settings", {}))
                reussis += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("Abonnement %s impossible : %s", categorie or '""', exc)
        return reussis > 0

    async def _sur_notification(self, categorie: str, charge: dict) -> None:
        reglages = charge.get("settings") or {}
        if reglages:
            await self._appliquer(categorie, reglages, charge.get("caller"),
                                  notification=True)

    async def _appliquer(self, categorie: str, reglages: dict, caller: str | None,
                         notification: bool) -> None:
        """Met le cache à jour (notification ou relecture) et diffuse le
        changement avec son origine. Une relecture passe aussi par ici : sans
        quoi une valeur relue avant sa notification ne serait jamais diffusée."""
        cache = self.etat.setdefault(categorie, {})
        delta: dict[str, Any] = {}
        nos_cles = set()
        for cle, valeur in reglages.items():
            valeur = _normaliser(cache.get(cle), valeur)
            if self._est_notre_ecriture(categorie, cle, valeur):
                nos_cles.add(cle)
            if cache.get(cle) != valeur:
                cache[cle] = valeur
                delta[cle] = valeur
        if delta:
            await self._diffuser({
                "type": "changement", "categorie": categorie, "reglages": delta,
                "origine": _origine(set(delta) <= nos_cles, caller, notification),
            })

    def _est_notre_ecriture(self, categorie: str, cle: str, valeur: Any) -> bool:
        # Comparaison textuelle : les notifications mêlent entiers et chaînes
        # selon le mode d'image.
        texte = str(valeur)
        trouvee = False
        for attendue, futur in self._attentes.get((categorie, cle), []):
            if str(attendue) == texte:
                trouvee = True
                if not futur.done():
                    futur.set_result(None)
        recente = self._recentes.get((categorie, cle))
        if recente and recente[0] == texte and recente[1] > time.monotonic():
            trouvee = True
        return trouvee

    # ------------------------------------------------------ lecture/écriture
    @property
    def mode_image(self) -> str | None:
        return self.etat.get("picture", {}).get("pictureMode")

    def instantane(self) -> dict:
        return {
            "connexion": self.etat_connexion,
            "ecriture_possible": self.ecriture_possible,
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
        await self._appliquer(categorie, valeurs, None, notification=False)
        return {cle: self.etat[categorie][cle] for cle in valeurs}

    async def ecrire(self, categorie: str, cle: str, valeur: Any) -> dict:
        """Écrit un réglage puis relit pour confirmer.

        Renvoie {"ancienne": …, "nouvelle": …, "confirme": bool,
        "mode_image": …}. Lève ConnexionTvPerdue si le téléviseur est
        injoignable.
        """
        if self.client is None or self.etat_connexion != "connecte":
            raise ConnexionTvPerdue
        if self.ecriture_possible is False:
            raise EcritureImpossible
        async with self._verrou_ecriture:
            mode_image = self.mode_image
            futur = asyncio.get_running_loop().create_future()
            attentes = self._attentes.setdefault((categorie, cle), [])
            attentes.append((valeur, futur))
            try:
                ancienne = self.etat.get(categorie, {}).get(cle)
                if ancienne is None:
                    lu = await self.lire(categorie, [cle])
                    ancienne = lu.get(cle)
                charge = {"category": categorie, "settings": {cle: valeur}}
                if self.voie_ecriture == "alerte":
                    relue = await self._ecrire_par_alerte(
                        categorie, cle, valeur, charge, futur)
                else:
                    await self.client.request("settings/setSystemSettings", charge)
                    relue = (await self.lire(categorie, [cle])).get(cle)
            except PyLGTVCmdException as exc:
                if _permission_refusee(exc):
                    await self._changer_ecriture(None)
                    raise EcritureImpossible from exc
                # Refus applicatif du téléviseur (valeur hors plage, clé non
                # acceptée dans ce contexte…) : à distinguer d'une perte de
                # connexion, l'appelant doit pouvoir continuer sur d'autres
                # écritures (application de preset, retour arrière en lot).
                message = getattr(exc, "message", exc)
                if isinstance(message, dict):
                    message = message.get("payload", {}).get("errorText", str(message))
                raise EcritureRefusee(str(message)) from exc
            finally:
                attentes.remove((valeur, futur))
                if not attentes:
                    del self._attentes[(categorie, cle)]
                futur.cancel()
                self._recentes[(categorie, cle)] = (
                    str(valeur), time.monotonic() + MEMOIRE_ECRITURES_S)
            return {
                "ancienne": ancienne,
                "nouvelle": relue,
                "confirme": relue == valeur,
                "mode_image": mode_image,
            }

    async def _ecrire_par_alerte(self, categorie: str, cle: str, valeur: Any,
                                 charge: dict, futur: asyncio.Future) -> Any:
        """Écrit via le pont createAlert et renvoie la valeur relue.

        Le téléviseur ne renvoie ni succès ni erreur : une valeur refusée
        (hors plage, clé non acceptée) se traduit par une relecture
        inchangée, donc une écriture non confirmée.
        """
        try:
            await asyncio.wait_for(
                self.client.luna_request(LUNA_ECRITURE, charge),
                timeout=DELAI_ALERTE_S)
        except asyncio.TimeoutError:
            log.warning("Pas de réponse à closeAlert pour %s.%s : vérification "
                        "par relecture", categorie, cle)
        try:
            await asyncio.wait_for(asyncio.shield(futur), self.delai_notification)
            return self.etat.get(categorie, {}).get(cle)
        except asyncio.TimeoutError:
            pass
        relue = None
        for _ in range(RELECTURES_ALERTE):
            relue = (await self.lire(categorie, [cle])).get(cle)
            if relue == valeur:
                break
            await asyncio.sleep(self.intervalle_relecture)
        return relue


def _origine(notre: bool, caller: str | None, notification: bool) -> str:
    if notre:
        return "application"
    if not notification:
        return "relecture"
    if caller is None:
        return "cascade"
    if caller in CALLERS_API:
        return "autre_application"
    return "manuel"


class ConnexionTvPerdue(Exception):
    """Le téléviseur n'est pas joignable."""


class AppairageRequis(Exception):
    """Le téléviseur ne reconnaît plus la clé client (ex. après une mise à
    jour du firmware)."""


class AppairageEchoue(Exception):
    """La demande d'appairage a été refusée, a expiré, ou le téléviseur est
    injoignable."""


class EcritureImpossible(Exception):
    """Le téléviseur n'accorde à ce client ni setSystemSettings (webOS 11 :
    réservé aux manifestes signés par LG) ni les alertes."""


class EcritureRefusee(Exception):
    """Le téléviseur a refusé l'écriture (valeur hors plage, clé non
    acceptée dans ce contexte, etc.)."""
