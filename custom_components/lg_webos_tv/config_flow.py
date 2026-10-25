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
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (EntitySelector,
                                            EntitySelectorConfig,
                                            NumberSelector,
                                            NumberSelectorConfig,
                                            NumberSelectorMode, SelectSelector,
                                            SelectSelectorConfig,
                                            SelectSelectorMode)
from homeassistant.helpers.service_info.ssdp import (ATTR_UPNP_FRIENDLY_NAME,
                                                     SsdpServiceInfo)

from .const import (CONF_CAPTEUR_LUX, CONF_CLE_CLIENT, CONF_CONFIRMATION_SAUT,
                    CONF_ECART_MINIMAL, CONF_EMPLACEMENT, CONF_GEL_ECRITURE,
                    CONF_HYSTERESIS_DESCENTE, CONF_HYSTERESIS_MONTEE,
                    CONF_LISSAGE_DESCENTE, CONF_LISSAGE_MONTEE,
                    CONF_LUMINOSITE_MAX, CONF_LUMINOSITE_MIN, CONF_LUX_MAX,
                    CONF_LUX_MIN, CONF_MODES_EXCLUS, CONF_PAUSE_MIN,
                    CONF_POINT_INTERMEDIAIRE, CONF_RAMPE_DEBIT,
                    CONF_RAMPE_PAS, DOMAIN, EMPLACEMENTS, OPTIONS_AVANCEES,
                    OPTIONS_LUMINOSITE_DEFAUT)
from .courbe import conserver_ancrages
from .luminosite_adaptative import BORNES, modes_proposes, valider_options
from .televiseur import AppairageEchoue, appairer

TITRE_DEFAUT = "LG webOS TV"
# Section repliée du formulaire : écart minimal, constantes du signal (qui
# suivent sinon le profil du capteur et son emplacement) et rampe.
SECTION_AVANCEE = "avance"
# Point intermédiaire de la courbe : deux champs du formulaire, une seule
# option `point_intermediaire` ([lux, luminosité]) ; vides tous deux, pas de
# point.
LUX_INTERMEDIAIRE = "lux_intermediaire"
LUMINOSITE_INTERMEDIAIRE = "luminosite_intermediaire"


class LgWebosTvConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 2

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


def _nombre(cle: str, unite: str | None = None,
            bornes: tuple[int, int] | None = None, pas: float = 1) -> NumberSelector:
    minimum, maximum = bornes or BORNES[cle]
    config = NumberSelectorConfig(min=minimum, max=maximum, step=pas,
                                  mode=NumberSelectorMode.BOX)
    if unite is not None:
        config["unit_of_measurement"] = unite
    return NumberSelector(config)


