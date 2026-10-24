"""Intégration LG webOS TV : réglages du téléviseur en entités Home
Assistant, synchronisés en temps réel dans les deux sens."""

from dataclasses import dataclass
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant

from . import arbre
from .const import CONF_CLE_CLIENT, DOMAIN
from .historique import Historique
from .presets import Presets
from .televiseur import Televiseur

PLATFORMS: list[Platform] = []


@dataclass
class DonneesLgWebosTv:
    televiseur: Televiseur
    historique: Historique
    presets: Presets


type LgWebosTvConfigEntry = ConfigEntry[DonneesLgWebosTv]


async def async_setup_entry(hass: HomeAssistant, entry: LgWebosTvConfigEntry) -> bool:
    # Bases SQLite hors de .storage (réservé au stockage JSON de HA), mais
    # dans le dossier de configuration : incluses dans les sauvegardes.
    dossier = Path(hass.config.path(DOMAIN))

    def construire() -> DonneesLgWebosTv:
        # Lectures disque (arbre, inventaire) et création des bases : hors
        # de la boucle d'événements.
        dossier.mkdir(exist_ok=True)
        arbre.par_id()
        return DonneesLgWebosTv(
            televiseur=Televiseur(entry.data[CONF_HOST], entry.data[CONF_CLE_CLIENT]),
            historique=Historique(dossier / "historique.sqlite"),
            presets=Presets(dossier / "presets.sqlite"),
        )

    donnees = await hass.async_add_executor_job(construire)
    entry.runtime_data = donnees

    async def sur_evenement(evenement: dict) -> None:
        if evenement == {"type": "connexion", "etat": "appairage_requis"}:
            entry.async_start_reauth(hass)

    donnees.televiseur.abonner(sur_evenement)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Le téléviseur peut être éteint : l'entrée est prête sans attendre la
    # connexion, les entités restent indisponibles jusque-là.
    await donnees.televiseur.demarrer(
        lambda coro: entry.async_create_background_task(
            hass, coro, f"{DOMAIN} connexion {entry.data[CONF_HOST]}"))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LgWebosTvConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.televiseur.arreter()
    return True
