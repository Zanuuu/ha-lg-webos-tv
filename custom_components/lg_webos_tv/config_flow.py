"""Flux de configuration : adresse du téléviseur (saisie ou découverte SSDP),
appairage avec acceptation sur l'écran, réauthentification quand le
téléviseur refuse la clé, changement d'adresse."""

import asyncio
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import (SOURCE_REAUTH, ConfigFlow,
                                          ConfigFlowResult)
from homeassistant.const import CONF_HOST
from homeassistant.helpers.service_info.ssdp import (ATTR_UPNP_FRIENDLY_NAME,
                                                     SsdpServiceInfo)

from .const import CONF_CLE_CLIENT, DOMAIN
from .televiseur import AppairageEchoue, appairer

TITRE_DEFAUT = "LG webOS TV"


class LgWebosTvConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._hote: str | None = None
        self._titre = TITRE_DEFAUT
        self._tache_appairage: asyncio.Task | None = None
        self._cle: str | None = None
        self._erreur: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._hote = user_input[CONF_HOST]
            return await self.async_step_appairage()
        erreurs = {"base": self._erreur} if self._erreur else {}
        self._erreur = None
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_HOST): str}),
                {CONF_HOST: self._hote}),
            errors=erreurs,
        )

    async def async_step_ssdp(
        self, discovery_info: SsdpServiceInfo
    ) -> ConfigFlowResult:
        hote = urlparse(discovery_info.ssdp_location or "").hostname
        if not hote:
            return self.async_abort(reason="cannot_connect")
        self._hote = hote
        self._titre = discovery_info.upnp.get(
            ATTR_UPNP_FRIENDLY_NAME, TITRE_DEFAUT).replace("[LG]", "LG")
        self.context["title_placeholders"] = {"name": self._titre}
        return await self.async_step_confirmer_decouverte()

    async def async_step_confirmer_decouverte(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_appairage()
        return self.async_show_form(
            step_id="confirmer_decouverte",
            description_placeholders={"name": self._titre, "host": self._hote},
        )

    async def async_step_appairage(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Attend l'acceptation sur l'écran du téléviseur (120 s au plus)."""
        if self._tache_appairage is None:
            self._tache_appairage = self.hass.async_create_task(
                appairer(self._hote), eager_start=False)
        if not self._tache_appairage.done():
            return self.async_show_progress(
                step_id="appairage", progress_action="appairage",
                progress_task=self._tache_appairage,
                description_placeholders={"host": self._hote},
            )
        tache, self._tache_appairage = self._tache_appairage, None
        try:
            self._cle = tache.result()
        except AppairageEchoue:
            self._erreur = "appairage_echoue"
            return self.async_show_progress_done(
                next_step_id="reauth_confirm" if self.source == SOURCE_REAUTH
                else "user")
        return self.async_show_progress_done(next_step_id="termine")

    async def async_step_termine(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        donnees = {CONF_HOST: self._hote, CONF_CLE_CLIENT: self._cle}
        if self.source == SOURCE_REAUTH:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates=donnees)
        return self.async_create_entry(title=self._titre, data=donnees)

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        self._hote = entry_data[CONF_HOST]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_appairage()
        erreurs = {"base": self._erreur} if self._erreur else {}
        self._erreur = None
        return self.async_show_form(
            step_id="reauth_confirm", errors=erreurs,
            description_placeholders={"host": self._hote},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Nouvelle adresse du même téléviseur : la clé d'appairage reste
        valable, elle est liée au téléviseur et non à son adresse."""
        entree = self._get_reconfigure_entry()
        if user_input is not None:
            return self.async_update_reload_and_abort(
                entree, data_updates={CONF_HOST: user_input[CONF_HOST]})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_HOST): str}),
                {CONF_HOST: entree.data[CONF_HOST]}),
        )
