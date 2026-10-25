"""Luminosité adaptative, exécutée dans Home Assistant contre l'intégration
et un téléviseur simulé."""

import copy
import json
from datetime import timedelta
from pathlib import Path

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.lg_webos_tv.const import (CONF_CAPTEUR_LUX, DOMAIN,
                                                 OPTIONS_LUMINOSITE_DEFAUT)
from custom_components.lg_webos_tv.luminosite_adaptative import (
    BORNES, ID_MODE, ID_OLED, modes_proposes, valider_options)
from custom_components.lg_webos_tv import restauration
from custom_components.lg_webos_tv.diagnostics import \
    async_get_config_entry_diagnostics
from custom_components.lg_webos_tv.presets import capturer_snapshot
from custom_components.lg_webos_tv.sante import Accumulateur, StatsJour

from .conftest import entite

LUX = "sensor.salon_lux"
TELECOMMANDE = "com.webos.app.quicksettings"


@pytest.fixture
def options_entree():
    return {CONF_CAPTEUR_LUX: LUX}


# Horloge simulée : le filtre du lux se calcule sur le temps réellement
# écoulé (dt_util.utcnow), pas seulement sur les minuteries déclenchées.
_horloge = None


@pytest.fixture(autouse=True)
def horloge(freezer):
    global _horloge
    _horloge = freezer
    yield freezer
    _horloge = None


