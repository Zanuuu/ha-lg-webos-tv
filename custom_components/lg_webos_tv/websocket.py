"""API websocket du panneau, calquée sur l'API REST de l'ancienne app :
même découpage, mêmes réponses, pour que le frontend ne change que sa couche
d'accès (frontend/src/api.js). Réservée aux administrateurs, comme le
panneau."""

from collections.abc import Callable
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from . import arbre, restauration
from .const import DOMAIN
from .presets import PresetExistant, PresetInconnu, capturer_snapshot


def _donnees(hass: HomeAssistant, connection, msg) -> Any | None:
    entrees = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entrees:
        connection.send_error(msg["id"], "non_chargee",
                              "L'intégration LG webOS TV n'est pas chargée")
        return None
    return entrees[0].runtime_data


def _commande(schema: dict, gestionnaire: Callable) -> Callable:
    """Commande asynchrone, réservée aux administrateurs, qui reçoit les
    données de l'entrée chargée."""

    @websocket_api.websocket_command(schema)
    @websocket_api.require_admin
    @websocket_api.async_response
    async def commande(hass: HomeAssistant, connection, msg) -> None:
        donnees = _donnees(hass, connection, msg)
        if donnees is not None:
            await gestionnaire(hass, connection, msg, donnees)

    return commande


def _echec_ecriture(connection, msg, resultat: dict) -> bool:
    """Envoie l'erreur d'une écriture échouée ; renvoie True si envoyée."""
    if resultat["ok"]:
        return False
    raison = resultat.get("raison", "")
    if raison == "téléviseur injoignable":
        code = "injoignable"
    elif raison == restauration.RAISON_ECRITURE_IMPOSSIBLE:
        code = "ecriture_impossible"
    else:
        code = "refusee"
    connection.send_error(msg["id"], code, raison)
    return True


async def _arbre(hass, connection, msg, donnees) -> None:
    connection.send_result(msg["id"], arbre.charger())


async def _reglages(hass, connection, msg, donnees) -> None:
    connection.send_result(msg["id"], donnees.televiseur.instantane())


async def _ecrire(hass, connection, msg, donnees) -> None:
    try:
        resultat = await donnees.ecritures.demander(msg["entree_id"], msg["valeur"], "panneau")
    except arbre.EntreeInconnue:
        connection.send_error(msg["id"], "introuvable", f"Entrée inconnue : {msg['entree_id']}")
        return
    except arbre.EntreeNonPilotable:
        connection.send_error(msg["id"], "invalide",
                              f"Entrée non pilotable par l'API : {msg['entree_id']}")
        return
    except arbre.ValeurInvalide as exc:
        connection.send_error(msg["id"], "invalide", f"Valeur invalide : {exc}")
        return
    if not _echec_ecriture(connection, msg, resultat):
        connection.send_result(msg["id"], resultat)


async def _historique(hass, connection, msg, donnees) -> None:
    connection.send_result(msg["id"], await donnees.historique.lister(msg["limite"]))


async def _annuler(hass, connection, msg, donnees) -> None:
    resultat = await restauration.annuler_ecriture(
        donnees.televiseur, donnees.historique, msg["ecriture_id"])
    if not resultat["ok"] and resultat.get("raison") == "entrée d'historique introuvable":
        connection.send_error(msg["id"], "introuvable", resultat["raison"])
        return
    connection.send_result(msg["id"], resultat)


async def _revenir(hass, connection, msg, donnees) -> None:
    resultats = await restauration.revenir_a(
        donnees.televiseur, donnees.historique, msg["horodatage"])
    connection.send_result(msg["id"], {"resultats": resultats})


async def _presets(hass, connection, msg, donnees) -> None:
    connection.send_result(msg["id"], await donnees.presets.lister())


async def _preset(hass, connection, msg, donnees) -> None:
    preset = await donnees.presets.recuperer(msg["nom"])
    if preset is None:
        connection.send_error(msg["id"], "introuvable", f"Preset inconnu : {msg['nom']}")
        return
    connection.send_result(msg["id"], preset)


