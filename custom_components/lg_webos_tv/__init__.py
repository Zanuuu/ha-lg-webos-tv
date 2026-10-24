"""Intégration LG webOS TV : réglages du téléviseur en entités Home
Assistant, synchronisés en temps réel dans les deux sens."""

from dataclasses import dataclass
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from . import panneau, restauration, services, websocket
from .const import CONF_CLE_CLIENT, DOMAIN
from .ecritures import FileEcritures
from .entite import descriptions
from .historique import Historique
from .presets import Presets
from .televiseur import Televiseur

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.EVENT,
             Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PROBLEME_ECRITURE = "ecriture_impossible"


@dataclass
class DonneesLgWebosTv:
    televiseur: Televiseur
    historique: Historique
    presets: Presets
    ecritures: FileEcritures


type LgWebosTvConfigEntry = ConfigEntry[DonneesLgWebosTv]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    # Actions enregistrées une fois pour l'intégration, et non par entrée :
    # elles restent visibles (et expliquent leur échec) même si l'entrée
    # n'est pas chargée.
    services.async_enregistrer(hass)
    websocket.async_enregistrer(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LgWebosTvConfigEntry) -> bool:
    # Bases SQLite hors de .storage (réservé au stockage JSON de HA), mais
    # dans le dossier de configuration : incluses dans les sauvegardes.
    dossier = Path(hass.config.path(DOMAIN))

    def construire() -> DonneesLgWebosTv:
        # Lectures disque (arbre, inventaire) et création des bases : hors
        # de la boucle d'événements.
        dossier.mkdir(exist_ok=True)
        descriptions()
        televiseur = Televiseur(entry.data[CONF_HOST], entry.data[CONF_CLE_CLIENT])
        historique = Historique(dossier / "historique.sqlite")

        async def ecrire(entree_id, valeur, origine, mode_attendu):
            return await restauration.ecrire_par_entree(
                televiseur, historique, entree_id, valeur, origine, mode_attendu)

        return DonneesLgWebosTv(
            televiseur=televiseur, historique=historique,
            presets=Presets(dossier / "presets.sqlite"),
            ecritures=FileEcritures(ecrire),
        )

    donnees = await hass.async_add_executor_job(construire)
    entry.runtime_data = donnees

    async def sur_evenement(evenement: dict) -> None:
        if evenement == {"type": "connexion", "etat": "appairage_requis"}:
            entry.async_start_reauth(hass)
        elif evenement["type"] == "ecriture":
            # Visible dans Réparations : un firmware peut fermer la voie
            # d'écriture (docs/incidents-ecriture.md § 7, limites).
            if evenement["possible"]:
                ir.async_delete_issue(hass, DOMAIN, PROBLEME_ECRITURE)
            else:
                ir.async_create_issue(
                    hass, DOMAIN, PROBLEME_ECRITURE, is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=PROBLEME_ECRITURE)

    donnees.televiseur.abonner(sur_evenement)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await panneau.async_enregistrer(hass)
    # Le téléviseur peut être éteint : l'entrée est prête sans attendre la
    # connexion, les entités restent indisponibles jusque-là.
    await donnees.televiseur.demarrer(
        lambda coro: entry.async_create_background_task(
            hass, coro, f"{DOMAIN} connexion {entry.data[CONF_HOST]}"))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LgWebosTvConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    panneau.async_retirer(hass)
    await entry.runtime_data.ecritures.arreter()
    await entry.runtime_data.televiseur.arreter()
    return True
