"""Luminosité adaptative, lot 7a : Soirée (R15), contre l'intégration et un
téléviseur simulé. Mêmes outils que test_luminosite_adaptative.py (horloge
simulée, ticks de 0,5 s) ; l'horloge part à 20:50, heure locale, la Soirée
commence à 21:00 par défaut."""

from datetime import datetime

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.lg_webos_tv.const import CONF_CAPTEUR_LUX
from custom_components.lg_webos_tv.diagnostics import async_get_config_entry_diagnostics
from custom_components.lg_webos_tv.luminosite_adaptative import AncrageImpossible

from . import test_luminosite_adaptative as base
from .conftest import entite
from .test_luminosite_adaptative import (LUX, RAMPE_S, TELECOMMANDE, etat, journal,
                                         luminosite, passer_le_temps, regler_lux)

horloge = base.horloge
fonction = base.fonction

SOIREE = {CONF_CAPTEUR_LUX: LUX, "soiree": True, "soiree_debut": "21:00",
          "soiree_fin": "06:00", "soiree_reduction": 20, "soiree_lumiere_bleue": True}
# Lux 20 : courbe à 60 (fixture `fonction`), 48 pendant la Soirée.
NORMALE, BAISSEE = 60, 48


@pytest.fixture(autouse=True)
def depart(hass, horloge):
    """Avant l'installation : 20:50, heure locale."""
    horloge.move_to(datetime(2026, 10, 20, 20, 50, tzinfo=dt_util.get_default_time_zone()))


@pytest.fixture
def options_entree():
    return dict(SOIREE)


async def preparer(hass, faux_client):
    """Comme la fixture `fonction` : mode non calibré, lux 20 (luminosité 60)."""
    await faux_client.notifier("picture", {"pictureMode": "vivid"}, caller=TELECOMMANDE)
    await regler_lux(hass, 20)
    assert luminosite(faux_client) == NORMALE


def la(entree):
    return entree.runtime_data.luminosite_adaptative


def soiree_entite(hass):
    return hass.states.get(entite(hass, "binary_sensor", "luminosite_adaptative_soiree"))


def bouton_terminer(hass):
    return entite(hass, "button", "luminosite_adaptative_terminer_soiree")


def lumiere_bleue(faux_client):
    return faux_client.valeurs["picture"]["eyeComfortMode"]


async def aller_a(hass, jour: int, heure: int, minute: int = 0, seconde: int = 5):
    """Avance l'horloge jusqu'à cette heure locale (puis quelques secondes
    pour la rampe)."""
    cible = datetime(2026, 10, jour, heure, minute, seconde,
                     tzinfo=dt_util.get_default_time_zone())
    await passer_le_temps(hass, (cible - dt_util.now()).total_seconds())


async def debut_de_soiree(hass):
    await aller_a(hass, 20, 21)
    await passer_le_temps(hass, RAMPE_S)


async def ecritures_lumiere_bleue(entree) -> list[dict]:
    return [e for e in await entree.runtime_data.historique.lister(100)
            if e["cle"] == "eyeComfortMode"]


# ------------------------------------------------------------- début, fin

async def test_debut_a_l_heure_baisse_en_rampe(hass: HomeAssistant, fonction, faux_client):
    assert soiree_entite(hass).state == "off"
    assert hass.states.get(bouton_terminer(hass)).state == "unavailable"
    await debut_de_soiree(hass)
    assert soiree_entite(hass).state == "on"
    assert soiree_entite(hass).attributes["reduction"] == 20
    assert etat(hass).state == "active" and etat(hass).attributes["cible"] == BAISSEE
    assert luminosite(faux_client) == BAISSEE
    # En rampe : plusieurs pas, une seule entrée d'historique.
    [application] = journal(fonction, "application")[-1:]
    assert application["ancienne"] == NORMALE and application["pas"] > 1
    assert lumiere_bleue(faux_client) == "on"
    [debut] = journal(fonction, "soiree_debut")
    assert debut["reduction"] == 20
    assert [e["action"] for e in journal(fonction, "lumiere_bleue")] == ["posee"]
    [ecriture] = await ecritures_lumiere_bleue(fonction)
    assert (ecriture["origine"], ecriture["ancienne"], ecriture["nouvelle"]) == (
        "luminosite_adaptative", "off", "on")
    assert journal(fonction, "pause") == []


