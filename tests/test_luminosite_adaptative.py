"""Luminosité adaptative, exécutée dans Home Assistant contre l'intégration
et un téléviseur simulé."""

import copy
import json
from datetime import timedelta
from pathlib import Path

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.lg_webos_tv.const import (CONF_CAPTEUR_LUX, DOMAIN,
                                                 OPTIONS_LUMINOSITE_DEFAUT)
from custom_components.lg_webos_tv.luminosite_adaptative import (
    BORNES, ID_MODE, ID_OLED, modes_proposes, valider_options)
from custom_components.lg_webos_tv.presets import capturer_snapshot

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


async def _pas_a_pas(hass, secondes):
    while secondes > 0:
        await _pas(hass, min(secondes, 1.0))
        secondes -= 1.0


async def passer_le_temps(hass, secondes=2.0):
    """Par pas d'une seconde, pour que chaque évaluation programmée par la
    précédente ait lieu à son heure ; au-delà de deux minutes, une minute pas
    à pas, un saut, puis une minute pas à pas."""
    if secondes > 120:
        await _pas_a_pas(hass, 60)
        await _pas(hass, secondes - 120)
        secondes = 60
    await _pas_a_pas(hass, secondes)


# Assez pour un saut confirmé (8 s), le filtre (15 s en descente) et les
# écritures espacées du gel (5 s).
STABILISATION_S = 120


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
    await hass.async_block_till_done(wait_background_tasks=True)
    assert luminosite(faux_client) == 100

    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    assert etat(hass).state == "pause"
    await hass.services.async_call("button", "press", {
        "entity_id": entite(hass, "button", "luminosite_adaptative_reprendre")},
        blocking=True)
    # Gel de 5 s après l'écriture de l'allumage.
    await passer_le_temps(hass, 6)
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
        "cause_pause": None, "conflit": None}

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
    await hass.async_block_till_done(wait_background_tasks=True)
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
        "cible": 60, "ancienne": 80.0}

    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    assert la.cause_pause["origine"] == "manuel"
    assert la.journal[-1]["type"] == "pause" and la.journal[-1]["origine"] == "manuel"

    la.reprendre()
    await hass.async_block_till_done(wait_background_tasks=True)
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
    await passer_le_temps(hass)
    # ln(20/5) / ln(300/5) = 0,339 → 40 + 0,339 × 40 = 53,5
    assert luminosite(faux_client) == 54

    hass.states.async_set("sensor.bureau_lux", "300", {"device_class": "illuminance"})
    la.reconfigurer({**la.options, CONF_CAPTEUR_LUX: "sensor.bureau_lux"})
    await passer_le_temps(hass)
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
    avant = len(la._ecouteurs), len(la._ecouteurs_journal)
    await commande(ws, "unsubscribe_events", subscription=abonnement["id"])
    assert (len(la._ecouteurs), len(la._ecouteurs_journal)) == (avant[0] - 1, avant[1] - 1)


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


async def test_transition_en_ecritures_espacees_du_gel(hass: HomeAssistant, fonction,
                                                       faux_client):
    nombre = len(applications(fonction))
    await regler_lux(hass, 300)
    nouvelles = applications(fonction)[nombre:]
    instants = [dt_util.parse_datetime(e["horodatage"]) for e in nouvelles]
    assert 2 <= len(nouvelles) <= 6
    assert all((b - a).total_seconds() >= 5 for a, b in zip(instants, instants[1:]))
    # Saut de plus d'un facteur 4 : confirmé au bout de 8 s.
    assert luminosite(faux_client) >= 98


async def test_saut_isole_ecarte(hass: HomeAssistant, fonction, faux_client):
    await regler_lux(hass, 2000, secondes=3)  # lampe torche sur le capteur
    await regler_lux(hass, 20, secondes=30)
    assert luminosite(faux_client) == 60
    assert "saut_ecarte" in types_journal(fonction)


async def test_emplacement_d_allonge_le_gel(hass: HomeAssistant, fonction, faux_client):
    la = fonction.runtime_data.luminosite_adaptative
    la.reconfigurer({**la.options, "emplacement_capteur": "d"})
    assert la.details()["constantes"]["gel_s"] == 20
    nombre = len(applications(fonction))
    await regler_lux(hass, 300, secondes=200)
    instants = [dt_util.parse_datetime(e["horodatage"])
                for e in applications(fonction)[nombre:]]
    assert len(instants) >= 2
    assert all((b - a).total_seconds() >= 20 for a, b in zip(instants, instants[1:]))


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
              "avance": {"ecart_minimal": 2, "confirmation_saut_s": 0}}
    flux = await hass.config_entries.options.async_configure(flux["flow_id"], saisie)
    assert flux["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert installe.options["ecart_minimal"] == 2
    assert installe.options["confirmation_saut_s"] == 0
    assert installe.options["emplacement_capteur"] == "b"
    assert "avance" not in installe.options and "lissage_montee_s" not in installe.options


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
