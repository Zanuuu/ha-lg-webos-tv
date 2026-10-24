"""Actions de l'intégration, pour les automatisations et scripts.

- regler : écrit un réglage, avec une garde facultative sur le mode d'image
  (les réglages d'image n'appartiennent qu'au mode actif) ; renvoie le
  résultat de l'écriture.
- appliquer_preset : applique un preset (mode d'image d'abord) ; renvoie les
  réglages appliqués et ceux en échec.
"""

from typing import Any

import voluptuous as vol

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import (HomeAssistant, ServiceCall, ServiceResponse,
                                SupportsResponse)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from . import arbre, restauration
from .const import DOMAIN
from .entite import descriptions
from .presets import PresetInconnu

ID_MODE_IMAGE = "image.mode-selection"

SCHEMA_REGLER = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    vol.Required("valeur"): vol.Any(bool, int, float, str),
    vol.Optional("mode_image"): cv.string,
})
SCHEMA_PRESET = vol.Schema({vol.Required("nom"): cv.string})


def _erreur(cle: str, **variables: str) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=cle,
                                  translation_placeholders=variables)


def _entree(hass: HomeAssistant):
    entrees = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entrees:
        raise _erreur("non_chargee")
    return entrees[0]


def _modes_image() -> dict[str, str]:
    """Libellé → valeur API des modes d'image."""
    return next(d.choix for d in descriptions() if d.entree_id == ID_MODE_IMAGE)


def _valeur_api(description, valeur: Any) -> Any:
    if description.plateforme == "select":
        if valeur in description.choix:
            return description.choix[valeur]
        if str(valeur) in map(str, description.choix.values()):
            return next(v for v in description.choix.values() if str(v) == str(valeur))
        raise _erreur("valeur_invalide", valeur=str(valeur),
                      attendu=", ".join(description.choix))
    if description.plateforme == "number":
        try:
            return int(round(float(valeur)))
        except (TypeError, ValueError):
            raise _erreur("valeur_invalide", valeur=str(valeur),
                          attendu="nombre") from None
    if description.plateforme == "switch":
        try:
            return cv.boolean(valeur)
        except vol.Invalid:
            raise _erreur("valeur_invalide", valeur=str(valeur),
                          attendu="on / off") from None
    raise _erreur("lecture_seule", reglage=description.nom)


async def _regler(call: ServiceCall) -> ServiceResponse:
    hass = call.hass
    entree = _entree(hass)
    inscrite = er.async_get(hass).async_get(call.data[ATTR_ENTITY_ID])
    par_id = {d.entree_id: d for d in descriptions()}
    if inscrite is None or inscrite.config_entry_id != entree.entry_id \
            or inscrite.unique_id not in par_id:
        raise _erreur("entite_inconnue", entite=call.data[ATTR_ENTITY_ID])
    description = par_id[inscrite.unique_id]
    valeur = _valeur_api(description, call.data["valeur"])

    tv = entree.runtime_data.televiseur
    mode_voulu = call.data.get("mode_image")
    if mode_voulu is not None:
        mode_voulu = _modes_image().get(mode_voulu, mode_voulu)
        if mode_voulu not in _modes_image().values():
            raise _erreur("valeur_invalide", valeur=mode_voulu,
                          attendu=", ".join(_modes_image().values()))
        if tv.mode_image != mode_voulu:
            # Garde attendue, pas une erreur : l'automatisation continue.
            return {"ok": False, "ecrit": False, "mode_image": tv.mode_image,
                    "raison": f"mode d'image actif « {tv.mode_image} », "
                              f"attendu « {mode_voulu} »"}

    try:
        resultat = await entree.runtime_data.ecritures.demander(
            description.entree_id, valeur, "home_assistant", mode_attendu=mode_voulu)
    except arbre.ValeurInvalide as exc:
        raise _erreur("valeur_invalide", valeur=str(valeur), attendu=str(exc)) from exc
    if not resultat["ok"]:
        raise HomeAssistantError(translation_domain=DOMAIN,
                                 translation_key="ecriture_echouee",
                                 translation_placeholders={
                                     "reglage": description.nom,
                                     "raison": resultat["raison"]})
    return {"ok": True, "ecrit": True, "ancienne": resultat["ancienne"],
            "nouvelle": resultat["nouvelle"], "mode_image": resultat["mode_image"]}


async def _appliquer_preset(call: ServiceCall) -> ServiceResponse:
    d = _entree(call.hass).runtime_data
    try:
        resultat = await restauration.appliquer_preset(
            d.televiseur, d.historique, d.presets, call.data["nom"])
    except PresetInconnu:
        raise _erreur("preset_inconnu", nom=call.data["nom"]) from None
    return {
        "appliques": [e.get("entree_id") or e["cle"] for e in resultat["appliques"]],
        "echecs": [{"reglage": e.get("entree_id") or e["cle"], "raison": e["raison"]}
                   for e in resultat["echecs"]],
    }


def async_enregistrer(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "regler", _regler, schema=SCHEMA_REGLER,
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "appliquer_preset", _appliquer_preset,
                                 schema=SCHEMA_PRESET,
                                 supports_response=SupportsResponse.OPTIONAL)
