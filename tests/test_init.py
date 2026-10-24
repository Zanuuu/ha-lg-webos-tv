"""Cycle de vie de l'entrée : connexion en tâche de fond, déchargement,
réauthentification quand le téléviseur refuse la clé."""

from unittest.mock import patch

import pytest

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lg_webos_tv.const import CONF_CLE_CLIENT, DOMAIN

from .conftest import attendre


@pytest.fixture
def entree(hass: HomeAssistant, tmp_path):
    hass.config.config_dir = str(tmp_path)
    entree = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "192.0.2.10",
                                                  CONF_CLE_CLIENT: "cle"})
    entree.add_to_hass(hass)
    return entree


@pytest.fixture
def client_simule(faux_client):
    async def construire(hote, **options):
        assert options == {"client_key": "cle"}
        return faux_client
    with patch("custom_components.lg_webos_tv.televiseur._construire_client", construire):
        yield faux_client


async def test_installation_et_dechargement(hass: HomeAssistant, entree, client_simule, tmp_path):
    assert await hass.config_entries.async_setup(entree.entry_id)
    assert entree.state is ConfigEntryState.LOADED
    tv = entree.runtime_data.televiseur
    assert await attendre(lambda: tv.etat_connexion == "connecte")
    assert tv.mode_image == "expert2"
    assert (tmp_path / DOMAIN / "historique.sqlite").is_file()

    assert await hass.config_entries.async_unload(entree.entry_id)
    assert entree.state is ConfigEntryState.NOT_LOADED
    assert tv.etat_connexion == "deconnecte"


async def test_cle_refusee_ouvre_la_reauthentification(hass: HomeAssistant, entree,
                                                         client_simule):
    client_simule.non_enregistre = True
    assert await hass.config_entries.async_setup(entree.entry_id)
    await hass.async_block_till_done()
    assert await attendre(lambda: any(
        flux["context"]["source"] == SOURCE_REAUTH
        for flux in hass.config_entries.flow.async_progress_by_handler(DOMAIN)))
    assert await hass.config_entries.async_unload(entree.entry_id)


async def test_construction_du_client_hors_boucle(hass: HomeAssistant):
    """Le constructeur de bscpylgtv lit le manifeste et crée un contexte SSL,
    deux opérations bloquantes : il doit s'exécuter hors du fil de la boucle
    (le harnais de test ne détecte pas ces appels-là de lui-même)."""
    import threading

    from bscpylgtv import WebOsClient

    from custom_components.lg_webos_tv.televiseur import _construire_client

    fils = []
    init_origine = WebOsClient.__init__

    def init_espion(self, *args, **kwargs):
        fils.append(threading.current_thread())
        init_origine(self, *args, **kwargs)

    with patch.object(WebOsClient, "__init__", init_espion):
        client = await _construire_client("192.0.2.10", client_key="cle")
    assert fils and fils[0] is not threading.main_thread()
    assert client.manifest["appId"] == "io.github.zanuuu.reglages-tv"
    assert client.storage is None