async def _pas(hass, secondes):
    _horloge.tick(timedelta(seconds=secondes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


# Un pas de rampe par tick : 2 points toutes les 0,5 s, le débit par défaut.
TICK_S = 0.5


async def _pas_a_pas(hass, secondes):
    while secondes > 0:
        await _pas(hass, min(secondes, TICK_S))
        secondes -= TICK_S


async def passer_le_temps(hass, secondes=2.0):
    """Par pas d'une demi-seconde, pour que chaque évaluation ou pas de rampe
    programmé par le précédent ait lieu à son heure ; au-delà de deux
    minutes, une minute pas à pas, un saut, puis une minute pas à pas."""
    if secondes > 120:
        await _pas_a_pas(hass, 60)
        await _pas(hass, secondes - 120)
        secondes = 60
    await _pas_a_pas(hass, secondes)


# Assez pour un saut confirmé (8 s), le filtre (15 s en descente) et la
# rampe qui le suit jusqu'à son arrivée.
STABILISATION_S = 120
# Une rampe de 40 points à 4 points par seconde, avec de la marge.
RAMPE_S = 20


async def regler_lux(hass, lux, secondes=STABILISATION_S):
    hass.states.async_set(LUX, str(lux), {"device_class": "illuminance",
                                          "unit_of_measurement": "lx"})
    await passer_le_temps(hass, secondes)


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
    # Après une transition en plusieurs pas, le téléviseur peut rester en
    # deçà de l'écart minimal (3) de la cible : c'est le rôle de cet écart.
    await regler_lux(hass, 300)
    assert etat(hass).attributes["cible"] == 100
    assert 98 <= luminosite(faux_client) <= 100
    await regler_lux(hass, 2)  # sous le minimum : luminosité minimale
    assert etat(hass).attributes["cible"] == 40
    assert 40 <= luminosite(faux_client) <= 42
    # ln(50/5) / ln(300/5) = 0,562 → 40 + 0,562 × 60 = 73,7
    await regler_lux(hass, 50)
    assert etat(hass).attributes["cible"] == 74
    assert abs(luminosite(faux_client) - 74) <= 2
    assert etat(hass).attributes["lux"] == 50
    assert etat(hass).attributes["lux_filtre"] == pytest.approx(50, rel=0.01)


async def test_petit_ecart_ignore(hass: HomeAssistant, fonction, faux_client):
    """Écart minimal de 2 par défaut. Une valeur rappelée par le téléviseur
    (changement d'entrée) relance le calcul sans hystérésis."""
    await faux_client.notifier("picture", {"backlight": "61"}, caller=None)
    await passer_le_temps(hass, RAMPE_S)
    assert luminosite(faux_client) == 61
    await faux_client.notifier("picture", {"backlight": "62"}, caller=None)
    await passer_le_temps(hass, RAMPE_S)
    assert luminosite(faux_client) == 60


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
    await passer_le_temps(hass, RAMPE_S)
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
    await passer_le_temps(hass, RAMPE_S)
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
    await passer_le_temps(hass, RAMPE_S)
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
    assert etat(hass).attributes["cause_pause"] == "manuel"
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
    await passer_le_temps(hass, RAMPE_S)
    assert luminosite(faux_client) == 100

    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    assert etat(hass).state == "pause"
    await hass.services.async_call("button", "press", {
        "entity_id": entite(hass, "button", "luminosite_adaptative_reprendre")},
        blocking=True)
    await passer_le_temps(hass, RAMPE_S)
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
        "etat": "active", "entree_id": ID_OLED, "cible": 60, "fin_pause": None,
        "cause_pause": None, "conflit": None, "rampe": None}

    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    evenements, _ = await commande(ws, "lg_webos_tv/reglages")
    assert etats_luminosite(evenements) == ["pause"]
    pause = next(e for e in evenements if e["type"] == "luminosite_adaptative")
    assert pause["fin_pause"] is not None
    assert pause["cause_pause"]["origine"] == "manuel"

    # Nouvelle mesure, même cible : rien à relayer au panneau.
    await regler_lux(hass, 19.5, secondes=2)
    evenements, _ = await commande(ws, "lg_webos_tv/reglages")
    assert etats_luminosite(evenements) == []

    evenements, reponse = await commande(ws, "lg_webos_tv/luminosite_adaptative/reprendre")
    assert etats_luminosite(evenements) == ["active"]
    assert reponse["result"]["etat"] == "active" and reponse["result"]["fin_pause"] is None
    await passer_le_temps(hass, 5)
    assert luminosite(faux_client) == 60

    # Désabonnement : l'écouteur de la fonction est retiré.
    ecouteurs = fonction.runtime_data.luminosite_adaptative._ecouteurs
    avant = len(ecouteurs)
    await commande(ws, "unsubscribe_events", subscription=abonnement["id"])
    assert len(ecouteurs) == avant - 1


# ------------------------------------------------------- cause et journal

def types_journal(fonction_entree) -> list[str]:
    return [e["type"] for e in fonction_entree.runtime_data.luminosite_adaptative.journal]


async def test_cause_de_pause_et_journal(hass: HomeAssistant, fonction, faux_client):
    la = fonction.runtime_data.luminosite_adaptative
    assert la.journal[-1] | {"horodatage": None} == {
        "horodatage": None, "type": "application", "lux": 20.0, "lux_brut": 20.0,
        "cible": 60, "ancienne": 80, "pas": 11, "duree_s": 5.0, "fin": "arrivee"}

    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    assert la.cause_pause["origine"] == "manuel"
    assert la.journal[-1]["type"] == "pause" and la.journal[-1]["origine"] == "manuel"

    la.reprendre()
    await passer_le_temps(hass, 5)
    assert la.cause_pause is None
    assert types_journal(fonction)[-2:] == ["reprise", "application"]
    assert la.journal[-2]["raison"] == "bouton"


async def test_cause_reglage_depuis_home_assistant(hass: HomeAssistant, fonction):
    await hass.services.async_call("number", "set_value", {
        "entity_id": entite(hass, "number", ID_OLED), "value": 30}, blocking=True)
    await hass.async_block_till_done()
    assert etat(hass).attributes["cause_pause"] == "home_assistant"


async def test_pause_manuelle(hass: HomeAssistant, fonction, faux_client):
    la = fonction.runtime_data.luminosite_adaptative
    la.mettre_en_pause(60)
    await regler_lux(hass, 300)
    assert luminosite(faux_client) == 60
    assert etat(hass).state == "pause"
    assert la.cause_pause["origine"] == "pause_manuelle"
    await passer_le_temps(hass, 61 * 60)
    assert luminosite(faux_client) == 100
    assert la.journal[-2]["raison"] == "delai"


async def test_desactivation_notee_sans_reprise(hass: HomeAssistant, fonction, faux_client):
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    fonction.runtime_data.luminosite_adaptative.activer(False)
    assert types_journal(fonction)[-2:] == ["pause", "desactivation"]


async def test_journal_plafonne(hass: HomeAssistant, fonction):
    la = fonction.runtime_data.luminosite_adaptative
    for _ in range(60):
        la.mettre_en_pause(10)
    assert len(la.journal) == 50


async def test_reconfiguration_a_chaud(hass: HomeAssistant, fonction, faux_client):
    la = fonction.runtime_data.luminosite_adaptative
    la.reconfigurer({**la.options, "luminosite_max": 80})
    await passer_le_temps(hass, RAMPE_S)
    # ln(20/5) / ln(300/5) = 0,339 → 40 + 0,339 × 40 = 53,5
    assert luminosite(faux_client) == 54

    hass.states.async_set("sensor.bureau_lux", "300", {"device_class": "illuminance"})
    la.reconfigurer({**la.options, CONF_CAPTEUR_LUX: "sensor.bureau_lux"})
    await passer_le_temps(hass, RAMPE_S)
    assert luminosite(faux_client) == 80
    # L'ancien capteur n'est plus suivi.
    await regler_lux(hass, 5)
    assert luminosite(faux_client) == 80


async def test_consultation(hass: HomeAssistant, fonction):
    await fonction.runtime_data.televiseur._changer_ecriture(None)
    await hass.async_block_till_done()
    assert etat(hass).state == "consultation"


async def test_capteur_indisponible(hass: HomeAssistant, fonction, faux_client):
    await regler_lux(hass, "unavailable")
    assert etat(hass).state == "capteur_indisponible"
    assert luminosite(faux_client) == 60


# ------------------------------------------------------ page du panneau

async def test_page_configuration(hass: HomeAssistant, fonction, ws):
    hass.states.async_set("sensor.temperature", "21", {"device_class": "temperature"})
    reponse = await ws("luminosite_adaptative/configuration")
    resultat = reponse["result"]
    assert resultat["options"] == {**OPTIONS_LUMINOSITE_DEFAUT, CONF_CAPTEUR_LUX: LUX}
    assert resultat["modes_proposes"] == modes_proposes()
    assert [c["entity_id"] for c in resultat["capteurs"]] == [LUX]
    assert resultat["capteurs"][0]["valeur"] == "20"


async def test_page_configurer_sans_rechargement(hass: HomeAssistant, fonction, faux_client,
                                                 ws):
    la = fonction.runtime_data.luminosite_adaptative
    reponse = await ws("luminosite_adaptative/configurer",
                       options={"lux_min": 400, "inconnue": 1})
    assert reponse["error"]["code"] == "invalide"
    assert "lux_max" in reponse["error"]["message"]

    reponse = await ws("luminosite_adaptative/configurer",
                       options={"luminosite_max": 80.0, "modes_exclus": []})
    assert reponse["result"] == {"recharge": False}
    await passer_le_temps(hass)
    assert fonction.runtime_data.luminosite_adaptative is la
    assert fonction.options["luminosite_max"] == 80
    assert isinstance(fonction.options["luminosite_max"], int)
    assert "inconnue" not in fonction.options
    assert luminosite(faux_client) == 54

    reponse = await ws("luminosite_adaptative/configurer",
                       options={CONF_CAPTEUR_LUX: "sensor.absent"})
    assert reponse["error"]["code"] == "invalide"


async def test_page_retirer_puis_creer_la_fonction(hass: HomeAssistant, fonction, ws):
    reponse = await ws("luminosite_adaptative/configurer", options={CONF_CAPTEUR_LUX: None})
    assert reponse["result"] == {"recharge": True}
    assert fonction.runtime_data.luminosite_adaptative is None
    assert CONF_CAPTEUR_LUX not in fonction.options
    assert entite(hass, "switch", "luminosite_adaptative") is None
    reponse = await ws("luminosite_adaptative/configuration")
    assert reponse["result"]["options"][CONF_CAPTEUR_LUX] is None

    reponse = await ws("luminosite_adaptative/configurer", options={CONF_CAPTEUR_LUX: LUX})
    assert reponse["result"] == {"recharge": True}
    assert fonction.runtime_data.luminosite_adaptative is not None
    assert entite(hass, "switch", "luminosite_adaptative") is not None


async def test_page_activer_et_pause(hass: HomeAssistant, fonction, faux_client, ws):
    reponse = await ws("luminosite_adaptative/pause", minutes=60)
    assert reponse["result"]["etat"] == "pause"
    assert reponse["result"]["cause_pause"]["origine"] == "pause_manuelle"
    reponse = await ws("luminosite_adaptative/activer", active=False)
    assert reponse["result"]["etat"] == "desactivee"
    reponse = await ws("luminosite_adaptative/activer", active=True)
    assert reponse["result"]["etat"] == "active"


async def test_page_suivi(hass: HomeAssistant, fonction, faux_client, ws):
    abonnement = await ws("luminosite_adaptative/suivre")
    assert abonnement["success"]
    instantane = (await ws.client.receive_json())["event"]
    assert instantane["type"] == "instantane"
    assert instantane["details"]["lux"] == 20.0
    assert instantane["details"]["actuelle"] == 60.0
    assert instantane["details"]["mode_image"] == "vivid"
    assert [e["type"] for e in instantane["journal"]][-1] == "application"

    # Le lux est suivi même quand la cible ne change pas.
    await regler_lux(hass, 19.5, secondes=2)
    evenements, _ = await commande(ws, "lg_webos_tv/reglages")
    assert [e["details"]["lux"] for e in evenements if e["type"] == "details"] == [19.5]

    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    evenements, _ = await commande(ws, "lg_webos_tv/reglages")
    assert [e["evenement"]["type"] for e in evenements if e["type"] == "journal"] == ["pause"]

    la = fonction.runtime_data.luminosite_adaptative
    ecouteurs = (la._ecouteurs, la._ecouteurs_details, la._ecouteurs_journal,
                 la._ecouteurs_sante)
    avant = [len(liste) for liste in ecouteurs]
    await commande(ws, "unsubscribe_events", subscription=abonnement["id"])
    assert [len(liste) for liste in ecouteurs] == [n - 1 for n in avant]


async def test_page_suit_la_rampe_pas_a_pas(hass: HomeAssistant, fonction, ws, ecrites):
    """La valeur du téléviseur est transmise à chaque pas, sans réécrire
    l'état des entités."""
    await ws("luminosite_adaptative/suivre")
    await ws.client.receive_json()
    etats_ecrits = []
    hass.bus.async_listen("state_changed", lambda e: etats_ecrits.append(
        e.data["entity_id"]) if "luminosite_adaptative_etat" in e.data["entity_id"] else None)
    await demarrer_rampe(hass, fonction)
    evenements, _ = await commande(ws, "lg_webos_tv/reglages")
    details = [e["details"] for e in evenements if e["type"] == "details"]
    vues = sorted({d["actuelle"] for d in details if d["rampe"] is not None})
    assert len(vues) >= 3 and vues[0] >= 60
    # Chaque pas confirmé est transmis, pas seulement les changements de cible.
    assert set(ecrites) <= {d["actuelle"] for d in details}
    assert all(d["rampe"]["depart"] == 60 for d in details if d["rampe"] is not None)
    assert len(etats_ecrits) < len(vues)


@pytest.mark.parametrize("options_entree", [{}])
async def test_page_sans_fonction(hass: HomeAssistant, installe, ws):
    reponse = await ws("luminosite_adaptative/configuration")
    assert reponse["result"]["options"][CONF_CAPTEUR_LUX] is None
    reponse = await ws("luminosite_adaptative/suivre")
    assert reponse["error"]["code"] == "non_configuree"


# ----------------------------------------------------------------- options

@pytest.mark.parametrize("options_entree", [{}])
async def test_options_creent_puis_retirent_la_fonction(hass: HomeAssistant, installe):
    assert entite(hass, "switch", "luminosite_adaptative") is None
    assert installe.runtime_data.luminosite_adaptative is None

    flux = await hass.config_entries.options.async_init(installe.entry_id)
    assert flux["type"] is FlowResultType.FORM
    # Écart minimal et constantes du signal dans la section repliée.
    saisie = {**{k: v for k, v in OPTIONS_LUMINOSITE_DEFAUT.items() if k != "ecart_minimal"},
              CONF_CAPTEUR_LUX: LUX, "avance": {"ecart_minimal": 3}}
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


# ------------------------------------------------------------------ signal

def applications(fonction_entree) -> list[dict]:
    return [e for e in fonction_entree.runtime_data.luminosite_adaptative.journal
            if e["type"] == "application"]


async def test_flux_rapide_applique_sans_attendre_sa_fin(hass: HomeAssistant, fonction,
                                                         faux_client):
    """Défaut de la 2.4.0 : un capteur à 0,5 s repoussait l'application sans
    fin (rebond glissant)."""
    for i in range(20):
        hass.states.async_set(LUX, str(40 + (i % 2) * 0.2), {"device_class": "illuminance"})
        await _pas(hass, 0.5)
    assert luminosite(faux_client) > 60


async def test_petite_variation_dans_la_bande_ignoree(hass: HomeAssistant, fonction,
                                                      faux_client):
    nombre = len(applications(fonction))
    for lux in (21, 19, 21.5, 18):  # de −10 % à +8 %
        await regler_lux(hass, lux, secondes=30)
    assert len(applications(fonction)) == nombre
    assert luminosite(faux_client) == 60


# ------------------------------------------------------------------- rampes

@pytest.fixture
def ecrites(faux_client):
    """Valeurs de la luminosité OLED écrites sur le téléviseur, dans l'ordre."""
    valeurs = []
    requete = faux_client.request

    async def espion(uri, payload=None):
        if uri == "settings/setSystemSettings" and "backlight" in payload["settings"]:
            valeurs.append(payload["settings"]["backlight"])
        return await requete(uri, payload)

    faux_client.request = espion
    return valeurs


async def ecritures_depuis(fonction_entree, avant: int) -> list[dict]:
    """Entrées d'historique ajoutées depuis qu'il en comptait `avant`, des
    plus anciennes aux plus récentes."""
    lignes = await fonction_entree.runtime_data.historique.lister()
    return list(reversed(lignes[:len(lignes) - avant]))


async def demarrer_rampe(hass, fonction_entree, lux=300):
    """Lux qui passe de 20 à 300 : saut confirmé en 8 s, puis rampe vers
    100 ; rend la main en pleine rampe, vers 70."""
    await regler_lux(hass, lux, secondes=12)
    la = fonction_entree.runtime_data.luminosite_adaptative
    assert la.rampe is not None
    return la


async def test_une_rampe_une_entree_d_historique(hass: HomeAssistant, fonction, faux_client,
                                                 ecrites):
    avant = len(await fonction.runtime_data.historique.lister())
    nombre = len(applications(fonction))
    await regler_lux(hass, 300)
    # Arrivée exacte : la rampe suit le filtre jusqu'au bout.
    assert luminosite(faux_client) == 100
    assert len(ecrites) >= 20
    assert all(0 < b - a <= 2 for a, b in zip([60, *ecrites], ecrites))
    [entree] = await ecritures_depuis(fonction, avant)
    assert (entree["ancienne"], entree["nouvelle"]) == (60, 100)
    assert entree["origine"] == "luminosite_adaptative" and entree["mode_image"] == "vivid"
    [ligne] = applications(fonction)[nombre:]
    assert (ligne["ancienne"], ligne["cible"], ligne["fin"]) == (60, 100, "arrivee")
    assert ligne["pas"] == len(ecrites)
    assert fonction.runtime_data.luminosite_adaptative.rampe is None


async def test_descente_suit_le_filtre_jusqu_a_la_cible(hass: HomeAssistant, fonction,
                                                        faux_client, ecrites):
    """Lot 1 : le téléviseur pouvait s'arrêter 2 points avant la cible."""
    await regler_lux(hass, 300)
    avant = len(await fonction.runtime_data.historique.lister())
    del ecrites[:]
    await regler_lux(hass, 20)
    assert luminosite(faux_client) == 60
    assert all(0 < a - b <= 2 for a, b in zip([100, *ecrites], ecrites))
    [entree] = await ecritures_depuis(fonction, avant)
    assert (entree["ancienne"], entree["nouvelle"]) == (100, 60)


async def test_cible_changee_en_cours_de_rampe(hass: HomeAssistant, fonction, faux_client,
                                               ecrites):
    avant = len(await fonction.runtime_data.historique.lister())
    la = await demarrer_rampe(hass, fonction)
    assert la.resume()["rampe"]["depart"] == 60
    details = la.details()
    assert details["rampe"]["pas"] >= 1
    assert details["ecart_minimal"] == 2
    assert details["parametres_rampe"] == {"pas": 1, "debit": 4}
    assert etat(hass).attributes["rampe"]["depart"] == 60
    la.reconfigurer({**la.options, "luminosite_max": 80})
    await passer_le_temps(hass, RAMPE_S)
    assert luminosite(faux_client) == 80
    assert max(ecrites) == 80
    [entree] = await ecritures_depuis(fonction, avant)
    assert (entree["ancienne"], entree["nouvelle"]) == (60, 80)
    assert la.resume()["rampe"] is None


async def test_reprise_en_main_pendant_la_rampe(hass: HomeAssistant, fonction, faux_client,
                                                ecrites):
    avant = len(await fonction.runtime_data.historique.lister())
    nombre = len(applications(fonction))
    await demarrer_rampe(hass, fonction)
    await faux_client.notifier("picture", {"backlight": "45"}, caller=TELECOMMANDE)
    ecrites_avant = len(ecrites)
    await passer_le_temps(hass, RAMPE_S)
    assert luminosite(faux_client) == 45
    assert etat(hass).state == "pause"
    assert len(ecrites) == ecrites_avant
    [entree] = await ecritures_depuis(fonction, avant)
    assert entree["ancienne"] == 60 and 60 < entree["nouvelle"] < 100
    [ligne] = applications(fonction)[nombre:]
    assert ligne["fin"] == "reprise_en_main"


async def test_reglage_depuis_home_assistant_pendant_la_rampe(hass: HomeAssistant, fonction,
                                                              faux_client):
    precedente, *_ = lignes = await fonction.runtime_data.historique.lister()
    avant = len(lignes)
    await demarrer_rampe(hass, fonction)
    await hass.services.async_call("number", "set_value", {
        "entity_id": entite(hass, "number", ID_OLED), "value": 30}, blocking=True)
    await passer_le_temps(hass, RAMPE_S)
    assert luminosite(faux_client) == 30
    assert etat(hass).state == "pause"
    rampe, utilisateur = await ecritures_depuis(fonction, avant)
    assert rampe["origine"] == "luminosite_adaptative"
    assert (utilisateur["origine"], utilisateur["nouvelle"]) == ("home_assistant", 30)

    # Entrée de la rampe à sa place, avant celle de l'utilisateur : le retour
    # à un instant antérieur retrouve le départ de la rampe.
    d = fonction.runtime_data
    await restauration.revenir_a(d.televiseur, d.historique,
                                 (precedente["horodatage"] + rampe["horodatage"]) / 2)
    assert luminosite(faux_client) == 60


async def test_changement_de_mode_pendant_la_rampe(hass: HomeAssistant, fonction, faux_client):
    """La garde de mode arrête la rampe ; une nouvelle part de la luminosité
    propre au nouveau mode."""
    avant = len(await fonction.runtime_data.historique.lister())
    nombre = len(applications(fonction))
    await demarrer_rampe(hass, fonction)
    await faux_client.notifier("picture", {"pictureMode": "cinema"}, caller=TELECOMMANDE)
    await faux_client.notifier("picture", {"backlight": "50"}, caller=None)
    await passer_le_temps(hass, 2 * RAMPE_S)
    assert luminosite(faux_client) == 100
    premiere, seconde = await ecritures_depuis(fonction, avant)
    assert premiere["mode_image"] == "vivid" and premiere["ancienne"] == 60
    assert (seconde["mode_image"], seconde["ancienne"], seconde["nouvelle"]) == (
        "cinema", 50, 100)
    assert [e["fin"] for e in applications(fonction)[nombre:]] == ["mode", "arrivee"]


async def test_rampe_arretee_par_un_mode_laisse_de_cote(hass: HomeAssistant, fonction,
                                                        faux_client, ecrites):
    await demarrer_rampe(hass, fonction)
    await faux_client.notifier("picture", {"pictureMode": "expert1"}, caller=TELECOMMANDE)
    await faux_client.notifier("picture", {"backlight": "50"}, caller=None)
    ecrites_avant = len(ecrites)
    await passer_le_temps(hass, RAMPE_S)
    assert luminosite(faux_client) == 50
    assert len(ecrites) == ecrites_avant
    assert etat(hass).state == "mode_exclu"


async def test_changement_d_entree_pendant_la_rampe(hass: HomeAssistant, fonction,
                                                    faux_client):
    nombre = len(applications(fonction))
    await demarrer_rampe(hass, fonction)
    await faux_client.notifier("picture", {"backlight": "90"}, caller=None)
    await passer_le_temps(hass, RAMPE_S)
    assert luminosite(faux_client) == 100
    lignes = applications(fonction)[nombre:]
    assert [e["fin"] for e in lignes] == ["changement_exterieur", "arrivee"]
    assert lignes[1]["ancienne"] == 90
    assert etat(hass).state == "active"


async def test_ecriture_non_confirmee_arrete_la_rampe(hass: HomeAssistant, fonction,
                                                      faux_client):
    avant = len(await fonction.runtime_data.historique.lister())
    nombre = len(applications(fonction))
    await demarrer_rampe(hass, fonction)
    faux_client.refuser.add(("picture", "backlight"))
    await passer_le_temps(hass, 2)
    la = fonction.runtime_data.luminosite_adaptative
    assert la.rampe is None
    assert "refusée" in la.derniere_erreur
    [entree] = await ecritures_depuis(fonction, avant)
    assert entree["nouvelle"] == luminosite(faux_client)
    assert applications(fonction)[nombre]["fin"] == "non_confirmee"


async def test_retour_arriere_d_une_rampe(hass: HomeAssistant, fonction, faux_client):
    d = fonction.runtime_data
    avant = len(await d.historique.lister())
    await regler_lux(hass, 300)
    [entree] = await ecritures_depuis(fonction, avant)
    resultat = await restauration.annuler_ecriture(d.televiseur, d.historique, entree["id"])
    assert resultat["ok"]
    await passer_le_temps(hass, RAMPE_S)
    # Le départ de la rampe, d'un coup ; et la fonction en pause.
    assert luminosite(faux_client) == 60
    assert etat(hass).state == "pause"
    assert la_cause(fonction) == "annulation"


def la_cause(fonction_entree) -> str:
    return fonction_entree.runtime_data.luminosite_adaptative.cause_pause["origine"]


async def test_mesures_mises_de_cote_pendant_la_rampe(hass: HomeAssistant, fonction,
                                                      faux_client, ecrites):
    """Le lux redescend en pleine rampe : la rampe va au bout, puis la
    mesure s'applique après le gel qui suit sa fin."""
    nombre = len(applications(fonction))
    await demarrer_rampe(hass, fonction)
    await regler_lux(hass, 20)
    assert max(ecrites) == 100
    assert luminosite(faux_client) == 60
    montee, descente = applications(fonction)[nombre:]
    fin_montee = dt_util.parse_datetime(montee["horodatage"])
    debut_descente = (dt_util.parse_datetime(descente["horodatage"])
                      - timedelta(seconds=descente["duree_s"]))
    # Gel de 5 s après la rampe, puis confirmation du saut (facteur 15) en 8 s.
    assert (debut_descente - fin_montee).total_seconds() >= 5 + 8


async def test_emplacement_d_allonge_le_gel_apres_la_rampe(hass: HomeAssistant, fonction,
                                                           faux_client):
    la = fonction.runtime_data.luminosite_adaptative
    la.reconfigurer({**la.options, "emplacement_capteur": "d"})
    assert la.details()["constantes"]["gel_s"] == 20
    nombre = len(applications(fonction))
    await demarrer_rampe(hass, fonction)
    await regler_lux(hass, 20, secondes=200)
    montee, descente = applications(fonction)[nombre:]
    fin_montee = dt_util.parse_datetime(montee["horodatage"])
    debut_descente = (dt_util.parse_datetime(descente["horodatage"])
                      - timedelta(seconds=descente["duree_s"]))
    assert (debut_descente - fin_montee).total_seconds() >= 20 + 8


async def test_saut_isole_ecarte(hass: HomeAssistant, fonction, faux_client):
    await regler_lux(hass, 2000, secondes=3)  # lampe torche sur le capteur
    await regler_lux(hass, 20, secondes=30)
    assert luminosite(faux_client) == 60
    assert "saut_ecarte" in types_journal(fonction)


async def test_profil_d_apres_la_plateforme_puis_la_cadence(hass: HomeAssistant, fonction):
    la = fonction.runtime_data.luminosite_adaptative
    assert la.profil == "inconnu"
    capteur = er.async_get(hass).async_get_or_create(
        "sensor", "zha", "lux-salon", suggested_object_id="salon_lux_zha").entity_id
    hass.states.async_set(capteur, "20", {"device_class": "illuminance"})
    la.reconfigurer({**la.options, CONF_CAPTEUR_LUX: capteur})
    assert la.profil == "sur_variation"
    assert la.details()["constantes"]["lissage_montee_s"] == 0
    # Rapports toutes les 2 s, valeur identique comprise : capteur rapide.
    for _ in range(6):
        hass.states.async_set(capteur, "20", {"device_class": "illuminance"})
        await passer_le_temps(hass, 2)
    assert la.profil == "rapide"
    assert la.details()["profil"] == {"nom": "rapide", "plateforme": "zha", "intervalle_s": 2}


async def test_capteur_fige_puis_retabli(hass: HomeAssistant, fonction, faux_client):
    for _ in range(6):
        await regler_lux(hass, 20, secondes=60)  # rapports identiques chaque minute
    assert etat(hass).state == "active"
    await passer_le_temps(hass, 2 * 3600)
    assert etat(hass).state == "capteur_fige"
    assert ir.async_get(hass).async_get_issue(DOMAIN, "capteur_fige") is not None
    assert "capteur_fige" in types_journal(fonction)

    await regler_lux(hass, 300)
    assert etat(hass).state == "active"
    assert ir.async_get(hass).async_get_issue(DOMAIN, "capteur_fige") is None
    assert luminosite(faux_client) >= 98


# ------------------------------------------------------------- cohabitation

async def test_conflit_economie_energie(hass: HomeAssistant, fonction, faux_client, ws):
    await faux_client.notifier("picture", {"energySaving": "auto"}, caller=TELECOMMANDE)
    # Pas plus de quelques secondes d'un coup : le client websocket de test
    # ne survit pas à un saut d'horloge d'une minute.
    await regler_lux(hass, 300, secondes=20)
    assert etat(hass).state == "conflit_economie_energie"
    assert etat(hass).attributes["conflit"] == "economie_energie"
    assert luminosite(faux_client) == 60  # aucune écriture : deux régulations
    probleme = ir.async_get(hass).async_get_issue(DOMAIN, "conflit_economie_energie")
    assert probleme.is_fixable and probleme.translation_key == "conflit_economie_energie"

    reponse = await ws("luminosite_adaptative/desactiver_economie_energie")
    assert reponse["success"]
    assert faux_client.valeurs["picture"]["energySaving"] == "off"
    await passer_le_temps(hass, 30)
    assert etat(hass).state == "active"
    assert ir.async_get(hass).async_get_issue(DOMAIN, "conflit_economie_energie") is None
    assert luminosite(faux_client) >= 98
    derniere = (await fonction.runtime_data.historique.lister())
    assert any(e["cle"] == "energySaving" and e["origine"] == "panneau" for e in derniere)


async def test_conflit_pendant_la_pause_signale(hass: HomeAssistant, fonction, faux_client):
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await faux_client.notifier("picture", {"energySaving": "max"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    assert etat(hass).state == "pause"
    assert ir.async_get(hass).async_get_issue(DOMAIN, "conflit_economie_energie") is not None


async def test_ecran_desactive_sans_conflit(hass: HomeAssistant, fonction, faux_client):
    await faux_client.notifier("picture", {"energySaving": "screen_off"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    assert etat(hass).state == "active"


async def test_conflit_mode_eco(hass: HomeAssistant, fonction, faux_client):
    await faux_client.notifier("picture", {"pictureMode": "eco"}, caller=TELECOMMANDE)
    await regler_lux(hass, 300)
    assert etat(hass).state == "conflit_economie_energie"
    probleme = ir.async_get(hass).async_get_issue(DOMAIN, "conflit_economie_energie")
    assert not probleme.is_fixable and probleme.translation_key == "conflit_mode_eco"

    # Éco laissé de côté : plus de conflit, mode exclu.
    la = fonction.runtime_data.luminosite_adaptative
    la.reconfigurer({**la.options, "modes_exclus": [*la.options["modes_exclus"], "eco"]})
    await hass.async_block_till_done()
    assert etat(hass).state == "mode_exclu"
    assert ir.async_get(hass).async_get_issue(DOMAIN, "conflit_economie_energie") is None


async def test_reparation_desactive_l_economie_d_energie(hass: HomeAssistant, fonction,
                                                         faux_client, hass_client):
    assert await async_setup_component(hass, "repairs", {})
    await faux_client.notifier("picture", {"energySaving": "auto"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()

    client = await hass_client()
    reponse = await client.post("/api/repairs/issues/fix", json={
        "handler": DOMAIN, "issue_id": "conflit_economie_energie"})
    flux = await reponse.json()
    assert flux["step_id"] == "confirm"
    reponse = await client.post(f"/api/repairs/issues/fix/{flux['flow_id']}", json={})
    assert (await reponse.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    assert faux_client.valeurs["picture"]["energySaving"] == "off"
    assert ir.async_get(hass).async_get_issue(DOMAIN, "conflit_economie_energie") is None


async def test_reparations_retirees_avec_la_fonction(hass: HomeAssistant, fonction,
                                                     faux_client):
    await faux_client.notifier("picture", {"energySaving": "auto"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    fonction.runtime_data.luminosite_adaptative.activer(False)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "conflit_economie_energie") is None


# ---------------------------------------------------------------- options

def test_options_2_4_0_valides_sans_nouvelles_cles():
    anciennes = {k: v for k, v in OPTIONS_LUMINOSITE_DEFAUT.items()
                 if k != "emplacement_capteur"}
    options, erreurs = valider_options(anciennes, modes_proposes())
    assert erreurs == {}
    assert options == anciennes


def test_options_avancees_vides_retirees():
    options, erreurs = valider_options(
        {**OPTIONS_LUMINOSITE_DEFAUT, "lissage_montee_s": None, "gel_ecriture_s": 8.0,
         "hysteresis_descente": 95}, modes_proposes())
    assert erreurs == {"hysteresis_descente": "hors_bornes"}
    options, erreurs = valider_options(
        {**OPTIONS_LUMINOSITE_DEFAUT, "lissage_montee_s": None, "gel_ecriture_s": 8.0},
        modes_proposes())
    assert erreurs == {}
    assert "lissage_montee_s" not in options and options["gel_ecriture_s"] == 8
    _, erreurs = valider_options({**OPTIONS_LUMINOSITE_DEFAUT, "emplacement_capteur": "z"},
                                 modes_proposes())
    assert erreurs == {"emplacement_capteur": "emplacement_inconnu"}


async def test_page_options_avancees(hass: HomeAssistant, fonction, ws):
    reponse = await ws("luminosite_adaptative/configurer", options={
        "emplacement_capteur": "a", "lissage_descente_s": 30})
    assert reponse["result"] == {"recharge": False}
    assert fonction.options["lissage_descente_s"] == 30
    la = fonction.runtime_data.luminosite_adaptative
    assert la.details()["constantes"]["lissage_descente_s"] == 30
    reponse = await ws("luminosite_adaptative/configurer", options={"lissage_descente_s": None})
    assert "lissage_descente_s" not in fonction.options
    assert la.details()["constantes"]["lissage_descente_s"] == 15


@pytest.mark.parametrize("options_entree", [{}])
async def test_formulaire_section_avancee(hass: HomeAssistant, installe):
    flux = await hass.config_entries.options.async_init(installe.entry_id)
    saisie = {**{k: v for k, v in OPTIONS_LUMINOSITE_DEFAUT.items() if k != "ecart_minimal"},
              CONF_CAPTEUR_LUX: LUX, "emplacement_capteur": "b",
              "avance": {"ecart_minimal": 3, "confirmation_saut_s": 0, "rampe_debit": 6}}
    flux = await hass.config_entries.options.async_configure(flux["flow_id"], saisie)
    assert flux["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert installe.options["ecart_minimal"] == 3
    assert installe.options["confirmation_saut_s"] == 0
    assert installe.options["rampe_debit"] == 6
    assert installe.options["emplacement_capteur"] == "b"
    assert "avance" not in installe.options and "lissage_montee_s" not in installe.options


@pytest.mark.parametrize(("options_entree", "attendu"), [
    ({CONF_CAPTEUR_LUX: LUX, "ecart_minimal": 3}, None),
    ({CONF_CAPTEUR_LUX: LUX, "ecart_minimal": 5}, 5),
])
async def test_migration_de_l_ecart_minimal(hass: HomeAssistant, installe, attendu):
    """Entrées d'avant la 2.6.0 (version 1.1) : l'ancien défaut est retiré,
    un choix différent gardé."""
    assert installe.minor_version == 2
    assert installe.options.get("ecart_minimal") == attendu
    la = installe.runtime_data.luminosite_adaptative
    assert la.ecart_minimal == (2 if attendu is None else attendu)


async def test_page_options_de_rampe(hass: HomeAssistant, fonction, ws):
    reponse = await ws("luminosite_adaptative/configurer", options={
        "rampe_pas": 2, "rampe_debit": 8, "ecart_minimal": 4})
    assert reponse["result"] == {"recharge": False}
    la = fonction.runtime_data.luminosite_adaptative
    assert la.details()["parametres_rampe"] == {"pas": 2, "debit": 8}
    assert la.details()["ecart_minimal"] == 4
    reponse = await ws("luminosite_adaptative/configurer", options={"rampe_debit": 50})
    assert not reponse["success"]
    await ws("luminosite_adaptative/configurer", options={
        "rampe_pas": None, "rampe_debit": None, "ecart_minimal": None})
    assert la.details()["parametres_rampe"] == {"pas": 1, "debit": 4}
    assert "ecart_minimal" not in fonction.options


def test_bornes_du_panneau_alignees():
    """luminosite.js recopie les bornes : elles ne doivent pas diverger."""
    source = (Path(__file__).parent.parent / "frontend" / "src" / "luminosite.js").read_text()
    bloc = source.split("export const BORNES = {")[1].split("}")[0]
    bornes_js = {}
    for ligne in bloc.strip().splitlines():
        cle, valeurs = ligne.strip().rstrip(",").split(":", 1)
        bas, haut = json.loads(valeurs.strip())
        bornes_js[cle.strip()] = (bas, haut)
    assert bornes_js == BORNES


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_emplacements_traduits(langue):
    from custom_components.lg_webos_tv.const import EMPLACEMENTS
    traductions = json.loads((Path(__file__).parent.parent / "custom_components" / DOMAIN
                              / "translations" / f"{langue}.json").read_text())
    assert list(traductions["selector"]["emplacement_capteur"]["options"]) == EMPLACEMENTS


# ---------------------------------------------------------------- santé

def sante(fonction_entree) -> dict:
    return fonction_entree.runtime_data.luminosite_adaptative.sante()


def diagnostic_sante(fonction_entree, id_) -> dict:
    return next(d for d in sante(fonction_entree)["diagnostics"] if d["id"] == id_)


async def test_statistiques_des_transitions_et_reprises(hass: HomeAssistant, fonction,
                                                        faux_client):
    la = fonction.runtime_data.luminosite_adaptative
    assert sante(fonction)["chargees"]
    assert sante(fonction)["resume"]["transitions"] == 1  # 80 → 60 à l'installation
    await passer_le_temps(hass, 600)
    assert sante(fonction)["resume"]["actif_s"] >= 600
    # Deux appuis sur la télécommande : une seule reprise, la dernière
    # valeur compte. Cible 60 à 20 lx (ambiance intermédiaire).
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await faux_client.notifier("picture", {"backlight": "54"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    assert la._accumulateur.stats.reprises["intermediaire"] == [1, -6]
    la.mettre_en_pause(60)
    assert sante(fonction)["resume"]["reprises"] == 1
    assert sante(fonction)["resume"]["pauses_manuelles"] == 1


async def test_ecriture_non_confirmee_comptee(hass: HomeAssistant, fonction, faux_client):
    await demarrer_rampe(hass, fonction)
    faux_client.refuser.add(("picture", "backlight"))
    await passer_le_temps(hass, 2)
    assert sante(fonction)["resume"]["non_confirmees"] == 1


async def test_statistiques_relues_au_redemarrage(hass: HomeAssistant, fonction):
    await regler_lux(hass, 300)
    avant = sante(fonction)["resume"]
    assert avant["transitions"] == 2
    assert await hass.config_entries.async_reload(fonction.entry_id)
    await passer_le_temps(hass)
    apres = sante(fonction)["resume"]
    assert apres["transitions"] == 2
    assert apres["actif_s"] >= avant["actif_s"]


async def test_enregistrement_periodique(hass: HomeAssistant, fonction):
    await passer_le_temps(hass, 6 * 60)
    lignes = await fonction.runtime_data.statistiques.charger(LUX, "2000-01-01")
    assert [ligne["transitions"] for ligne in lignes] == [1]


async def test_nouveau_capteur_repart_de_zero(hass: HomeAssistant, fonction, ws):
    hass.states.async_set("sensor.bureau_lux", "20", {"device_class": "illuminance"})
    await ws("luminosite_adaptative/configurer", options={CONF_CAPTEUR_LUX: "sensor.bureau_lux"})
    await passer_le_temps(hass)
    assert sante(fonction)["resume"]["transitions"] == 0
    # Retour au premier capteur : ses statistiques, enregistrées avant le
    # changement, sont relues.
    await ws("luminosite_adaptative/configurer", options={CONF_CAPTEUR_LUX: LUX})
    await passer_le_temps(hass)
    assert sante(fonction)["resume"]["transitions"] == 1


async def test_commande_sante_et_flux(hass: HomeAssistant, fonction, faux_client, ws):
    reponse = await ws("luminosite_adaptative/sante")
    ids = [d["id"] for d in reponse["result"]["diagnostics"]]
    assert ids[:2] == ["conflit", "capteur_fige"] and "retroaction" in ids
    assert reponse["result"]["jours"][0]["transitions"] == 1

    abonnement = await ws("luminosite_adaptative/suivre")
    assert abonnement["success"]
    instantane = (await ws.client.receive_json())["event"]
    assert instantane["sante"]["resume"]["transitions"] == 1
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    evenements, _ = await commande(ws, "lg_webos_tv/reglages")
    [message] = [e for e in evenements if e["type"] == "sante"]
    assert message["sante"]["resume"]["reprises"] == 1


async def test_sante_reservee_aux_administrateurs(hass: HomeAssistant, fonction,
                                                  hass_ws_client,
                                                  hass_read_only_access_token):
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json({"id": 1, "type": "lg_webos_tv/luminosite_adaptative/sante"})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"


async def test_proposition_de_courbe_appliquee(hass: HomeAssistant, fonction, ws):
    """Douze heures entre 400 et 4 000 lx : la luminosité reste au maximum ;
    la proposition (90ᵉ centile) appliquée par la commande `configurer`
    fait disparaître le diagnostic."""
    la = fonction.runtime_data.luminosite_adaptative
    jour = la._accumulateur.stats.jour
    accumulateur = Accumulateur(StatsJour(jour))
    for i in range(721):
        lux = 400 * 10 ** (i / 720)
        accumulateur.echantillon(i * 60, jour, True, True, lux, lux)
    la._jours["2000-01-01"] = StatsJour("2000-01-01")  # hors fenêtre, ignoré
    la._accumulateur.stats.fusionner(accumulateur.stats)
    la._actualiser_sante()
    courbe = diagnostic_sante(fonction, "courbe")
    assert courbe["niveau"] == "avertissement" and courbe["proposition"] == {"lux_max": 3200}

    reponse = await ws("luminosite_adaptative/configurer", options=courbe["proposition"])
    assert reponse["success"]
    assert fonction.options["lux_max"] == 3200
    assert diagnostic_sante(fonction, "courbe")["niveau"] == "ok"


async def test_retroaction_mesuree_a_l_extinction(hass: HomeAssistant, fonction):
    """Le capteur perd 12 lx quand l'écran s'éteint : mesuré, et noté au
    journal pour vérifier à l'essai réel."""
    la = fonction.runtime_data.luminosite_adaptative
    tv = fonction.runtime_data.televiseur
    await tv._changer_etat("deconnecte")
    await regler_lux(hass, 8, secondes=40)
    await regler_lux(hass, 8.1, secondes=150)
    [evenement] = [e for e in la.journal if e["type"] == "retroaction"]
    assert (evenement["sens"], evenement["avant"]) == ("extinction", 20)
    # Seul rapport de la fenêtre [30 s ; 150 s] après l'extinction.
    assert evenement["apres"] == 8.1
    assert la._accumulateur.stats.tv == [["extinction", 20, 8.1]]
    assert diagnostic_sante(fonction, "retroaction")["valeurs"]["evenements"] == 1


async def test_pieces_et_diagnostics_ha(hass: HomeAssistant, fonction):
    """Pièces lues dans les registres ; les diagnostics téléchargeables n'en
    gardent que la différence, sans nom ni identifiant du capteur."""
    zones = ar.async_get(hass)
    bureau, salon = zones.async_create("Bureau"), zones.async_create("Salon")
    # L'identifiant n'est libre au registre que sans état.
    etat_lux = hass.states.get(LUX)
    hass.states.async_remove(LUX)
    er.async_get(hass).async_get_or_create(
        "sensor", "essai", "lux-salon", suggested_object_id="salon_lux")
    hass.states.async_set(LUX, etat_lux.state, etat_lux.attributes)
    er.async_get(hass).async_update_entity(LUX, area_id=bureau.id)
    appareils = dr.async_get(hass)
    tv = appareils.async_get_device_by_identifier((DOMAIN, fonction.entry_id),
                                                  fonction.entry_id)
    appareils.async_update_device(tv.id, area_id=salon.id)
    fonction.runtime_data.luminosite_adaptative._actualiser_sante()
    pieces = diagnostic_sante(fonction, "pieces_differentes")
    assert pieces["niveau"] == "info"
    assert pieces["valeurs"] == {"capteur": "Bureau", "televiseur": "Salon"}

    diag = await async_get_config_entry_diagnostics(hass, fonction)
    bloc = diag["luminosite_adaptative"]
    assert bloc["etat"] == "active" and CONF_CAPTEUR_LUX not in bloc["options"]
    assert bloc["statistiques"]["transitions"] == 1
    [pieces] = [d for d in bloc["diagnostics"] if d["id"] == "pieces_differentes"]
    assert pieces["valeurs"] == {"differentes": True}
    texte = json.dumps(diag)
    assert "salon_lux" not in texte and "Bureau" not in texte and "Salon" not in texte


@pytest.mark.parametrize("options_entree", [{}])
async def test_diagnostics_ha_sans_fonction(hass: HomeAssistant, installe):
    diag = await async_get_config_entry_diagnostics(hass, installe)
    assert diag["luminosite_adaptative"] is None


# ------------------------------------------------------- mise en route (lot 4)
async def ouvrir_mise_en_route(ws) -> int:
    """Abonnement de l'assistant ; renvoie son identifiant."""
    reponse = await ws("luminosite_adaptative/mise_en_route")
    assert reponse["success"]
    return reponse["id"]


async def fermer_mise_en_route(hass, ws, abonnement: int) -> None:
    await ws.client.send_json({"id": next(ws.compteur), "type": "unsubscribe_events",
                               "subscription": abonnement})
    assert (await ws.client.receive_json())["success"]
    await hass.async_block_till_done()


async def test_mise_en_route_ecrit_sans_pause_ni_reprise_comptee(hass: HomeAssistant, fonction,
                                                                 faux_client, ws):
    la = fonction.runtime_data.luminosite_adaptative
    abonnement = await ouvrir_mise_en_route(ws)
    assert la.etat == "mise_en_route"
    assert etat(hass).state == "mise_en_route"
    # Curseur de l'assistant (origine panneau, historisé) puis télécommande.
    reponse = await ws("ecrire", entree_id=ID_OLED, valeur=75)
    assert reponse["success"]
    historique = await fonction.runtime_data.historique.lister()
    assert (historique[0]["origine"], historique[0]["nouvelle"]) == ("panneau", 75)
    await faux_client.notifier("picture", {"backlight": "78"}, caller=TELECOMMANDE)
    # Pas plus d'une minute en tout : au-delà, le client websocket de test
    # perd sa connexion, ce qui fermerait l'assistant.
    await passer_le_temps(hass, 10)
    # Ni pause, ni écriture de la fonction, ni correction comptée.
    assert la.fin_pause is None and luminosite(faux_client) == 78
    assert sante(fonction)["resume"]["reprises"] == 0
    actif = sante(fonction)["resume"]["actif_s"]
    await passer_le_temps(hass, 30)
    assert sante(fonction)["resume"]["actif_s"] == pytest.approx(actif, abs=1)
    assert [e["type"] for e in la.journal][-1] == "mise_en_route"

    # Assistant fermé sans ancrage : la fonction reprend la courbe.
    await fermer_mise_en_route(hass, ws, abonnement)
    await passer_le_temps(hass, RAMPE_S)
    assert la.etat == "active" and luminosite(faux_client) == 60
    assert la.fin_pause is None


async def test_mise_en_route_interrompt_la_rampe(hass: HomeAssistant, fonction, ws):
    la = await demarrer_rampe(hass, fonction)
    await ouvrir_mise_en_route(ws)
    await passer_le_temps(hass, 2)
    assert la.rampe is None
    assert applications(fonction)[-1]["fin"] == "mise_en_route"


async def test_ancrer_cale_la_courbe(hass: HomeAssistant, fonction, faux_client, ws):
    la = fonction.runtime_data.luminosite_adaptative
    await ouvrir_mise_en_route(ws)
    await ws("ecrire", entree_id=ID_OLED, valeur=70)
    reponse = await ws("luminosite_adaptative/ancrer")
    resultat = reponse["result"]
    assert resultat["compte_rendu"]["points"] == 1 and resultat["compte_rendu"]["cible"] == 70
    # Valeur relue sur le téléviseur, au lux filtré (20 lx).
    [ancrage] = fonction.options["ancrages"]
    assert (ancrage["lux"], ancrage["luminosite"]) == (20, 70)
    assert fonction.options["lux_min"] < 5 and fonction.options["luminosite_min"] == 40
    assert la.options == {**OPTIONS_LUMINOSITE_DEFAUT, **fonction.options}
    assert la.cible == 70
    assert la.journal[-1]["type"] == "ancrage"

    # Deuxième point, dans le noir : deux points, pente calée.
    # Moins de deux minutes : le client websocket de test ne survit pas à un
    # saut d'horloge.
    await regler_lux(hass, 1, secondes=60)
    await ws("ecrire", entree_id=ID_OLED, valeur=45)
    reponse = await ws("luminosite_adaptative/ancrer")
    assert reponse["result"]["compte_rendu"]["points"] == 2
    assert len(fonction.options["ancrages"]) == 2
    assert la.cible == 45

    # Courbe retouchée depuis la page : ancrages oubliés ; autre réglage :
    # conservés.
    await ws("luminosite_adaptative/configurer", options={"pause": 60})
    assert len(fonction.options["ancrages"]) == 2
    await ws("luminosite_adaptative/configurer", options={"luminosite_max": 90})
    assert "ancrages" not in fonction.options


async def test_ancrer_refuse(hass: HomeAssistant, fonction, faux_client, ws):
    await faux_client.notifier("picture", {"pictureMode": "expert1"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    reponse = await ws("luminosite_adaptative/ancrer")
    assert reponse["error"]["code"] == "mode_exclu"
    await faux_client.notifier("picture", {"pictureMode": "vivid"}, caller=TELECOMMANDE)
    hass.states.async_set(LUX, "unavailable")
    await hass.async_block_till_done()
    reponse = await ws("luminosite_adaptative/ancrer")
    assert reponse["error"]["code"] == "indisponible"
    assert "ancrages" not in fonction.options


async def test_mise_en_route_et_ancrage_reserves_aux_administrateurs(
        hass: HomeAssistant, fonction, hass_ws_client, hass_read_only_access_token):
    client = await hass_ws_client(hass, hass_read_only_access_token)
    for i, nom in enumerate(("ancrer", "mise_en_route"), start=1):
        await client.send_json({"id": i, "type": f"lg_webos_tv/luminosite_adaptative/{nom}"})
        assert (await client.receive_json())["error"]["code"] == "unauthorized"
    assert fonction.runtime_data.luminosite_adaptative.etat == "active"


async def test_configuration_enrichie_et_triee(hass: HomeAssistant, fonction, ws):
    zones = ar.async_get(hass)
    salon = zones.async_create("Salon")
    appareils = dr.async_get(hass)
    tv = appareils.async_get_device_by_identifier((DOMAIN, fonction.entry_id),
                                                  fonction.entry_id)
    appareils.async_update_device(tv.id, area_id=salon.id)
    attributs = {"device_class": "illuminance", "unit_of_measurement": "lx"}
    # Capteur de la pièce du téléviseur, enregistré par ZHA.
    er.async_get(hass).async_get_or_create(
        "sensor", "zha", "lux-canape", suggested_object_id="canape_lux")
    er.async_get(hass).async_update_entity("sensor.canape_lux", area_id=salon.id)
    hass.states.async_set("sensor.canape_lux", "12", attributs)
    hass.states.async_set("sensor.ancien_lux", "3", attributs,
                          timestamp=dt_util.utcnow().timestamp() - 2 * 3600)
    hass.states.async_set("sensor.recent_lux", "8", attributs)
    reponse = await ws("luminosite_adaptative/configuration")
    resultat = reponse["result"]
    assert resultat["piece_televiseur"] == "Salon"
    capteurs = resultat["capteurs"]
    assert [c["entity_id"] for c in capteurs] == [
        "sensor.canape_lux", "sensor.recent_lux", LUX, "sensor.ancien_lux"]
    canape = capteurs[0]
    assert canape["piece"] == "Salon" and canape["meme_piece"]
    assert canape["plateforme"] == "zha" and canape["profil"] == "sur_variation"
    assert canape["age_s"] == 0 and capteurs[-1]["age_s"] == 2 * 3600


async def test_point_intermediaire_depuis_la_page(hass: HomeAssistant, fonction, faux_client,
                                                  ws):
    reponse = await ws("luminosite_adaptative/configurer",
                       options={"point_intermediaire": [400, 90]})
    assert reponse["error"]["code"] == "invalide"
    assert "point_intermediaire" in reponse["error"]["message"]
    # 20 lx sur le premier segment (5 → 40 lx, 40 → 80) : 40 + 40 × 2/3 = 66,7
    reponse = await ws("luminosite_adaptative/configurer",
                       options={"point_intermediaire": [40, 80]})
    assert reponse["result"] == {"recharge": False}
    await passer_le_temps(hass, RAMPE_S)
    assert fonction.options["point_intermediaire"] == [40, 80]
    assert luminosite(faux_client) == 67
    await ws("luminosite_adaptative/configurer", options={"point_intermediaire": None})
    await passer_le_temps(hass, RAMPE_S)
    assert "point_intermediaire" not in fonction.options
    assert luminosite(faux_client) == 60


def test_options_2_7_0_memes_cibles():
    options_2_7_0 = {**OPTIONS_LUMINOSITE_DEFAUT, "lux_min": 3, "lux_max": 800,
                     "luminosite_min": 35, "luminosite_max": 95}
    valides, erreurs = valider_options(options_2_7_0, modes_proposes())
    assert erreurs == {} and valides == options_2_7_0


ANCRAGES = [{"lux": 20, "luminosite": 70, "horodatage": "2026-10-25T20:00:00+00:00"}]


async def formulaire(hass, entree, **valeurs):
    flux = await hass.config_entries.options.async_init(entree.entry_id)
    saisie = {**{k: v for k, v in OPTIONS_LUMINOSITE_DEFAUT.items() if k != "ecart_minimal"},
              CONF_CAPTEUR_LUX: LUX, "avance": {}, **valeurs}
    return await hass.config_entries.options.async_configure(flux["flow_id"], saisie)


@pytest.mark.parametrize("options_entree", [{CONF_CAPTEUR_LUX: LUX, "ancrages": ANCRAGES}])
async def test_formulaire_point_intermediaire(hass: HomeAssistant, installe):
    flux = await formulaire(hass, installe, lux_intermediaire=40)
    assert flux["errors"] == {"luminosite_intermediaire": "point_intermediaire_incomplet"}
    flux = await formulaire(hass, installe, lux_intermediaire=400, luminosite_intermediaire=90)
    assert flux["errors"] == {"lux_intermediaire": "point_intermediaire_hors_courbe"}

    # Autre réglage que la courbe : les ancrages restent.
    flux = await formulaire(hass, installe, pause=60)
    assert flux["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert installe.options["ancrages"] == ANCRAGES
    assert "point_intermediaire" not in installe.options

    flux = await formulaire(hass, installe, lux_intermediaire=40.0, luminosite_intermediaire=80.0)
    assert flux["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert installe.options["point_intermediaire"] == [40.0, 80]
    assert "ancrages" not in installe.options
    assert installe.runtime_data.luminosite_adaptative.options["point_intermediaire"] == [40, 80]

    # Réaffiché dans ses deux champs, puis retiré en les vidant.
    flux = await hass.config_entries.options.async_init(installe.entry_id)
    suggestions = {str(cle): (cle.description or {}).get("suggested_value")
                   for cle in flux["data_schema"].schema}
    assert (suggestions["lux_intermediaire"], suggestions["luminosite_intermediaire"]) == (40, 80)
    flux = await formulaire(hass, installe)
    await hass.async_block_till_done()
    assert "point_intermediaire" not in installe.options
