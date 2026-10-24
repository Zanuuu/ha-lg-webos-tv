"""Entités dérivées de l'arbre : génération, état poussé par le téléviseur,
écriture depuis Home Assistant, diagnostics et réparations."""

from unittest.mock import patch

import pytest

from homeassistant.const import CONF_HOST, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lg_webos_tv import arbre
from custom_components.lg_webos_tv.const import CONF_CLE_CLIENT, DOMAIN
from custom_components.lg_webos_tv.diagnostics import \
    async_get_config_entry_diagnostics
from custom_components.lg_webos_tv.entite import (ACTIVES_PAR_DEFAUT,
                                                  descriptions)

from .conftest import attendre

ID_MODE = "image.mode-selection"
ID_OLED = "image.parametres-avances.luminosite.luminosite-pixels-oled"
ID_PROTECTION_YEUX = "image.parametres-avances.luminosite.protection-yeux"
ID_ECONOMIE = "general.economie-energie.fonction-economie-energie"
ID_EARC = "son.parametres-avances.compatibilite-earc"


# ------------------------------------------------------------- génération

def par_id():
    return {d.entree_id: d for d in descriptions()}


def test_types_d_entites():
    d = par_id()
    assert d[ID_MODE].plateforme == "select"
    assert d[ID_OLED].plateforme == "number"
    assert d[ID_OLED].bornes == {"min": 0, "max": 100, "pas": 1}
    assert d[ID_PROTECTION_YEUX].plateforme == "switch"
    assert d["son.mode-selection"].plateforme == "sensor"


def test_correspondance_incomplete_jamais_exposee():
    d = par_id()
    # Choix sans valeur API (gamma), curseurs sans bornes (avSync), actions,
    # texte, mode magasin, lectures seules douteuses.
    for absente in ("image.parametres-avances.luminosite.gamma",
                    "son.parametres-avances.synchroniser-image-son",
                    "general.systeme.heure-et-minuterie.heure-date-fuseau",
                    "general.systeme.lieu.code-postal",
                    "assistance.mode-domicile-magasin",
                    "image.parametres-avances.luminosite.plage-video"):
        assert absente not in d
    # Pays : effets de bord en cascade à l'écriture (incidents § 1) → capteur.
    assert d["general.systeme.lieu.pays"].plateforme == "sensor"


def test_noms_et_identifiants_uniques():
    noms = [d.nom for d in descriptions()]
    assert len(noms) == len(set(noms))
    assert "Image — Mode Sélection" in noms and "Son — Mode Sélection" in noms
    assert "Balance des blancs — Méthode" in noms
    assert len({d.entree_id for d in descriptions()}) == len(descriptions())


def test_libelles_de_choix_uniques():
    for d in descriptions():
        entree = arbre.par_id()[d.entree_id]
        libelles = [c["libelle"] for c in entree.get("choix") or [] if "valeur_api" in c]
        assert len(libelles) == len(d.choix), d.entree_id


def test_modes_observes_sur_le_televiseur_tous_connus():
    # Modes vus défiler aux réglages rapides sur 43.21.77 (rapport-api, phase 7).
    observes = {"vivid", "normal", "eco", "cinema", "sports", "game",
                "filmMaker", "expert1", "expert2"}
    assert observes <= set(par_id()[ID_MODE].choix.values())


def test_actives_par_defaut_existent():
    assert ACTIVES_PAR_DEFAUT <= set(par_id())


# --------------------------------------------------------- intégration HA

@pytest.fixture
async def installe(hass: HomeAssistant, tmp_path, faux_client):
    hass.config.config_dir = str(tmp_path)
    entree = MockConfigEntry(domain=DOMAIN, title="LG webOS TV",
                             data={CONF_HOST: "192.0.2.10", CONF_CLE_CLIENT: "cle"})
    entree.add_to_hass(hass)

    async def construire(hote, **options):
        return faux_client

    with patch("custom_components.lg_webos_tv.televiseur._construire_client", construire):
        assert await hass.config_entries.async_setup(entree.entry_id)
        tv = entree.runtime_data.televiseur
        tv.delai_notification = 0.05
        tv.intervalle_relecture = 0
        assert await attendre(lambda: tv.etat_connexion == "connecte")
        await hass.async_block_till_done()
        yield entree
        await hass.config_entries.async_unload(entree.entry_id)


def entite(hass, plateforme, unique_id):
    return er.async_get(hass).async_get_entity_id(plateforme, DOMAIN, unique_id)