async def _creer_preset(hass, connection, msg, donnees) -> None:
    tv = donnees.televiseur
    snapshot = capturer_snapshot(tv.etat, tv.mode_image, msg.get("entrees"))
    if not snapshot:
        connection.send_error(
            msg["id"], "invalide",
            "Aucun réglage pilotable à capturer (sélection vide, ou valeurs pas "
            "encore lues depuis le téléviseur)")
        return
    try:
        connection.send_result(msg["id"], await donnees.presets.sauvegarder(msg["nom"], snapshot))
    except PresetExistant:
        connection.send_error(msg["id"], "existe_deja",
                              f"Un preset nommé « {msg['nom']} » existe déjà")


async def _importer_preset(hass, connection, msg, donnees) -> None:
    try:
        connection.send_result(msg["id"], await donnees.presets.sauvegarder(
            msg["nom"], msg["entrees"], remplacer=msg["remplacer"]))
    except PresetExistant:
        connection.send_error(
            msg["id"], "existe_deja",
            f"Un preset nommé « {msg['nom']} » existe déjà (utilisez remplacer)")


async def _supprimer_preset(hass, connection, msg, donnees) -> None:
    if not await donnees.presets.supprimer(msg["nom"]):
        connection.send_error(msg["id"], "introuvable", f"Preset inconnu : {msg['nom']}")
        return
    connection.send_result(msg["id"], {"supprime": msg["nom"]})


async def _appliquer_preset(hass, connection, msg, donnees) -> None:
    try:
        connection.send_result(msg["id"], await restauration.appliquer_preset(
            donnees.televiseur, donnees.historique, donnees.presets, msg["nom"]))
    except PresetInconnu:
        connection.send_error(msg["id"], "introuvable", f"Preset inconnu : {msg['nom']}")


async def _abonner(hass, connection, msg, donnees) -> None:
    """Flux temps réel : instantané initial puis événements du téléviseur."""
    tv = donnees.televiseur

    async def relayer(evenement: dict) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], evenement))

    tv.abonner(relayer)

    @callback
    def desabonner() -> None:
        tv.desabonner(relayer)

    connection.subscriptions[msg["id"]] = desabonner
    connection.send_result(msg["id"])
    connection.send_message(websocket_api.event_message(
        msg["id"], {"type": "instantane", **tv.instantane()}))


def _type(nom: str) -> dict:
    return {vol.Required("type"): f"{DOMAIN}/{nom}"}


COMMANDES = [
    _commande(_type("arbre"), _arbre),
    _commande(_type("reglages"), _reglages),
    _commande({**_type("ecrire"), vol.Required("entree_id"): str,
               vol.Required("valeur"): vol.Any(bool, int, float, str, dict, list)}, _ecrire),
    _commande({**_type("historique"), vol.Optional("limite", default=100): int}, _historique),
    _commande({**_type("historique/annuler"), vol.Required("ecriture_id"): int}, _annuler),
    _commande({**_type("historique/revenir"), vol.Required("horodatage"): vol.Coerce(float)},
              _revenir),
    _commande(_type("presets"), _presets),
    _commande({**_type("presets/obtenir"), vol.Required("nom"): str}, _preset),
    _commande({**_type("presets/creer"), vol.Required("nom"): str,
               vol.Optional("entrees"): vol.Any(None, [str])}, _creer_preset),
    _commande({**_type("presets/importer"), vol.Required("nom"): str,
               vol.Required("entrees"): [dict],
               vol.Optional("remplacer", default=False): bool}, _importer_preset),
    _commande({**_type("presets/supprimer"), vol.Required("nom"): str}, _supprimer_preset),
    _commande({**_type("presets/appliquer"), vol.Required("nom"): str}, _appliquer_preset),
    _commande(_type("abonner"), _abonner),
]


@callback
def async_enregistrer(hass: HomeAssistant) -> None:
    for commande in COMMANDES:
        websocket_api.async_register_command(hass, commande)
