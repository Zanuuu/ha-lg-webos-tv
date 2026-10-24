"""Panneau « LG webOS TV » de la barre latérale : la réplique du menu
Réglages (arbre complet, presets, historique), construite depuis frontend/
dans ce dossier."""

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

URL_STATIQUE = "/lg_webos_tv_panneau"
CHEMIN_PANNEAU = "lg-webos-tv"
ELEMENT = "lg-webos-tv-panel"
DOSSIER = Path(__file__).resolve().parent / "frontend"
_CHEMIN_STATIQUE_ENREGISTRE = f"{DOMAIN}_chemin_statique"


async def async_enregistrer(hass: HomeAssistant) -> None:
    if "frontend" not in hass.config.components:
        # Installations sans interface (tests, configurations minimales).
        return
    if not hass.data.get(_CHEMIN_STATIQUE_ENREGISTRE):
        # Un chemin statique ne se retire pas : enregistré une fois par
        # démarrage de Home Assistant, pas à chaque rechargement de l'entrée.
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_STATIQUE, str(DOSSIER), cache_headers=False)])
        hass.data[_CHEMIN_STATIQUE_ENREGISTRE] = True
    version = (await async_get_integration(hass, DOMAIN)).version
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=CHEMIN_PANNEAU,
        webcomponent_name=ELEMENT,
        sidebar_title="LG webOS TV",
        sidebar_icon="mdi:television",
        # Version en paramètre : un navigateur ne garde pas l'ancien panneau
        # après une mise à jour de l'intégration.
        module_url=f"{URL_STATIQUE}/panneau.js?v={version}",
        # Document à part entière, comme sous l'Ingress de l'ancienne app :
        # la feuille de style (:root, body, polices) s'applique telle quelle.
        embed_iframe=True,
        require_admin=True,
    )


def async_retirer(hass: HomeAssistant) -> None:
    if "frontend" in hass.config.components:
        frontend.async_remove_panel(hass, CHEMIN_PANNEAU, warn_if_unknown=False)
