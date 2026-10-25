"""API websocket du panneau (équivalent des anciennes routes REST de l'app)."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.lg_webos_tv import panneau

ID_NETTETE = "image.parametres-avances.clarte.ajuster-nettete"
ID_CONTRASTE = "image.parametres-avances.luminosite.ajuster-le-contraste"


@pytest.fixture
async def ws(hass: HomeAssistant, installe, hass_ws_client):
    client = await hass_ws_client(hass)
    compteur = iter(range(1, 10_000))

    async def envoyer(type_, **donnees):
        await client.send_json({"id": next(compteur), "type": f"lg_webos_tv/{type_}", **donnees})
        return await client.receive_json()

    envoyer.client = client
    envoyer.compteur = compteur
    return envoyer


async def test_arbre_et_reglages(ws):
    rep = await ws("arbre")
    assert rep["success"]
    assert [s["id"] for s in rep["result"]["sections"]][:2] == ["image", "son"]
    rep = await ws("reglages")
    assert rep["result"]["connexion"] == "connecte"
    assert rep["result"]["mode_image"] == "expert2"


async def test_ecrire_et_historique(ws, faux_client):
    rep = await ws("ecrire", entree_id=ID_NETTETE, valeur=25)
    assert rep["success"], rep
    assert rep["result"]["nouvelle"] == 25 and rep["result"]["cle"] == "sharpness"
    assert faux_client.valeurs["picture"]["sharpness"] == 25

    historique = (await ws("historique"))["result"]
    assert historique[0]["origine"] == "panneau"
    rep = await ws("historique/annuler", ecriture_id=historique[0]["id"])
    assert rep["result"]["ok"] is True
    assert faux_client.valeurs["picture"]["sharpness"] == 10


async def test_ecrire_erreurs(ws, faux_client):
    rep = await ws("ecrire", entree_id="inexistante", valeur=1)
    assert rep["error"]["code"] == "introuvable"
    rep = await ws("ecrire", entree_id=ID_NETTETE, valeur=999)
    assert rep["error"]["code"] == "invalide"
    faux_client.refuser.add(("picture", "sharpness"))
    rep = await ws("ecrire", entree_id=ID_NETTETE, valeur=12)
    assert rep["error"]["code"] == "refusee"
    assert "refusée par le téléviseur" in rep["error"]["message"]


async def test_revenir_a_un_instant(ws, faux_client):
    repere = time.time()
    await ws("ecrire", entree_id=ID_NETTETE, valeur=20)
    await ws("ecrire", entree_id=ID_CONTRASTE, valeur=90)
    rep = await ws("historique/revenir", horodatage=repere)
    assert all(r["ok"] for r in rep["result"]["resultats"])
    assert faux_client.valeurs["picture"]["sharpness"] == 10
    assert faux_client.valeurs["picture"]["contrast"] == 100


async def test_cycle_de_vie_d_un_preset(hass: HomeAssistant, ws, faux_client):
    rep = await ws("presets/creer", nom="Soirée", entrees=[ID_NETTETE])
    assert rep["success"], rep
    assert (await ws("presets/creer", nom="Soirée"))["error"]["code"] == "existe_deja"
    assert [p["nom"] for p in (await ws("presets"))["result"]] == ["Soirée"]
    exporte = (await ws("presets/obtenir", nom="Soirée"))["result"]

    rep = await ws("presets/importer", nom="Copie", entrees=exporte["entrees"])
    assert rep["success"]
    assert (await ws("presets/importer", nom="Copie", entrees=[]))["error"]["code"] == "existe_deja"

    faux_client.valeurs["picture"]["sharpness"] = 1
    await hass.config_entries.async_entries("lg_webos_tv")[0].runtime_data.televiseur \
        .lire("picture", ["sharpness"])
    rep = await ws("presets/appliquer", nom="Copie")
    assert [e["cle"] for e in rep["result"]["appliques"]] == ["sharpness"]
    assert faux_client.valeurs["picture"]["sharpness"] == 10

    assert (await ws("presets/supprimer", nom="Copie"))["success"]
    assert (await ws("presets/supprimer", nom="Copie"))["error"]["code"] == "introuvable"
    assert (await ws("presets/obtenir", nom="Copie"))["error"]["code"] == "introuvable"
    assert (await ws("presets/appliquer", nom="Copie"))["error"]["code"] == "introuvable"


async def test_abonnement_temps_reel(ws, faux_client, installe):
    abonnes = installe.runtime_data.televiseur._abonnes
    avant = len(abonnes)
    rep = await ws("abonner")
    assert rep["success"]
    instantane = await ws.client.receive_json()
    assert instantane["event"]["type"] == "instantane"
    assert instantane["event"]["reglages"]["picture"]["backlight"] == 80

    await faux_client.notifier("picture", {"backlight": "60"})
    evenement = await ws.client.receive_json()
    assert evenement["event"] == {"type": "changement", "categorie": "picture",
                                  "reglages": {"backlight": 60}, "origine": "manuel"}

    # Désabonnement : le relais est retiré des abonnés du téléviseur.
    assert len(abonnes) == avant + 1
    await ws.client.send_json({"id": next(ws.compteur), "type": "unsubscribe_events",
                               "subscription": rep["id"]})
    assert (await ws.client.receive_json())["success"]
    assert len(abonnes) == avant


async def test_abonnement_signale_historique_et_presets(ws, faux_client, installe):
    donnees = installe.runtime_data
    avant = (len(donnees.historique._ecouteurs), len(donnees.presets._ecouteurs))
    rep = await ws("abonner")
    await ws.client.receive_json()  # instantané

    await ws.client.send_json({"id": next(ws.compteur), "type": "lg_webos_tv/presets/creer",
                               "nom": "Soirée", "entrees": [ID_NETTETE]})
    recus = [await ws.client.receive_json() for _ in range(2)]
    assert {"type": "presets"} in [r.get("event") for r in recus]

    await ws.client.send_json({"id": next(ws.compteur), "type": "lg_webos_tv/ecrire",
                               "entree_id": ID_NETTETE, "valeur": 25})
    evenements = []
    while True:
        message = await ws.client.receive_json()
        if message.get("type") == "result":
            break
        evenements.append(message["event"])
    assert {"type": "historique"} in evenements

    await ws.client.send_json({"id": next(ws.compteur), "type": "unsubscribe_events",
                               "subscription": rep["id"]})
    while (await ws.client.receive_json()).get("type") != "result":
        pass
    assert (len(donnees.historique._ecouteurs), len(donnees.presets._ecouteurs)) == avant


async def test_reserve_aux_administrateurs(hass: HomeAssistant, installe, hass_ws_client,
                                           hass_read_only_access_token):
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json({"id": 1, "type": "lg_webos_tv/reglages"})
    rep = await client.receive_json()
    assert rep["error"]["code"] == "unauthorized"


async def test_panneau_enregistre_seulement_avec_le_frontend(hass: HomeAssistant):
    with patch.object(panneau.panel_custom, "async_register_panel", AsyncMock()) as enreg:
        await panneau.async_enregistrer(hass)
        enreg.assert_not_called()

        hass.config.components.add("frontend")
        hass.http = AsyncMock()
        await panneau.async_enregistrer(hass)
        await panneau.async_enregistrer(hass)  # rechargement de l'entrée
    assert hass.http.async_register_static_paths.await_count == 1
    options = enreg.await_args.kwargs
    assert options["embed_iframe"] is True and options["require_admin"] is True
    assert options["module_url"].startswith("/lg_webos_tv_panneau/panneau.js?v=")
    # Bundle construit et commité avec l'intégration (npm run build).
    assert (panneau.DOSSIER / "panneau.js").is_file()