class OptionsLgWebosTv(OptionsFlowWithReload):
    """Luminosité adaptative. L'entrée est rechargée à l'enregistrement : la
    fonction et ses entités n'existent que si un capteur est choisi. Le
    panneau modifie les mêmes options, sans rechargement quand il le peut."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        erreurs = {}
        # Lecture de l'arbre (en cache une fois l'entrée chargée).
        modes = await self.hass.async_add_executor_job(modes_proposes)
        saisie = None
        champs_point = None
        if user_input is not None:
            # Options stockées à plat : la section n'est qu'une présentation.
            saisie = {**user_input, **user_input.get(SECTION_AVANCEE, {})}
            saisie.pop(SECTION_AVANCEE, None)
            point = [saisie.pop(LUX_INTERMEDIAIRE, None),
                     saisie.pop(LUMINOSITE_INTERMEDIAIRE, None)]
            champs_point = dict(zip((LUX_INTERMEDIAIRE, LUMINOSITE_INTERMEDIAIRE), point,
                                    strict=True))
            if None not in point:
                saisie[CONF_POINT_INTERMEDIAIRE] = point
            options, erreurs = valider_options(saisie, modes)
            if point.count(None) == 1:
                manquant = LUX_INTERMEDIAIRE if point[0] is None else LUMINOSITE_INTERMEDIAIRE
                erreurs[manquant] = "point_intermediaire_incomplet"
            if (erreur := erreurs.pop(CONF_POINT_INTERMEDIAIRE, None)) is not None:
                erreurs[LUX_INTERMEDIAIRE] = erreur
            if not erreurs:
                return self.async_create_entry(
                    data=conserver_ancrages(self.config_entry.options, options))

        avance = vol.Schema({
            # Vides : valeur par défaut, ou celle du profil du capteur.
            vol.Optional(CONF_ECART_MINIMAL): _nombre(CONF_ECART_MINIMAL),
            vol.Optional(CONF_LISSAGE_MONTEE): _nombre(CONF_LISSAGE_MONTEE, "s"),
            vol.Optional(CONF_LISSAGE_DESCENTE): _nombre(CONF_LISSAGE_DESCENTE, "s"),
            vol.Optional(CONF_HYSTERESIS_MONTEE): _nombre(CONF_HYSTERESIS_MONTEE, "%"),
            vol.Optional(CONF_HYSTERESIS_DESCENTE): _nombre(CONF_HYSTERESIS_DESCENTE, "%"),
            vol.Optional(CONF_CONFIRMATION_SAUT): _nombre(CONF_CONFIRMATION_SAUT, "s"),
            vol.Optional(CONF_GEL_ECRITURE): _nombre(CONF_GEL_ECRITURE, "s"),
            vol.Optional(CONF_RAMPE_PAS): _nombre(CONF_RAMPE_PAS),
            vol.Optional(CONF_RAMPE_DEBIT): _nombre(CONF_RAMPE_DEBIT, "points/s"),
        })
        schema = vol.Schema({
            vol.Optional(CONF_CAPTEUR_LUX): EntitySelector(EntitySelectorConfig(
                domain="sensor", device_class="illuminance")),
            vol.Required(CONF_EMPLACEMENT): SelectSelector(SelectSelectorConfig(
                options=EMPLACEMENTS, mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_EMPLACEMENT)),
            # Dans l'ordre de la courbe : pièce sombre, intermédiaire
            # (facultative), lumineuse.
            # Lux au dixième : le point d'ancrage cale la courbe à cette
            # précision en pièce sombre.
            vol.Required(CONF_LUX_MIN): _nombre(CONF_LUX_MIN, "lx", pas=0.1),
            vol.Required(CONF_LUMINOSITE_MIN): _nombre(CONF_LUMINOSITE_MIN),
            vol.Optional(LUX_INTERMEDIAIRE): _nombre(
                LUX_INTERMEDIAIRE, "lx", (BORNES[CONF_LUX_MIN][0], BORNES[CONF_LUX_MAX][1]),
                pas=0.1),
            vol.Optional(LUMINOSITE_INTERMEDIAIRE): _nombre(
                LUMINOSITE_INTERMEDIAIRE, None, BORNES[CONF_LUMINOSITE_MIN]),
            vol.Required(CONF_LUX_MAX): _nombre(CONF_LUX_MAX, "lx", pas=0.1),
            vol.Required(CONF_LUMINOSITE_MAX): _nombre(CONF_LUMINOSITE_MAX),
            vol.Required(CONF_PAUSE_MIN): _nombre(CONF_PAUSE_MIN, "min"),
            vol.Required(CONF_MODES_EXCLUS): SelectSelector(SelectSelectorConfig(
                options=modes, multiple=True, translation_key=CONF_MODES_EXCLUS)),
            vol.Required(SECTION_AVANCEE): section(avance, {"collapsed": True}),
        })
        valeurs = {**OPTIONS_LUMINOSITE_DEFAUT, **self.config_entry.options, **(saisie or {})}
        valeurs[SECTION_AVANCEE] = {cle: valeurs.pop(cle) for cle in OPTIONS_AVANCEES
                                    if cle in valeurs}
        if (point := valeurs.pop(CONF_POINT_INTERMEDIAIRE, None)) is not None:
            valeurs[LUX_INTERMEDIAIRE], valeurs[LUMINOSITE_INTERMEDIAIRE] = point
        if champs_point is not None:
            # Saisie refusée : réafficher ce qui a été tapé, même incomplet.
            valeurs.update(champs_point)
        return self.async_show_form(
            step_id="init", errors=erreurs,
            data_schema=self.add_suggested_values_to_schema(schema, valeurs))
