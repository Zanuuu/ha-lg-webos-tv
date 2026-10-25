"""Luminosité adaptative, lot 6 : décalage pilotable (R11), entités « Lux
filtré » et « Ambiance » (R14a), contre l'intégration et un téléviseur
simulé. Mêmes outils que test_luminosite_adaptative.py (horloge simulée,
ticks de 0,5 s)."""

import pytest

from homeassistant.core import HomeAssistant

from custom_components.lg_webos_tv.const import (CONF_CAPTEUR_LUX,
                                                 OPTIONS_LUMINOSITE_DEFAUT)
from custom_components.lg_webos_tv.luminosite_adaptative import (
    modes_proposes, valider_options)

from . import test_luminosite_adaptative as base
from .conftest import entite
from .test_luminosite_adaptative import (LUX, RAMPE_S, TELECOMMANDE, etat, journal,
                                         luminosite, passer_le_temps, regler_lux,
                                         types_journal)

# Horloge simulée, options de l'entrée et fonction installée : les mêmes
# fixtures que les tests des lots 1 à 5.
horloge = base.horloge
options_entree = base.options_entree
fonction = base.fonction


def decalage_entite(hass):
    return entite(hass, "number", "luminosite_adaptative_decalage")


async def regler_decalage(hass, valeur):
    await hass.services.async_call("number", "set_value", {
        "entity_id": decalage_entite(hass), "value": valeur}, blocking=True)
    await passer_le_temps(hass, RAMPE_S)


def fonction_de(entree):
    return entree.runtime_data.luminosite_adaptative


# --------------------------------------------------------------- décalage

async def test_decalage_ajoute_sans_pause(hass: HomeAssistant, fonction, faux_client):
    etat_decalage = hass.states.get(decalage_entite(hass))
    assert float(etat_decalage.state) == 0
    assert etat_decalage.attributes["min"] == -30 and etat_decalage.attributes["max"] == 30
    await regler_decalage(hass, -10)
    assert luminosite(faux_client) == 50
    assert etat(hass).state == "active"
    assert etat(hass).attributes["decalage"] == -10
    assert float(hass.states.get(decalage_entite(hass)).state) == -10
    [evenement] = journal(fonction, "decalage")
    assert (evenement["ancien"], evenement["nouveau"], evenement["origine"]) == (
        -10 + 10, -10, "home_assistant")
    assert journal(fonction, "pause") == []
    # Une écriture de la fonction elle-même, historisée comme telle.
    [derniere, *_] = await fonction.runtime_data.historique.lister(1)
    assert (derniere["origine"], derniere["nouvelle"]) == ("luminosite_adaptative", 50)


async def test_decalage_borne_a_0_100(hass: HomeAssistant, fonction, faux_client):
    await regler_lux(hass, 300)
    await regler_decalage(hass, 10)
    assert etat(hass).attributes["cible"] == 100
    assert luminosite(faux_client) >= 98
    await regler_lux(hass, 2)
    await regler_decalage(hass, -30)
    # 40 − 30 : sous la luminosité minimale de la courbe, comme voulu.
    assert etat(hass).attributes["cible"] == 10
    assert luminosite(faux_client) <= 12


async def test_decalage_en_pause_applique_a_la_reprise(hass: HomeAssistant, fonction,
                                                      faux_client):
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    await regler_decalage(hass, 10)
    assert etat(hass).state == "pause"
    assert luminosite(faux_client) == 55
    fonction_de(fonction).reprendre()
    await passer_le_temps(hass, RAMPE_S)
    assert luminosite(faux_client) == 70


async def test_decalage_conserve_au_redemarrage(hass: HomeAssistant, fonction, faux_client):
    await regler_decalage(hass, 5)
    assert await hass.config_entries.async_reload(fonction.entry_id)
    await passer_le_temps(hass, RAMPE_S)
    assert fonction_de(fonction).decalage == 5
    assert float(hass.states.get(decalage_entite(hass)).state) == 5
    assert luminosite(faux_client) == 65


async def test_correction_mesuree_avec_le_decalage(hass: HomeAssistant, fonction, faux_client):
    await regler_decalage(hass, -10)
    await faux_client.notifier("picture", {"backlight": "53"}, caller=TELECOMMANDE)
    await passer_le_temps(hass, 601)
    [correction] = journal(fonction, "correction")
    assert (correction["valeur"], correction["cible"]) == (53, 50)
    [enregistree] = fonction_de(fonction).suggestions()["corrections"]
    assert (enregistree["ecart"], enregistree["decalage"]) == (3, -10)


async def test_correction_ecartee_si_le_decalage_change(hass: HomeAssistant, fonction,
                                                        faux_client):
    await faux_client.notifier("picture", {"backlight": "53"}, caller=TELECOMMANDE)
    await passer_le_temps(hass, 60)
    await regler_decalage(hass, -10)
    [ecartee] = journal(fonction, "correction_ecartee")
    assert ecartee["raison"] == "decalage"


async def test_ancrage_avec_decalage(hass: HomeAssistant, fonction, faux_client):
    await regler_decalage(hass, -10)
    la = fonction_de(fonction)
    la.commencer_mise_en_route()
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    options, compte_rendu = la.ancrer()
    # La courbe est calée sur 65 ; avec le décalage, la cible redonne 55.
    assert compte_rendu["decalage"] == -10 and compte_rendu["cible"] == 55
    assert options["ancrages"][0]["luminosite"] == 65
    la.terminer_mise_en_route()


