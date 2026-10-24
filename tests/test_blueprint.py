"""Blueprint « luminosité OLED selon la lumière ambiante », exécuté dans
Home Assistant contre l'intégration et un téléviseur simulé."""

import shutil
from datetime import timedelta
from pathlib import Path

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import entite

BLUEPRINT = Path(__file__).parent.parent / "blueprints" / "automation" / "lg_webos_tv" \
    / "luminosite_ambiante.yaml"
ID_OLED = "image.parametres-avances.luminosite.luminosite-pixels-oled"
LUX = "sensor.salon_lux"


async def regler_lux(hass, lux):
    hass.states.async_set(LUX, str(lux), {"device_class": "illuminance",
                                          "unit_of_measurement": "lx"})
    await hass.async_block_till_done()


@pytest.fixture
async def automatisation(hass: HomeAssistant, installe, faux_client, tmp_path):
    cible = tmp_path / "blueprints" / "automation" / "lg_webos_tv"
    cible.mkdir(parents=True)
    shutil.copy(BLUEPRINT, cible)
    # Mode non calibré : le blueprint laisse les modes Expert de côté par défaut.
    await faux_client.notifier("picture", {"pictureMode": "vivid"},
                               caller="com.webos.app.quicksettings")
    await regler_lux(hass, 20)
    assert await async_setup_component(hass, "automation", {"automation": {
        "alias": "Luminosité ambiante",
        "use_blueprint": {
            "path": "lg_webos_tv/luminosite_ambiante.yaml",
            "input": {
                "capteur_lux": LUX,
                "luminosite": entite(hass, "number", ID_OLED),
                "evenement": entite(hass, "event", "reglage_modifie"),
                "connexion": entite(hass, "binary_sensor", "connexion"),
            },
        },
    }})
    await hass.async_block_till_done()
    assert hass.states.get("automation.luminosite_ambiante").state == "on"
    # Laisse passer le regroupement de l'événement du changement de mode.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    return installe


async def test_echelle_logarithmique(hass: HomeAssistant, automatisation, faux_client):
    await regler_lux(hass, 300)
    assert faux_client.valeurs["picture"]["backlight"] == 100
    await regler_lux(hass, 2)  # sous le minimum : luminosité minimale
    assert faux_client.valeurs["picture"]["backlight"] == 40
    # ln(50/5) / ln(300/5) = 0,562 → 40 + 0,562 × 60 = 73,7
    await regler_lux(hass, 50)
    assert faux_client.valeurs["picture"]["backlight"] == 74


async def test_petit_ecart_ignore(hass: HomeAssistant, automatisation, faux_client):
    await regler_lux(hass, 50)
    assert faux_client.valeurs["picture"]["backlight"] == 74
    ecritures = len(await automatisation.runtime_data.historique.lister())
    await regler_lux(hass, 52)  # cible 75 : écart de 1 < 3
    assert len(await automatisation.runtime_data.historique.lister()) == ecritures


async def test_pause_apres_reglage_manuel_puis_rallumage(hass: HomeAssistant,
                                                          automatisation, faux_client):
    await faux_client.notifier("picture", {"backlight": "55"})  # télécommande
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    await regler_lux(hass, 300)
    assert faux_client.valeurs["picture"]["backlight"] == "55"

    # Le téléviseur s'éteint puis se rallume : la pause est levée.
    tv = automatisation.runtime_data.televiseur
    await tv._changer_etat("deconnecte")
    await hass.async_block_till_done()
    await tv._changer_etat("connecte")
    await hass.async_block_till_done()
    assert faux_client.valeurs["picture"]["backlight"] == 100


async def test_mode_calibre_laisse_de_cote(hass: HomeAssistant, automatisation, faux_client):
    await faux_client.notifier("picture", {"pictureMode": "expert2"},
                               caller="com.webos.app.quicksettings")
    await hass.async_block_till_done()
    await regler_lux(hass, 300)
    assert faux_client.valeurs["picture"]["backlight"] == 80


def test_modes_du_blueprint_alignes_sur_l_arbre():
    import yaml

    from custom_components.lg_webos_tv.entite import descriptions

    class Chargeur(yaml.SafeLoader):
        pass

    Chargeur.add_constructor("!input", lambda chargeur, noeud: noeud.value)
    contenu = yaml.load(BLUEPRINT.read_text(), Loader=Chargeur)
    options = contenu["blueprint"]["input"]["modes_exclus"]["selector"]["select"]["options"]
    mode = next(d for d in descriptions() if d.entree_id == "image.mode-selection")
    assert {o["label"]: o["value"] for o in options} == mode.choix
