"""Luminosité adaptative, exécutée dans Home Assistant contre l'intégration
et un téléviseur simulé."""

import copy
import json
from datetime import timedelta
from pathlib import Path

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.lg_webos_tv.const import (CONF_CAPTEUR_LUX, DOMAIN,
                                                 OPTIONS_LUMINOSITE_DEFAUT)
from custom_components.lg_webos_tv.luminosite_adaptative import (ID_MODE,
                                                                 ID_OLED,
                                                                 modes_proposes)
from custom_components.lg_webos_tv.presets import capturer_snapshot

from .conftest import entite

LUX = "sensor.salon_lux"
TELECOMMANDE = "com.webos.app.quicksettings"


@pytest.fixture
def options_entree():
    return {CONF_CAPTEUR_LUX: LUX}


async def passer_le_temps(hass, secondes=2.0):
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=secondes))
    await hass.async_block_till_done(wait_background_tasks=True)


async def regler_lux(hass, lux):
    hass.states.async_set(LUX, str(lux), {"device_class": "illuminance",
                                          "unit_of_measurement": "lx"})
    await passer_le_temps(hass)


def etat(hass):
    return hass.states.get(entite(hass, "sensor", "luminosite_adaptative_etat"))


def luminosite(faux_client):
    return int(faux_client.valeurs["picture"]["backlight"])


@pytest.fixture
async def fonction(hass: HomeAssistant, installe, faux_client):
    # Mode non calibré : les modes Expert sont laissés de côté par défaut.
    await faux_client.notifier("picture", {"pictureMode": "vivid"}, caller=TELECOMMANDE)
    # ln(20/5) / ln(300/5) = 0,339 → 40 + 0,339 × 60 = 60,3
    await regler_lux(hass, 20)
    assert luminosite(faux_client) == 60
    assert etat(hass).state == "active"
    return installe


# ------------------------------------------------------------------ courbe

async def test_echelle_logarithmique(hass: HomeAssistant, fonction, faux_client):
    await regler_lux(hass, 300)
    assert luminosite(faux_client) == 100
    await regler_lux(hass, 2)  # sous le minimum : luminosité minimale
    assert luminosite(faux_client) == 40
    # ln(50/5) / ln(300/5) = 0,562 → 40 + 0,562 × 60 = 73,7
    await regler_lux(hass, 50)
    assert luminosite(faux_client) == 74
    assert etat(hass).attributes["cible"] == 74
    assert etat(hass).attributes["lux"] == 50


async def test_petit_ecart_ignore(hass: HomeAssistant, fonction, faux_client):
    historique = fonction.runtime_data.historique
    ecritures = len(await historique.lister())
    await regler_lux(hass, 22)  # cible 62 : écart de 2 < 3
    assert len(await historique.lister()) == ecritures


async def test_ecritures_historisees_avec_leur_origine(hass: HomeAssistant, fonction):
    derniere = (await fonction.runtime_data.historique.lister())[0]
    assert derniere["origine"] == "luminosite_adaptative"
    assert derniere["entree_id"] == ID_OLED
    # Ses propres écritures ne valent pas reprise en main.
    assert etat(hass).state == "active"


async def test_changement_d_entree_reapplique(hass: HomeAssistant, fonction, faux_client):
    # Autre entrée HDMI : le téléviseur rappelle la luminosité qui lui est
    # propre, sans changement de mode.
    await faux_client.notifier("picture", {"backlight": "85"}, caller=None)
    await passer_le_temps(hass)
    assert luminosite(faux_client) == 60


# ------------------------------------------------------------------- pause

async def test_pause_apres_reglage_manuel_puis_rallumage(hass: HomeAssistant, fonction,
                                                          faux_client):
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await regler_lux(hass, 300)
    assert luminosite(faux_client) == 55
    assert etat(hass).state == "pause"
    assert etat(hass).attributes["fin_pause"] is not None

    # Le téléviseur s'éteint puis se rallume : la pause est levée.
    tv = fonction.runtime_data.televiseur
    await tv._changer_etat("deconnecte")
    await tv._changer_etat("connecte")
    await passer_le_temps(hass)
    assert luminosite(faux_client) == 100
    assert etat(hass).state == "active"


async def test_un_autre_reglage_ne_leve_pas_la_pause(hass: HomeAssistant, fonction,
                                                     faux_client):
    """Défaut du blueprint : il ne regardait que le dernier réglage manuel."""
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await faux_client.notifier("picture", {"contrast": "90"}, caller=TELECOMMANDE)
    await regler_lux(hass, 300)
    assert luminosite(faux_client) == 55
    assert etat(hass).state == "pause"


