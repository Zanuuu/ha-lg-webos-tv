"""Flux de configuration : adresse du téléviseur (saisie ou découverte SSDP),
appairage avec acceptation sur l'écran, réauthentification quand le
téléviseur refuse la clé, changement d'adresse. Options : luminosité
adaptative."""

import asyncio
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import (SOURCE_REAUTH, ConfigEntry,
                                          ConfigFlow, ConfigFlowResult,
                                          OptionsFlowWithReload)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.selector import (EntitySelector,
                                            EntitySelectorConfig,
                                            NumberSelector,
                                            NumberSelectorConfig,
                                            NumberSelectorMode, SelectSelector,
                                            SelectSelectorConfig)
from homeassistant.helpers.service_info.ssdp import (ATTR_UPNP_FRIENDLY_NAME,
                                                     SsdpServiceInfo)

from .const import (CONF_CAPTEUR_LUX, CONF_CLE_CLIENT, CONF_ECART_MINIMAL,
                    CONF_LUMINOSITE_MAX, CONF_LUMINOSITE_MIN, CONF_LUX_MAX,
                    CONF_LUX_MIN, CONF_MODES_EXCLUS, CONF_PAUSE_MIN, DOMAIN,
                    OPTIONS_LUMINOSITE_DEFAUT)
from .luminosite_adaptative import modes_proposes
from .televiseur import AppairageEchoue, appairer

TITRE_DEFAUT = "LG webOS TV"


class LgWebosTvConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "OptionsLgWebosTv":
        return OptionsLgWebosTv()

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


def _nombre(minimum: float, maximum: float, unite: str | None = None) -> NumberSelector:
    config = NumberSelectorConfig(min=minimum, max=maximum, step=1,
                                  mode=NumberSelectorMode.BOX)
    if unite is not None:
        config["unit_of_measurement"] = unite
    return NumberSelector(config)


class OptionsLgWebosTv(OptionsFlowWithReload):
    """Luminosité adaptative. L'entrée est rechargée à l'enregistrement : la
    fonction et ses entités n'existent que si un capteur est choisi."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        erreurs = {}
        if user_input is not None:
            if user_input[CONF_LUX_MAX] <= user_input[CONF_LUX_MIN]:
                erreurs[CONF_LUX_MAX] = "lux_max_trop_bas"
            if user_input[CONF_LUMINOSITE_MAX] < user_input[CONF_LUMINOSITE_MIN]:
                erreurs[CONF_LUMINOSITE_MAX] = "luminosite_max_trop_basse"
            if not erreurs:
                # Les sélecteurs numériques rendent des flottants ; le
                # téléviseur n'accepte que des entiers.
                for cle in (CONF_LUMINOSITE_MIN, CONF_LUMINOSITE_MAX,
                            CONF_ECART_MINIMAL, CONF_PAUSE_MIN):
                    user_input[cle] = int(user_input[cle])
                return self.async_create_entry(data=user_input)

        # Lecture de l'arbre (en cache une fois l'entrée chargée).
        modes = await self.hass.async_add_executor_job(modes_proposes)
        schema = vol.Schema({
            vol.Optional(CONF_CAPTEUR_LUX): EntitySelector(EntitySelectorConfig(
                domain="sensor", device_class="illuminance")),
            vol.Required(CONF_LUX_MIN): _nombre(1, 1000, "lx"),
            vol.Required(CONF_LUX_MAX): _nombre(2, 100000, "lx"),
            vol.Required(CONF_LUMINOSITE_MIN): _nombre(0, 100),
            vol.Required(CONF_LUMINOSITE_MAX): _nombre(0, 100),
            vol.Required(CONF_ECART_MINIMAL): _nombre(1, 20),
            vol.Required(CONF_PAUSE_MIN): _nombre(5, 720, "min"),
            vol.Required(CONF_MODES_EXCLUS): SelectSelector(SelectSelectorConfig(
                options=modes, multiple=True, translation_key=CONF_MODES_EXCLUS)),
        })
        valeurs = {**OPTIONS_LUMINOSITE_DEFAUT, **self.config_entry.options,
                   **(user_input or {})}
        return self.async_show_form(
            step_id="init", errors=erreurs,
            data_schema=self.add_suggested_values_to_schema(schema, valeurs))