async def test_fin_a_l_heure_restaure(hass: HomeAssistant, fonction, faux_client):
    await debut_de_soiree(hass)
    await aller_a(hass, 21, 6)
    await passer_le_temps(hass, RAMPE_S)
    assert soiree_entite(hass).state == "off"
    assert luminosite(faux_client) == NORMALE
    assert lumiere_bleue(faux_client) == "off"
    [fin] = journal(fonction, "soiree_fin")
    assert fin["raison"] == "heure"
    assert [e["action"] for e in journal(fonction, "lumiere_bleue")] == ["posee", "restauree"]


async def test_lumiere_bleue_deja_active_n_est_pas_touchee(hass: HomeAssistant, fonction,
                                                          faux_client):
    await faux_client.notifier("picture", {"eyeComfortMode": "on"}, caller=TELECOMMANDE)
    await debut_de_soiree(hass)
    await aller_a(hass, 21, 6)
    assert lumiere_bleue(faux_client) == "on"
    assert await ecritures_lumiere_bleue(fonction) == []


@pytest.mark.parametrize("options_entree", [{**SOIREE, "soiree_lumiere_bleue": False}])
async def test_sans_lumiere_bleue(hass: HomeAssistant, faux_client, installe):
    await preparer(hass, faux_client)
    await debut_de_soiree(hass)
    assert soiree_entite(hass).state == "on"
    assert luminosite(faux_client) == BAISSEE
    assert lumiere_bleue(faux_client) == "off"


# --------------------------------------------------- extinction, Terminer

async def test_extinction_puis_rallumage_dans_la_plage(hass: HomeAssistant, fonction,
                                                       faux_client):
    tv = fonction.runtime_data.televiseur
    await debut_de_soiree(hass)
    await tv._changer_etat("deconnecte")  # noqa: SLF001
    await passer_le_temps(hass, 1800)
    await tv._changer_etat("connecte")  # noqa: SLF001
    await passer_le_temps(hass, RAMPE_S)
    assert soiree_entite(hass).state == "on"
    assert luminosite(faux_client) == BAISSEE
    assert journal(fonction, "soiree_fin") == []


async def test_rallumage_apres_la_fin_restaure_la_lumiere_bleue(hass: HomeAssistant, fonction,
                                                               faux_client):
    tv = fonction.runtime_data.televiseur
    await debut_de_soiree(hass)
    await tv._changer_etat("deconnecte")  # noqa: SLF001
    # Le téléviseur garde le réglage éteint ; la fin passe sans lui.
    await aller_a(hass, 21, 8)
    assert lumiere_bleue(faux_client) == "on"
    await tv._changer_etat("connecte")  # noqa: SLF001
    await passer_le_temps(hass, RAMPE_S)
    assert lumiere_bleue(faux_client) == "off"
    assert luminosite(faux_client) == NORMALE


async def test_terminer_la_soiree(hass: HomeAssistant, fonction, faux_client):
    await debut_de_soiree(hass)
    # « Reprendre » n'y touche pas.
    await hass.services.async_call("button", "press", {
        "entity_id": entite(hass, "button", "luminosite_adaptative_reprendre")}, blocking=True)
    await passer_le_temps(hass, RAMPE_S)
    assert soiree_entite(hass).state == "on"
    await hass.services.async_call("button", "press", {"entity_id": bouton_terminer(hass)},
                                   blocking=True)
    await passer_le_temps(hass, RAMPE_S)
    assert soiree_entite(hass).state == "off"
    assert soiree_entite(hass).attributes["terminee_jusqua"].startswith("2026-10-21T06:00")
    assert hass.states.get(bouton_terminer(hass)).state == "unavailable"
    assert luminosite(faux_client) == NORMALE
    assert lumiere_bleue(faux_client) == "off"
    [fin] = journal(fonction, "soiree_fin")
    assert (fin["raison"], fin["origine"]) == ("terminee", "home_assistant")
    # Terminée jusqu'à 6 h, même téléviseur rallumé.
    tv = fonction.runtime_data.televiseur
    await tv._changer_etat("deconnecte")  # noqa: SLF001
    await tv._changer_etat("connecte")  # noqa: SLF001
    await passer_le_temps(hass, RAMPE_S)
    assert soiree_entite(hass).state == "off"
    # Le lendemain soir, elle recommence.
    await aller_a(hass, 21, 21)
    assert soiree_entite(hass).state == "on"