async def test_fin_de_pause_apres_le_delai(hass: HomeAssistant, fonction, faux_client):
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await passer_le_temps(hass, 119 * 60)
    assert luminosite(faux_client) == 55
    await passer_le_temps(hass, 121 * 60)
    assert luminosite(faux_client) == 60


async def test_reglage_depuis_home_assistant_met_en_pause(hass: HomeAssistant, fonction,
                                                          faux_client):
    await hass.services.async_call("number", "set_value", {
        "entity_id": entite(hass, "number", ID_OLED), "value": 30}, blocking=True)
    await regler_lux(hass, 300)
    assert luminosite(faux_client) == 30
    assert etat(hass).state == "pause"


async def test_preset_respecte(hass: HomeAssistant, fonction, faux_client):
    """Le changement de mode du preset fait rappeler une luminosité par le
    téléviseur ; la fonction ne doit pas s'intercaler avant que le preset
    pose la sienne."""
    d = fonction.runtime_data
    reglages = copy.deepcopy(d.televiseur.etat)
    reglages["picture"] |= {"pictureMode": "cinema", "backlight": 45}
    await d.presets.sauvegarder("Soirée", capturer_snapshot(
        reglages, "cinema", [ID_MODE, ID_OLED]))
    await hass.async_block_till_done()

    await hass.services.async_call(DOMAIN, "appliquer_preset", {"nom": "Soirée"},
                                   blocking=True, return_response=True)
    await passer_le_temps(hass, 5)
    assert faux_client.valeurs["picture"]["pictureMode"] == "cinema"
    assert luminosite(faux_client) == 45
    assert etat(hass).state == "pause"


async def test_lot_en_cours_repousse_l_application(hass: HomeAssistant, fonction,
                                                   faux_client):
    """Un preset réel écrit ses réglages un à un sur plusieurs secondes : tant
    qu'il écrit, la fonction attend, pour ne pas s'intercaler."""
    await faux_client.notifier("picture", {"backlight": "85"}, caller=None)
    await fonction.runtime_data.historique.enregistrer(
        "image.parametres-avances.luminosite.ajuster-le-contraste", "picture",
        "contrast", 100, 90, "vivid", "preset")
    await passer_le_temps(hass, 2)
    assert luminosite(faux_client) == 85
    await passer_le_temps(hass, 4)
    assert luminosite(faux_client) == 60


async def test_reglage_manuel_dans_un_mode_exclu_sans_pause(hass: HomeAssistant, fonction,
                                                           faux_client):
    await faux_client.notifier("picture", {"pictureMode": "expert2"}, caller=TELECOMMANDE)
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await passer_le_temps(hass)
    assert etat(hass).state == "mode_exclu"

    await faux_client.notifier("picture", {"pictureMode": "vivid"}, caller=TELECOMMANDE)
    await passer_le_temps(hass)
    assert luminosite(faux_client) == 60


async def test_pause_conservee_au_redemarrage(hass: HomeAssistant, fonction, faux_client):
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(fonction.entry_id)
    await passer_le_temps(hass)
    assert etat(hass).state == "pause"
    assert luminosite(faux_client) == 55


# ------------------------------------------------------------------- modes

async def test_mode_calibre_laisse_de_cote(hass: HomeAssistant, fonction, faux_client):
    await faux_client.notifier("picture", {"pictureMode": "expert2"}, caller=TELECOMMANDE)
    await regler_lux(hass, 300)
    assert luminosite(faux_client) == 60
    assert etat(hass).state == "mode_exclu"


@pytest.mark.parametrize("mode", ["hdrStandard", "dolbyHdrCinema", "creator"])
async def test_hdr_et_modes_inconnus_laisses_de_cote(hass: HomeAssistant, fonction,
                                                     faux_client, mode):
    await faux_client.notifier("picture", {"pictureMode": mode}, caller=None)
    await regler_lux(hass, 300)
    assert luminosite(faux_client) == 60
    assert etat(hass).state == "mode_exclu"


# --------------------------------------------------------------- commandes