async def test_etat_initial_et_mode_image(hass: HomeAssistant, installe):
    etat = hass.states.get(entite(hass, "select", ID_MODE))
    assert etat.state == "Expert (pièce sombre, nuit)"
    oled = hass.states.get(entite(hass, "number", ID_OLED))
    assert float(oled.state) == 80
    assert oled.attributes["mode_image"] == "expert2"
    assert oled.attributes["min"] == 0 and oled.attributes["max"] == 100
    assert hass.states.get(entite(hass, "switch", ID_PROTECTION_YEUX)).state == "off"
    assert hass.states.get(entite(hass, "binary_sensor", "connexion")).state == "on"
    assert hass.states.get(entite(hass, "sensor", "voie_ecriture")).state == "ssap"


async def test_entite_hors_usage_courant_creee_desactivee(hass: HomeAssistant, installe):
    entity_id = entite(hass, "switch", ID_EARC)
    assert er.async_get(hass).async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(entity_id) is None


async def test_changement_a_la_telecommande_pousse_l_etat(hass: HomeAssistant, installe,
                                                          faux_client):
    await faux_client.notifier("picture", {"backlight": "60"})
    await hass.async_block_till_done()
    assert float(hass.states.get(entite(hass, "number", ID_OLED)).state) == 60

    # Changement de mode : le mode, puis les valeurs du nouveau mode.
    await faux_client.notifier("picture", {"pictureMode": "cinema"})
    await faux_client.notifier("picture", {"backlight": "40"})
    await hass.async_block_till_done()
    assert hass.states.get(entite(hass, "select", ID_MODE)).state == "Cinéma"
    oled = hass.states.get(entite(hass, "number", ID_OLED))
    assert float(oled.state) == 40
    assert oled.attributes["mode_image"] == "cinema"


async def test_ecriture_depuis_home_assistant(hass: HomeAssistant, installe, faux_client):
    oled = entite(hass, "number", ID_OLED)
    await hass.services.async_call("number", "set_value",
                                   {"entity_id": oled, "value": 55}, blocking=True)
    assert faux_client.valeurs["picture"]["backlight"] == 55
    assert float(hass.states.get(oled).state) == 55

    await hass.services.async_call("select", "select_option", {
        "entity_id": entite(hass, "select", ID_ECONOMIE), "option": "Maximum"}, blocking=True)
    assert faux_client.valeurs["picture"]["energySaving"] == "max"

    await hass.services.async_call("switch", "turn_on", {
        "entity_id": entite(hass, "switch", ID_PROTECTION_YEUX)}, blocking=True)
    assert faux_client.valeurs["picture"]["motionEyeCare"] == "on"

    historique = await installe.runtime_data.historique.lister()
    assert [h["cle"] for h in historique] == ["motionEyeCare", "energySaving", "backlight"]


async def test_ecriture_refusee_leve_une_erreur(hass: HomeAssistant, installe, faux_client):
    faux_client.refuser.add(("picture", "backlight"))
    oled = entite(hass, "number", ID_OLED)
    with pytest.raises(HomeAssistantError, match="refusée par le téléviseur"):
        await hass.services.async_call("number", "set_value",
                                       {"entity_id": oled, "value": 10}, blocking=True)
    assert float(hass.states.get(oled).state) == 80


async def test_indisponible_quand_le_televiseur_se_deconnecte(hass: HomeAssistant, installe):
    tv = installe.runtime_data.televiseur
    await tv._changer_etat("deconnecte")
    await hass.async_block_till_done()
    assert hass.states.get(entite(hass, "number", ID_OLED)).state == STATE_UNAVAILABLE
    assert hass.states.get(entite(hass, "binary_sensor", "connexion")).state == "off"


async def test_reparation_quand_l_ecriture_est_fermee(hass: HomeAssistant, installe):
    tv = installe.runtime_data.televiseur
    await tv._changer_ecriture(None)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "ecriture_impossible")
    assert hass.states.get(entite(hass, "binary_sensor", "ecriture_impossible")).state == "on"

    await tv._changer_ecriture("alerte")
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "ecriture_impossible") is None
    assert hass.states.get(entite(hass, "sensor", "voie_ecriture")).state == "alerte"


async def test_diagnostics_masquent_adresse_et_cle(hass: HomeAssistant, installe):
    diag = await async_get_config_entry_diagnostics(hass, installe)
    assert diag["entree"] == {CONF_HOST: "**REDACTED**", CONF_CLE_CLIENT: "**REDACTED**"}
    assert diag["mode_image"] == "expert2"
    assert diag["entites"]["number"] > 0
