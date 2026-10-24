"""Diagnostics téléchargeables depuis la page de l'intégration."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_CLE_CLIENT
from .entite import descriptions

A_MASQUER = {CONF_HOST, CONF_CLE_CLIENT}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    tv = entry.runtime_data.televiseur
    return {
        "entree": async_redact_data(dict(entry.data), A_MASQUER),
        "connexion": tv.etat_connexion,
        "voie_ecriture": tv.voie_ecriture,
        "ecriture_possible": tv.ecriture_possible,
        "mode_image": tv.mode_image,
        "reglages": tv.etat,
        "entites": {
            plateforme: sum(1 for d in descriptions() if d.plateforme == plateforme)
            for plateforme in ("number", "select", "switch", "sensor")
        },
    }
