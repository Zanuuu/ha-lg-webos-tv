"""Luminosité adaptative, lot 6 : capteur de secours (R12), contre
l'intégration et un téléviseur simulé. Le secours ne prend le relais qu'une
fois le facteur appris (30 échantillons, un par minute) et le rapport
stable."""

from datetime import timedelta

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.lg_webos_tv.const import (CONF_CAPTEUR_LUX,
                                                 CONF_CAPTEUR_SECOURS, DOMAIN)
from custom_components.lg_webos_tv.diagnostics import \
    async_get_config_entry_diagnostics
from custom_components.lg_webos_tv.secours import ECHANTILLONS_MIN

from . import test_luminosite_adaptative as base
from .conftest import entite
from .test_luminosite_adaptative import (LUX, RAMPE_S, TELECOMMANDE, etat, journal,
                                         luminosite, passer_le_temps)

SECOURS = "sensor.plafond_lux"
ATTRIBUTS = {"device_class": "illuminance", "unit_of_measurement": "lx"}

horloge = base.horloge
fonction = base.fonction


@pytest.fixture
def options_entree():
    return {CONF_CAPTEUR_LUX: LUX, CONF_CAPTEUR_SECOURS: SECOURS}


def la(entree):
    return entree.runtime_data.luminosite_adaptative


async def minute(hass, principal=None, secours=None):
    """Une minute : chaque capteur donné publie (même valeur : rapport sans
    changement d'état), puis l'horloge avance d'un coup."""
    if principal is not None:
        hass.states.async_set(LUX, str(principal), ATTRIBUTS)
    if secours is not None:
        hass.states.async_set(SECOURS, str(secours), ATTRIBUTS)
    base._horloge.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


async def apprendre(hass, principal=20, secours=10, minutes=ECHANTILLONS_MIN + 1):
    for _ in range(minutes):
        await minute(hass, principal, secours)


async def test_facteur_appris_puis_relais_sans_saut(hass: HomeAssistant, fonction, faux_client):
    fn = la(fonction)
    await apprendre(hass, minutes=ECHANTILLONS_MIN - 2)
    assert fn.details()["secours"]["etat"] == "apprentissage"
    await apprendre(hass, minutes=3)
    secours = fn.details()["secours"]
    assert (secours["etat"], secours["facteur"]) == ("stable", 2.0)
    assert journal(fonction, "rapport_secours")[-1]["etat"] == "stable"

    ecritures = len(await fonction.runtime_data.historique.lister(100))
    hass.states.async_set(LUX, "unavailable")
    await passer_le_temps(hass, RAMPE_S)
    assert fn.capteur_actif == "secours"
    assert etat(hass).state == "active"
    assert etat(hass).attributes["capteur_actif"] == "secours"
    [bascule] = journal(fonction, "bascule")
    assert (bascule["raison"], bascule["facteur"]) == ("indisponible", 2.0)
    # 10 lx × 2 = 20 lx, comme le principal : aucune écriture.
    assert fn.lux_filtre == pytest.approx(20, rel=0.01)
    assert luminosite(faux_client) == 60
    assert len(await fonction.runtime_data.historique.lister(100)) == ecritures

    # Le secours suit l'éclairage, converti : 150 × 2 = 300 lx.
    hass.states.async_set(SECOURS, "150", ATTRIBUTS)
    await passer_le_temps(hass, 120)
    assert luminosite(faux_client) >= 98

    hass.states.async_set(LUX, "300", ATTRIBUTS)
    await passer_le_temps(hass, 5)
    assert fn.capteur_actif == "principal"
    assert journal(fonction, "retour")


async def test_pas_de_relais_avant_apprentissage(hass: HomeAssistant, fonction, faux_client):
    hass.states.async_set(SECOURS, "10", ATTRIBUTS)
    hass.states.async_set(LUX, "unavailable")
    await passer_le_temps(hass, 5)
    assert etat(hass).state == "capteur_indisponible"
    assert la(fonction).capteur_actif is None
    assert journal(fonction, "bascule") == []
    # Santé recalculée à la minute.
    await passer_le_temps(hass, 60)
    diagnostic = next(d for d in la(fonction).sante()["diagnostics"] if d["id"] == "secours")
    # Principal indisponible : pas d'échantillon possible, apprentissage figé.
    assert diagnostic["niveau"] == "attente"


async def test_rapport_instable_jamais_utilise(hass: HomeAssistant, fonction):
    for i in range(ECHANTILLONS_MIN + 5):
        await minute(hass, 20, (2, 10, 60)[i % 3])
    assert la(fonction).details()["secours"]["etat"] == "instable"
    diagnostic = next(d for d in la(fonction).sante()["diagnostics"] if d["id"] == "secours")
    assert diagnostic["niveau"] == "avertissement"
    hass.states.async_set(LUX, "unavailable")
    await passer_le_temps(hass, 5)
    assert etat(hass).state == "capteur_indisponible"