async def test_decalage_par_le_panneau(hass: HomeAssistant, fonction, faux_client, ws):
    reponse = await ws("luminosite_adaptative/decalage", valeur=7)
    assert reponse["success"] and reponse["result"]["decalage"] == 7
    await passer_le_temps(hass, RAMPE_S)
    assert luminosite(faux_client) == 67
    assert journal(fonction, "decalage")[-1]["origine"] == "panneau"
    reponse = await ws("luminosite_adaptative/decalage", valeur=31)
    assert not reponse["success"]
    assert fonction_de(fonction).decalage == 7


async def test_decalage_reserve_aux_administrateurs(hass: HomeAssistant, fonction,
                                                    hass_ws_client, hass_read_only_access_token):
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json({"id": 1, "type": "lg_webos_tv/luminosite_adaptative/decalage",
                            "valeur": 5})
    assert (await client.receive_json())["error"]["code"] == "unauthorized"


# ------------------------------------------------------ lux filtré, ambiance

def lux_filtre(hass):
    return hass.states.get(entite(hass, "sensor", "luminosite_adaptative_lux_filtre"))


def ambiance(hass):
    return hass.states.get(entite(hass, "sensor", "luminosite_adaptative_ambiance"))


async def test_lux_filtre_et_ambiance(hass: HomeAssistant, fonction):
    etat_lux = lux_filtre(hass)
    assert float(etat_lux.state) == pytest.approx(20, abs=0.1)
    assert etat_lux.attributes["unit_of_measurement"] == "lx"
    assert etat_lux.attributes["device_class"] == "illuminance"
    assert ambiance(hass).state == "intermediaire"
    assert ambiance(hass).attributes["seuil_sombre"] == pytest.approx(19.6)

    await regler_lux(hass, 300)
    assert float(lux_filtre(hass).state) == pytest.approx(300, abs=1)
    # Dix minutes avant tout changement d'ambiance.
    assert ambiance(hass).state == "intermediaire"
    await passer_le_temps(hass, 500)
    assert ambiance(hass).state == "claire"
    assert journal(fonction, "ambiance")[-1]["valeur"] == "claire"


async def test_disponibles_televiseur_eteint_et_en_pause(hass: HomeAssistant, fonction,
                                                         faux_client):
    await faux_client.notifier("picture", {"backlight": "55"}, caller=TELECOMMANDE)
    await hass.async_block_till_done()
    await fonction.runtime_data.televiseur._changer_etat("deconnecte")
    await regler_lux(hass, 2)
    assert etat(hass).state == "televiseur_deconnecte"
    # Le filtre avance sans la fonction : la descente lissée est suivie.
    assert float(lux_filtre(hass).state) == pytest.approx(2, abs=0.1)
    await passer_le_temps(hass, 500)
    assert ambiance(hass).state == "sombre"


async def test_lux_filtre_indisponible_sans_mesure(hass: HomeAssistant, fonction):
    hass.states.async_set(LUX, "unavailable")
    await passer_le_temps(hass)
    assert lux_filtre(hass).state == "unavailable"
    assert ambiance(hass).state == "unavailable"


async def test_ambiance_restauree_au_redemarrage(hass: HomeAssistant, fonction):
    await regler_lux(hass, 300)
    await passer_le_temps(hass, 500)
    assert ambiance(hass).state == "claire"
    # Retour à l'éclairage intermédiaire juste avant le redémarrage : pas de
    # changement d'état parasite, l'ambiance attend ses 10 minutes.
    await regler_lux(hass, 40, secondes=60)
    assert await hass.config_entries.async_reload(fonction.entry_id)
    await passer_le_temps(hass, 60)
    assert ambiance(hass).state == "claire"
    await passer_le_temps(hass, 600)
    assert ambiance(hass).state == "intermediaire"


async def test_seuils_figes_par_les_options(hass: HomeAssistant, fonction, ws):
    reponse = await ws("luminosite_adaptative/configurer",
                       options={"ambiance_sombre": 30, "ambiance_claire": 200})
    assert reponse["success"]
    await passer_le_temps(hass, 2)
    assert ambiance(hass).attributes["seuil_sombre"] == 30
    reponse = await ws("luminosite_adaptative/configurer",
                       options={"ambiance_sombre": 300})
    assert not reponse["success"] and "ambiance_claire" in reponse["error"]["message"]


# ------------------------------------------------------- rétrocompatibilité

def test_options_2_9_0_inchangees():
    """Options d'une installation 2.9.0 : aucune clé du lot 6, aucune
    erreur, rien d'ajouté."""
    anciennes = {**OPTIONS_LUMINOSITE_DEFAUT, CONF_CAPTEUR_LUX: LUX, "pause": 90}
    options, erreurs = valider_options(dict(anciennes), modes_proposes())
    assert erreurs == {} and options == anciennes
    # Champs facultatifs laissés vides par le formulaire.
    options, erreurs = valider_options(
        {**anciennes, "capteur_secours": None, "ambiance_sombre": None}, modes_proposes())
    assert erreurs == {} and options == anciennes


@pytest.mark.parametrize("options_entree", [{CONF_CAPTEUR_LUX: LUX, "pause": 90}])
async def test_entree_2_9_0(hass: HomeAssistant, fonction):
    la = fonction_de(fonction)
    assert (la.decalage, la.capteur_secours, la.capteur_actif) == (0, None, "principal")
    assert la.details()["secours"] is None
    assert types_journal(fonction).count("bascule") == 0