async def test_interrupteur_et_bouton_reprendre(hass: HomeAssistant, fonction, faux_client):
    interrupteur = entite(hass, "switch", "luminosite_adaptative")
    await hass.services.async_call("switch", "turn_off", {"entity_id": interrupteur},
                                   blocking=True)
    await regler_lux(hass, 300)
    assert luminosite(faux_client) == 60
    assert etat(hass).state == "desactivee"

    await hass.services.async_call("switch", "turn_on", {"entity_id": interrupteur},
                                   blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert luminosite(faux_client) == 100

    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    assert etat(hass).state == "pause"
    await hass.services.async_call("button", "press", {
        "entity_id": entite(hass, "button", "luminosite_adaptative_reprendre")},
        blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert luminosite(faux_client) == 100
    assert etat(hass).state == "active"


async def commande(ws, type_, **donnees) -> tuple[list[dict], dict]:
    """Envoie une commande ; renvoie les événements reçus avant sa réponse,
    et la réponse."""
    await ws.client.send_json({"id": next(ws.compteur), "type": type_, **donnees})
    evenements = []
    while (message := await ws.client.receive_json()).get("type") != "result":
        evenements.append(message["event"])
    return evenements, message


def etats_luminosite(evenements: list[dict]) -> list[str]:
    return [e["etat"] for e in evenements if e["type"] == "luminosite_adaptative"]


async def test_panneau_suit_l_etat_et_reprend(hass: HomeAssistant, fonction, faux_client, ws):
    abonnement = await ws("abonner")
    assert abonnement["success"]
    instantane = (await ws.client.receive_json())["event"]
    assert instantane["luminosite_adaptative"] == {
        "etat": "active", "entree_id": ID_OLED, "cible": 60, "fin_pause": None}

    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    evenements, _ = await commande(ws, "lg_webos_tv/reglages")
    assert etats_luminosite(evenements) == ["pause"]
    pause = next(e for e in evenements if e["type"] == "luminosite_adaptative")
    assert pause["fin_pause"] is not None

    # Nouvelle mesure, même cible : rien à relayer au panneau.
    await regler_lux(hass, 19.5)
    evenements, _ = await commande(ws, "lg_webos_tv/reglages")
    assert etats_luminosite(evenements) == []

    evenements, reponse = await commande(ws, "lg_webos_tv/luminosite_adaptative/reprendre")
    assert etats_luminosite(evenements) == ["active"]
    assert reponse["result"]["etat"] == "active" and reponse["result"]["fin_pause"] is None
    await hass.async_block_till_done(wait_background_tasks=True)
    assert luminosite(faux_client) == 60

    # Désabonnement : l'écouteur de la fonction est retiré.
    ecouteurs = fonction.runtime_data.luminosite_adaptative._ecouteurs
    avant = len(ecouteurs)
    await commande(ws, "unsubscribe_events", subscription=abonnement["id"])
    assert len(ecouteurs) == avant - 1


async def test_consultation(hass: HomeAssistant, fonction):
    await fonction.runtime_data.televiseur._changer_ecriture(None)
    await hass.async_block_till_done()
    assert etat(hass).state == "consultation"


async def test_capteur_indisponible(hass: HomeAssistant, fonction, faux_client):
    await regler_lux(hass, "unavailable")
    assert etat(hass).state == "capteur_indisponible"
    assert luminosite(faux_client) == 60


# ----------------------------------------------------------------- options

@pytest.mark.parametrize("options_entree", [{}])
async def test_options_creent_puis_retirent_la_fonction(hass: HomeAssistant, installe):
    assert entite(hass, "switch", "luminosite_adaptative") is None
    assert installe.runtime_data.luminosite_adaptative is None

    flux = await hass.config_entries.options.async_init(installe.entry_id)
    assert flux["type"] is FlowResultType.FORM
    saisie = {**OPTIONS_LUMINOSITE_DEFAUT, CONF_CAPTEUR_LUX: LUX}
    flux = await hass.config_entries.options.async_configure(
        flux["flow_id"], {**saisie, "lux_max": 5})
    assert flux["errors"] == {"lux_max": "lux_max_trop_bas"}
    flux = await hass.config_entries.options.async_configure(
        flux["flow_id"], {**saisie, "luminosite_min": 80, "luminosite_max": 60})
    assert flux["errors"] == {"luminosite_max": "luminosite_max_trop_basse"}
    flux = await hass.config_entries.options.async_configure(flux["flow_id"], saisie)
    assert flux["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert installe.options[CONF_CAPTEUR_LUX] == LUX
    for plateforme, unique_id in (("switch", "luminosite_adaptative"),
                                  ("sensor", "luminosite_adaptative_etat"),
                                  ("button", "luminosite_adaptative_reprendre")):
        assert entite(hass, plateforme, unique_id) is not None

    flux = await hass.config_entries.options.async_init(installe.entry_id)
    sans_capteur = {k: v for k, v in saisie.items() if k != CONF_CAPTEUR_LUX}
    await hass.config_entries.options.async_configure(flux["flow_id"], sans_capteur)
    await hass.async_block_till_done()
    assert installe.runtime_data.luminosite_adaptative is None
    assert entite(hass, "switch", "luminosite_adaptative") is None
    assert entite(hass, "button", "luminosite_adaptative_reprendre") is None


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_modes_proposes_traduits(langue):
    traductions = json.loads((Path(__file__).parent.parent / "custom_components" / DOMAIN
                              / "translations" / f"{langue}.json").read_text())
    assert list(traductions["selector"]["modes_exclus"]["options"]) == modes_proposes()
