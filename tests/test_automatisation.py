"""Briques d'automatisation : événement « manuel », actions regler et
appliquer_preset, boutons de presets."""

from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.lg_webos_tv.const import DOMAIN
from custom_components.lg_webos_tv.entite import descriptions
from custom_components.lg_webos_tv.presets import capturer_snapshot

from .conftest import entite

ID_MODE = "image.mode-selection"
ID_OLED = "image.parametres-avances.luminosite.luminosite-pixels-oled"
ID_NETTETE = "image.parametres-avances.clarte.ajuster-nettete"


async def passer_le_temps(hass, secondes=1.0):
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=secondes))
    await hass.async_block_till_done()


# ------------------------------------------------------------ événement

async def test_rafale_manuelle_un_seul_evenement(hass: HomeAssistant, installe, faux_client):
    evenement = entite(hass, "event", "reglage_modifie")
    for valeur in ("59", "66", "78", "100", "100"):
        await faux_client.notifier("picture", {"backlight": valeur},
                                   caller="com.webos.app.quicksettings")
    await hass.async_block_till_done()
    assert hass.states.get(evenement).state == "unknown"  # rafale en cours

    await passer_le_temps(hass)
    etat = hass.states.get(evenement)
    assert etat.attributes["event_type"] == "manuel"
    assert etat.attributes["entree_id"] == ID_OLED
    assert etat.attributes["libelle"] == "Luminosité des pixels OLED"
    assert etat.attributes["valeur"] == 100
    assert etat.attributes["mode_image"] == "expert2"


async def test_changement_de_mode_sans_evenement_parasite(hass: HomeAssistant, installe,
                                                          faux_client):
    evenements = []
    hass.bus.async_listen("state_changed", lambda e: evenements.append(e)
                          if e.data["entity_id"] == entite(hass, "event", "reglage_modifie")
                          else None)
    await faux_client.notifier("picture", {"pictureMode": "cinema"},
                               caller="com.webos.app.quicksettings")
    await faux_client.notifier("picture", {"backlight": "40", "contrast": "85"}, caller=None)
    await passer_le_temps(hass)
    assert len(evenements) == 1
    etat = evenements[0].data["new_state"]
    assert etat.attributes["cle"] == "pictureMode"
    assert etat.attributes["valeur_libelle"] == "Cinéma"


async def test_nos_ecritures_ne_declenchent_pas_l_evenement(hass: HomeAssistant, installe):
    await hass.services.async_call("number", "set_value", {
        "entity_id": entite(hass, "number", ID_OLED), "value": 30}, blocking=True)
    await passer_le_temps(hass)
    assert hass.states.get(entite(hass, "event", "reglage_modifie")).state == "unknown"


# ---------------------------------------------------------------- regler

async def regler(hass, **donnees):
    return await hass.services.async_call(DOMAIN, "regler", donnees, blocking=True,
                                          return_response=True)


async def test_regler_renvoie_le_resultat(hass: HomeAssistant, installe, faux_client):
    reponse = await regler(hass, entity_id=entite(hass, "number", ID_OLED), valeur=42)
    assert reponse == {"ok": True, "ecrit": True, "ancienne": 80, "nouvelle": 42,
                       "mode_image": "expert2"}
    assert faux_client.valeurs["picture"]["backlight"] == 42


async def test_regler_liste_par_libelle_ou_valeur_api(hass: HomeAssistant, installe,
                                                      faux_client):
    mode = entite(hass, "select", ID_MODE)
    await regler(hass, entity_id=mode, valeur="Cinéma")
    assert faux_client.valeurs["picture"]["pictureMode"] == "cinema"
    await regler(hass, entity_id=mode, valeur="expert1")
    assert faux_client.valeurs["picture"]["pictureMode"] == "expert1"


async def test_regler_garde_de_mode(hass: HomeAssistant, installe, faux_client):
    oled = entite(hass, "number", ID_OLED)
    reponse = await regler(hass, entity_id=oled, valeur=10, mode_image="cinema")
    assert reponse["ok"] is False and reponse["ecrit"] is False
    assert reponse["mode_image"] == "expert2"
    assert faux_client.valeurs["picture"]["backlight"] == 80
    # Libellé du menu accepté aussi pour le mode.
    reponse = await regler(hass, entity_id=oled, valeur=10,
                           mode_image="Expert (pièce sombre, nuit)")
    assert reponse["ok"] is True
    assert faux_client.valeurs["picture"]["backlight"] == 10