async def test_terminee_conservee_au_rechargement(hass: HomeAssistant, fonction, faux_client):
    await debut_de_soiree(hass)
    la(fonction).terminer_soiree("panneau")
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(fonction.entry_id)
    await hass.async_block_till_done()
    await passer_le_temps(hass, RAMPE_S)
    assert not la(fonction).soiree_active
    assert soiree_entite(hass).state == "off"


async def test_lumiere_bleue_restauree_apres_rechargement(hass: HomeAssistant, fonction,
                                                         faux_client):
    await debut_de_soiree(hass)
    assert lumiere_bleue(faux_client) == "on"
    assert await hass.config_entries.async_reload(fonction.entry_id)
    await hass.async_block_till_done()
    # Rechargée en pleine Soirée : rien n'est réécrit.
    assert [e["action"] for e in journal(fonction, "lumiere_bleue")] == []
    await aller_a(hass, 21, 6)
    assert lumiere_bleue(faux_client) == "off"


# ----------------------------------------------------- pause, reprise en main

async def test_pause_respectee_baisse_a_la_reprise(hass: HomeAssistant, fonction, faux_client):
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    await debut_de_soiree(hass)
    assert etat(hass).state == "pause"
    assert luminosite(faux_client) == 55
    # La lumière bleue suit son propre pilote.
    assert lumiere_bleue(faux_client) == "on"
    la(fonction).reprendre()
    await passer_le_temps(hass, RAMPE_S)
    assert luminosite(faux_client) == BAISSEE
    assert soiree_entite(hass).state == "on"


async def test_reprise_en_main_de_la_lumiere_bleue_seule(hass: HomeAssistant, fonction,
                                                        faux_client):
    await debut_de_soiree(hass)
    await faux_client.notifier("picture", {"eyeComfortMode": "off"}, caller=TELECOMMANDE)
    await passer_le_temps(hass, RAMPE_S)
    assert lumiere_bleue(faux_client) == "off"
    assert etat(hass).state == "active"
    assert soiree_entite(hass).attributes["lumiere_bleue_reprise_en_main"] is True
    [*_, reprise] = journal(fonction, "lumiere_bleue")
    assert (reprise["action"], reprise["origine"]) == ("reprise_en_main", "manuel")
    # Ni réactivée par un changement de mode, ni restaurée à la fin.
    await faux_client.notifier("picture", {"pictureMode": "normal"}, caller=TELECOMMANDE)
    await faux_client.notifier("picture", {"eyeComfortMode": "on"}, caller=TELECOMMANDE)
    await aller_a(hass, 21, 6)
    assert lumiere_bleue(faux_client) == "on"
    assert len(await ecritures_lumiere_bleue(fonction)) == 1


async def test_reprise_en_main_de_la_lumiere_bleue_depuis_home_assistant(
        hass: HomeAssistant, fonction, faux_client):
    """Écriture d'une entité : le téléviseur l'attribue à notre client, seul
    l'historique dit son origine."""
    await debut_de_soiree(hass)
    resultat = await fonction.runtime_data.ecritures.demander(
        "image.parametres-avances.reduire-lumiere-bleue", "off", "home_assistant")
    assert resultat["ok"]
    await hass.async_block_till_done()
    assert la(fonction).resume_soiree()["lumiere_bleue"]["reprise"] is True
    assert lumiere_bleue(faux_client) == "off"
    assert etat(hass).state == "active"


async def test_mode_laisse_de_cote(hass: HomeAssistant, fonction, faux_client):
    await debut_de_soiree(hass)
    await faux_client.notifier("picture", {"pictureMode": "expert1"}, caller=TELECOMMANDE)
    await passer_le_temps(hass, 2)
    assert lumiere_bleue(faux_client) == "off"
    [*_, restauree] = journal(fonction, "lumiere_bleue")
    assert (restauree["action"], restauree["raison"]) == ("restauree", "mode_exclu")
    await faux_client.notifier("picture", {"pictureMode": "vivid"}, caller=TELECOMMANDE)
    await passer_le_temps(hass, 2)
    assert lumiere_bleue(faux_client) == "on"