async def test_principal_fige_releve_par_le_secours(hass: HomeAssistant, fonction, faux_client):
    await apprendre(hass)
    # Le principal se tait plus de deux heures, le secours publie encore.
    for _ in range(125):
        await minute(hass, secours=10)
    fn = la(fonction)
    assert fn.capteur_actif == "secours"
    assert journal(fonction, "bascule")[-1]["raison"] == "fige"
    assert etat(hass).state == "active"
    probleme = ir.async_get(hass).async_get_issue(DOMAIN, "capteur_fige")
    assert probleme is not None and probleme.translation_key == "capteur_fige_secours"
    diagnostic = next(d for d in fn.sante()["diagnostics"] if d["id"] == "capteur_fige")
    assert (diagnostic["niveau"], diagnostic["valeurs"]["relais"]) == ("avertissement", True)

    # Réglage manuel pendant le relais : pas de correction.
    await faux_client.notifier("picture", {"backlight": "70"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    assert journal(fonction, "correction_ecartee")[-1]["raison"] == "secours"
    assert fn.details()["correction_en_cours"] is None

    await minute(hass, principal=20, secours=10)
    assert fn.capteur_actif == "principal"
    assert ir.async_get(hass).async_get_issue(DOMAIN, "capteur_fige") is None


async def test_statistiques_du_principal_seul(hass: HomeAssistant, fonction):
    await apprendre(hass)
    fn = la(fonction)
    rapports = fn._accumulateur.stats.rapports
    hass.states.async_set(LUX, "unavailable")
    for _ in range(5):
        await minute(hass, secours=10)
    assert fn.capteur_actif == "secours"
    assert fn._accumulateur.stats.rapports == rapports


async def test_rapport_conserve_au_redemarrage(hass: HomeAssistant, fonction):
    await apprendre(hass)
    assert await hass.config_entries.async_reload(fonction.entry_id)
    await passer_le_temps(hass, 2)
    secours = la(fonction).details()["secours"]
    assert (secours["etat"], secours["facteur"]) == ("stable", 2.0)


async def test_secours_configure_par_le_panneau(hass: HomeAssistant, fonction, ws):
    hass.states.async_set("sensor.bureau_lux", "5", ATTRIBUTS)
    reponse = await ws("luminosite_adaptative/configurer",
                       options={CONF_CAPTEUR_SECOURS: LUX})
    assert not reponse["success"] and "capteur_secours" in reponse["error"]["message"]
    reponse = await ws("luminosite_adaptative/configurer",
                       options={CONF_CAPTEUR_SECOURS: "sensor.absent"})
    assert not reponse["success"]
    reponse = await ws("luminosite_adaptative/configurer",
                       options={CONF_CAPTEUR_SECOURS: "sensor.bureau_lux"})
    assert reponse["success"]
    assert la(fonction).capteur_secours == "sensor.bureau_lux"
    assert la(fonction).details()["secours"]["etat"] == "apprentissage"
    reponse = await ws("luminosite_adaptative/configurer", options={CONF_CAPTEUR_SECOURS: None})
    assert reponse["success"]
    assert la(fonction).capteur_secours is None
    assert CONF_CAPTEUR_SECOURS not in fonction.options
    # Le « Lux filtré » de la fonction n'est pas proposé comme capteur.
    configuration = (await ws("luminosite_adaptative/configuration"))["result"]
    assert all(c["entity_id"].startswith("sensor.") and "lg_webos_tv" not in c["entity_id"]
               for c in configuration["capteurs"])


async def test_diagnostics_sans_identifiant_de_capteur(hass: HomeAssistant, fonction):
    await apprendre(hass, minutes=3)
    diagnostics = await async_get_config_entry_diagnostics(hass, fonction)
    texte = str(diagnostics["luminosite_adaptative"])
    assert SECOURS not in texte and LUX not in texte
    assert diagnostics["luminosite_adaptative"]["secours"]["etat"] == "apprentissage"


async def test_formulaire_capteur_de_secours(hass: HomeAssistant, fonction):
    flux = await base.formulaire(hass, fonction, capteur_secours=LUX)
    assert flux["errors"] == {CONF_CAPTEUR_SECOURS: "secours_identique"}
    flux = await base.formulaire(hass, fonction, capteur_secours=SECOURS,
                                 avance={"ambiance_sombre": 10.5})
    assert flux["type"] == "create_entry"
    await hass.async_block_till_done()
    assert (fonction.options[CONF_CAPTEUR_SECOURS], fonction.options["ambiance_sombre"]) == (
        SECOURS, 10.5)
    # Le « Lux filtré » de la fonction est exclu du sélecteur.
    flux = await hass.config_entries.options.async_init(fonction.entry_id)
    selecteur = next(cle for cle in flux["data_schema"].schema if str(cle) == CONF_CAPTEUR_LUX)
    exclus = flux["data_schema"].schema[selecteur].config["exclude_entities"]
    assert entite(hass, "sensor", "luminosite_adaptative_lux_filtre") in exclus