@pytest.mark.parametrize(("plateforme", "unique_id", "valeur", "cle_erreur"), [
    ("select", ID_MODE, "Inexistant", "valeur_invalide"),
    ("number", ID_OLED, "beaucoup", "valeur_invalide"),
    ("sensor", "son.mode-selection", "standard", "lecture_seule"),
])
async def test_regler_valeurs_refusees(hass: HomeAssistant, installe, plateforme,
                                       unique_id, valeur, cle_erreur):
    from homeassistant.helpers import entity_registry as er

    entity_id = entite(hass, plateforme, unique_id)
    if er.async_get(hass).async_get(entity_id).disabled_by:
        er.async_get(hass).async_update_entity(entity_id, disabled_by=None)
    with pytest.raises(ServiceValidationError) as erreur:
        await regler(hass, entity_id=entity_id, valeur=valeur)
    assert erreur.value.translation_key == cle_erreur


async def test_regler_ecriture_refusee(hass: HomeAssistant, installe, faux_client):
    faux_client.refuser.add(("picture", "backlight"))
    with pytest.raises(HomeAssistantError) as erreur:
        await regler(hass, entity_id=entite(hass, "number", ID_OLED), valeur=5)
    assert erreur.value.translation_key == "ecriture_echouee"


def test_modes_de_l_action_alignes_sur_l_arbre():
    services = yaml.safe_load(
        (Path(__file__).parent.parent / "custom_components" / DOMAIN / "services.yaml")
        .read_text())
    options = services["regler"]["fields"]["mode_image"]["selector"]["select"]["options"]
    mode = next(d for d in descriptions() if d.entree_id == ID_MODE)
    assert options == list(mode.choix.values())


# --------------------------------------------------------------- presets

async def creer_preset(installe, nom, entrees=None):
    d = installe.runtime_data
    await d.presets.sauvegarder(nom, capturer_snapshot(
        d.televiseur.etat, d.televiseur.mode_image, entrees))


async def test_action_appliquer_preset(hass: HomeAssistant, installe, faux_client):
    await creer_preset(installe, "Soirée", [ID_MODE, ID_NETTETE])
    faux_client.valeurs["picture"]["sharpness"] = 1
    installe.runtime_data.televiseur.etat["picture"]["sharpness"] = 1
    reponse = await hass.services.async_call(DOMAIN, "appliquer_preset", {"nom": "Soirée"},
                                             blocking=True, return_response=True)
    assert set(reponse["appliques"]) == {ID_MODE, ID_NETTETE}
    assert reponse["echecs"] == []
    assert faux_client.valeurs["picture"]["sharpness"] == 10

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "appliquer_preset", {"nom": "Inconnu"},
                                       blocking=True, return_response=True)


async def test_boutons_suivent_les_presets(hass: HomeAssistant, installe, faux_client):
    await creer_preset(installe, "Soirée", [ID_NETTETE])
    await hass.async_block_till_done()
    bouton = entite(hass, "button", "preset_Soirée")
    assert bouton is not None
    assert hass.states.get(bouton).attributes["friendly_name"].endswith("Soirée")

    faux_client.valeurs["picture"]["sharpness"] = 1
    installe.runtime_data.televiseur.etat["picture"]["sharpness"] = 1
    await hass.services.async_call("button", "press", {"entity_id": bouton}, blocking=True)
    assert faux_client.valeurs["picture"]["sharpness"] == 10

    # Preset d'un autre mode d'image : appliqué en partie, l'échec est signalé.
    installe.runtime_data.televiseur.etat["picture"]["pictureMode"] = "cinema"
    with pytest.raises(HomeAssistantError) as erreur:
        await hass.services.async_call("button", "press", {"entity_id": bouton},
                                       blocking=True)
    assert erreur.value.translation_key == "preset_partiel"

    await installe.runtime_data.presets.supprimer("Soirée")
    await hass.async_block_till_done()
    assert entite(hass, "button", "preset_Soirée") is None
    assert hass.states.get(bouton) is None