async def test_lumiere_bleue_refusee(hass: HomeAssistant, fonction, faux_client):
    faux_client.refuser.add(("picture", "eyeComfortMode"))
    await debut_de_soiree(hass)
    assert lumiere_bleue(faux_client) == "off"
    [refus] = journal(fonction, "lumiere_bleue")
    assert refus["action"] == "refusee"
    # Baisse appliquée malgré tout.
    assert luminosite(faux_client) == BAISSEE
    diagnostic = next(d for d in la(fonction).sante()["diagnostics"] if d["id"] == "soiree")
    assert (diagnostic["niveau"], diagnostic["valeurs"]["cause"]) == ("avertissement",
                                                                      "lumiere_bleue")


async def test_fonction_desactivee_restaure_la_lumiere_bleue(hass: HomeAssistant, fonction,
                                                            faux_client):
    await debut_de_soiree(hass)
    la(fonction).activer(False)
    await passer_le_temps(hass, 2)
    assert lumiere_bleue(faux_client) == "off"


# --------------------------------------------- corrections, point d'ancrage

async def test_correction_ecartee_et_ancrage_refuse(hass: HomeAssistant, fonction, faux_client):
    await debut_de_soiree(hass)
    await faux_client.notifier("picture", {"backlight": "50"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    [ecartee] = journal(fonction, "correction_ecartee")
    assert ecartee["raison"] == "soiree"
    assert la(fonction).details()["correction_en_cours"] is None
    with pytest.raises(AncrageImpossible, match="soiree"):
        la(fonction).ancrer()


async def test_correction_en_observation_abandonnee_au_debut(hass: HomeAssistant, fonction,
                                                            faux_client):
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    assert la(fonction).details()["correction_en_cours"] is not None
    await debut_de_soiree(hass)
    assert la(fonction).details()["correction_en_cours"] is None
    assert journal(fonction, "correction_ecartee")[-1]["raison"] == "soiree"


# ----------------------------------------------------------------- sources

@pytest.mark.parametrize("options_entree", [{**SOIREE, "soiree_entite": "binary_sensor.soir"}])
async def test_source_interrupteur(hass: HomeAssistant, faux_client, installe):
    hass.states.async_set("binary_sensor.soir", "off")
    await preparer(hass, faux_client)
    await aller_a(hass, 20, 21)
    assert soiree_entite(hass).state == "off"
    hass.states.async_set("binary_sensor.soir", "on")
    await passer_le_temps(hass, RAMPE_S)
    assert soiree_entite(hass).state == "on"
    assert luminosite(faux_client) == BAISSEE
    hass.states.async_set("binary_sensor.soir", "off")
    await passer_le_temps(hass, RAMPE_S)
    assert soiree_entite(hass).state == "off"
    assert journal(installe, "soiree_fin")[-1]["raison"] == "entite"
    hass.states.async_set("binary_sensor.soir", "unavailable")
    await passer_le_temps(hass, 2)
    diagnostic = next(d for d in la(installe).sante()["diagnostics"] if d["id"] == "soiree")
    assert (diagnostic["niveau"], diagnostic["valeurs"]["cause"]) == ("avertissement", "source")


@pytest.mark.parametrize("options_entree",
                         [{**SOIREE, "soiree_entite": "input_datetime.coucher"}])
async def test_source_input_datetime(hass: HomeAssistant, faux_client, installe):
    hass.states.async_set("input_datetime.coucher", "21:30:00", {
        "has_date": False, "has_time": True, "hour": 21, "minute": 30, "second": 0})
    await preparer(hass, faux_client)
    await aller_a(hass, 20, 21, 10)
    assert soiree_entite(hass).state == "off"
    await aller_a(hass, 20, 21, 30)
    assert soiree_entite(hass).state == "on"


# -------------------------------------------- options, websocket, diagnostics

@pytest.mark.parametrize("options_entree", [{CONF_CAPTEUR_LUX: LUX}])
async def test_options_2_10_0_sans_soiree(hass: HomeAssistant, faux_client, installe):
    """Options d'avant le lot 7 : Soirée désactivée, rien ne change à 21 h."""
    await preparer(hass, faux_client)
    await aller_a(hass, 20, 21, 1)
    assert soiree_entite(hass).state == "off"
    assert luminosite(faux_client) == NORMALE
    assert la(installe).resume_soiree()["configuree"] is False
    assert not any(d["id"] == "soiree" for d in la(installe).sante()["diagnostics"])


async def test_websocket_configurer_et_terminer(hass: HomeAssistant, fonction, faux_client, ws):
    hass.states.async_set("schedule.soir", "off")
    hass.states.async_set("input_datetime.date_seule", "2026-10-20", {"has_time": False})
    configuration = (await ws("luminosite_adaptative/configuration"))["result"]
    assert [s["entity_id"] for s in configuration["sources_soiree"]] == ["schedule.soir"]
    assert (await ws("luminosite_adaptative/terminer_soiree"))["error"]["code"] == "hors_soiree"
    reponse = await ws("luminosite_adaptative/configurer",
                       options={"soiree_debut": "20:51", "soiree_reduction": 10})
    assert reponse["success"] and reponse["result"] == {"recharge": False}
    await passer_le_temps(hass, RAMPE_S)
    assert soiree_entite(hass).state == "on"
    assert luminosite(faux_client) == 54
    reponse = await ws("luminosite_adaptative/terminer_soiree")
    assert reponse["success"] and reponse["result"]["soiree"]["active"] is False
    reponse = await ws("luminosite_adaptative/configurer",
                       options={"soiree_debut": "21:00", "soiree_fin": "21:00"})
    assert reponse["error"]["code"] == "invalide"
    reponse = await ws("luminosite_adaptative/configurer",
                       options={"soiree_entite": "sensor.inconnu"})
    assert reponse["error"]["code"] == "invalide"


async def test_terminer_reserve_aux_administrateurs(hass: HomeAssistant, fonction, hass_ws_client,
                                                   hass_read_only_access_token):
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json({"id": 1, "type": "lg_webos_tv/luminosite_adaptative/terminer_soiree"})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("options_entree", [{**SOIREE, "soiree_entite": "schedule.coucher_x"}])
async def test_diagnostics_sans_entite_de_soiree(hass: HomeAssistant, installe):
    diagnostics = await async_get_config_entry_diagnostics(hass, installe)
    texte = str(diagnostics)
    assert "coucher_x" not in texte
    assert diagnostics["luminosite_adaptative"]["soiree_source"] == "schedule"


async def test_entites_retirees_avec_la_fonction(hass: HomeAssistant, fonction, ws):
    assert (await ws("luminosite_adaptative/configurer",
                     options={CONF_CAPTEUR_LUX: None}))["result"] == {"recharge": True}
    await hass.async_block_till_done()
    assert entite(hass, "binary_sensor", "luminosite_adaptative_soiree") is None
    assert bouton_terminer(hass) is None



async def test_formulaire_section_soiree(hass: HomeAssistant, fonction):
    section = {"soiree": True, "soiree_debut": "22:15:00", "soiree_fin": "22:15:00",
               "soiree_reduction": 30, "soiree_lumiere_bleue": False}
    flux = await base.formulaire(hass, fonction, section_soiree=section)
    assert flux["errors"] == {"soiree_fin": "soiree_debut_egal_fin"}
    flux = await base.formulaire(hass, fonction,
                                 section_soiree={**section, "soiree_fin": "05:30:00"})
    assert flux["type"] == "create_entry"
    await hass.async_block_till_done()
    options = fonction.options
    assert (options["soiree_debut"], options["soiree_fin"], options["soiree_reduction"]) == (
        "22:15", "05:30", 30)
    assert "soiree_entite" not in options
    # L'entité de la Soirée elle-même n'est pas proposée comme source.
    flux = await hass.config_entries.options.async_init(fonction.entry_id)
    section_schema = next(v for k, v in flux["data_schema"].schema.items()
                          if str(k) == "section_soiree").schema
    selecteur = next(v for k, v in section_schema.schema.items() if str(k) == "soiree_entite")
    assert soiree_entite(hass).entity_id in selecteur.config["exclude_entities"]
