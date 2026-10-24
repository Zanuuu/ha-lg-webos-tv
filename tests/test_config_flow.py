"""Flux de configuration : saisie, découverte SSDP, appairage, réauth,
changement d'adresse."""

from unittest.mock import patch

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.ssdp import (ATTR_UPNP_FRIENDLY_NAME,
                                                     ATTR_UPNP_UDN,
                                                     SsdpServiceInfo)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lg_webos_tv.const import CONF_CLE_CLIENT, DOMAIN
from custom_components.lg_webos_tv.televiseur import AppairageEchoue

APPAIRER = "custom_components.lg_webos_tv.config_flow.appairer"


@pytest.fixture(autouse=True)
def sans_installation():
    # Les tests du flux ne démarrent pas de connexion réelle au téléviseur.
    with patch("custom_components.lg_webos_tv.async_setup_entry", return_value=True):
        yield


async def appairer_ok(hote):
    return "cle-recue"


async def appairer_ko(hote):
    raise AppairageEchoue("refusée")


async def mener_appairage(hass: HomeAssistant, resultat):
    """Fait avancer l'étape de progression jusqu'à son terme."""
    assert resultat["type"] is FlowResultType.SHOW_PROGRESS
    assert resultat["progress_action"] == "appairage"
    await hass.async_block_till_done()
    return await hass.config_entries.flow.async_configure(resultat["flow_id"])


async def test_saisie_puis_appairage(hass: HomeAssistant):
    resultat = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert resultat["type"] is FlowResultType.FORM
    with patch(APPAIRER, appairer_ok):
        resultat = await hass.config_entries.flow.async_configure(
            resultat["flow_id"], {CONF_HOST: "192.0.2.10"})
        resultat = await mener_appairage(hass, resultat)
    assert resultat["type"] is FlowResultType.CREATE_ENTRY
    assert resultat["data"] == {CONF_HOST: "192.0.2.10", CONF_CLE_CLIENT: "cle-recue"}


async def test_appairage_refuse_revient_a_la_saisie(hass: HomeAssistant):
    resultat = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch(APPAIRER, appairer_ko):
        resultat = await hass.config_entries.flow.async_configure(
            resultat["flow_id"], {CONF_HOST: "192.0.2.10"})
        resultat = await mener_appairage(hass, resultat)
    assert resultat["type"] is FlowResultType.FORM
    assert resultat["step_id"] == "user"
    assert resultat["errors"] == {"base": "appairage_echoue"}

    # Nouvel essai depuis le même flux.
    with patch(APPAIRER, appairer_ok):
        resultat = await hass.config_entries.flow.async_configure(
            resultat["flow_id"], {CONF_HOST: "192.0.2.10"})
        resultat = await mener_appairage(hass, resultat)
    assert resultat["type"] is FlowResultType.CREATE_ENTRY


async def test_decouverte_ssdp(hass: HomeAssistant):
    decouverte = SsdpServiceInfo(
        ssdp_usn="uuid:abc::urn:lge-com:service:webos-second-screen:1",
        ssdp_st="urn:lge-com:service:webos-second-screen:1",
        ssdp_location="http://192.0.2.20:1914/",
        upnp={ATTR_UPNP_FRIENDLY_NAME: "[LG] webOS TV OLED65G5", ATTR_UPNP_UDN: "uuid:abc"},
    )
    resultat = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_SSDP}, data=decouverte)
    assert resultat["type"] is FlowResultType.FORM
    assert resultat["step_id"] == "confirmer_decouverte"
    with patch(APPAIRER, appairer_ok):
        resultat = await hass.config_entries.flow.async_configure(resultat["flow_id"], {})
        resultat = await mener_appairage(hass, resultat)
    assert resultat["type"] is FlowResultType.CREATE_ENTRY
    assert resultat["title"] == "LG webOS TV OLED65G5"
    assert resultat["data"][CONF_HOST] == "192.0.2.20"


async def test_une_seule_entree(hass: HomeAssistant):
    MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "192.0.2.10",
                                         CONF_CLE_CLIENT: "cle"}).add_to_hass(hass)
    resultat = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert resultat["type"] is FlowResultType.ABORT
    assert resultat["reason"] == "single_instance_allowed"


async def test_reauthentification(hass: HomeAssistant):
    entree = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "192.0.2.10",
                                                  CONF_CLE_CLIENT: "ancienne"})
    entree.add_to_hass(hass)
    resultat = await entree.start_reauth_flow(hass)
    assert resultat["step_id"] == "reauth_confirm"

    with patch(APPAIRER, appairer_ko):
        resultat = await hass.config_entries.flow.async_configure(resultat["flow_id"], {})
        resultat = await mener_appairage(hass, resultat)
    assert resultat["step_id"] == "reauth_confirm"
    assert resultat["errors"] == {"base": "appairage_echoue"}

    with patch(APPAIRER, appairer_ok):
        resultat = await hass.config_entries.flow.async_configure(resultat["flow_id"], {})
        resultat = await mener_appairage(hass, resultat)
    assert resultat["type"] is FlowResultType.ABORT
    assert resultat["reason"] == "reauth_successful"
    assert entree.data[CONF_CLE_CLIENT] == "cle-recue"


async def test_changement_d_adresse_garde_la_cle(hass: HomeAssistant):
    entree = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "192.0.2.10",
                                                  CONF_CLE_CLIENT: "cle"})
    entree.add_to_hass(hass)
    resultat = await entree.start_reconfigure_flow(hass)
    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"], {CONF_HOST: "192.0.2.11"})
    assert resultat["reason"] == "reconfigure_successful"
    assert entree.data == {CONF_HOST: "192.0.2.11", CONF_CLE_CLIENT: "cle"}
