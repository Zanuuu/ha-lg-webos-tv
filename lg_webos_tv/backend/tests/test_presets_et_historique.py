import time

from starlette.testclient import TestClient

ID_NETTETE = "image.parametres-avances.clarte.ajuster-nettete"
ID_CONTRASTE = "image.parametres-avances.luminosite.ajuster-le-contraste"
ID_MODE = "image.mode-selection"
ID_EARC = "son.parametres-avances.compatibilite-earc"


# --------------------------------------------------------------- historique

def test_annuler_ecriture(application):
    with TestClient(application) as client:
        client.post(f"/api/reglages/{ID_NETTETE}", json={"valeur": 25})
        id_ecriture = client.get("/api/historique").json()[0]["id"]

        resultat = client.post(f"/api/historique/{id_ecriture}/annuler").json()
        assert resultat["ok"] is True
        assert resultat["nouvelle"] == 10

        histo = client.get("/api/historique").json()
        assert len(histo) == 2
        assert histo[0]["ancienne"] == 25 and histo[0]["nouvelle"] == 10


def test_annuler_refuse_si_mode_image_different(application, faux_client):
    with TestClient(application) as client:
        client.post(f"/api/reglages/{ID_NETTETE}", json={"valeur": 25})
        id_ecriture = client.get("/api/historique").json()[0]["id"]

        # Le mode d'image change entre-temps (ex. via la télécommande).
        client.app.state.televiseur.etat["picture"]["pictureMode"] = "expert1"

        resultat = client.post(f"/api/historique/{id_ecriture}/annuler").json()
        assert resultat["ok"] is False
        assert "expert2" in resultat["raison"] and "expert1" in resultat["raison"]
        # La valeur n'a pas bougé.
        assert faux_client.valeurs["picture"]["sharpness"] == 25


def test_annuler_entree_inconnue(application):
    with TestClient(application) as client:
        assert client.post("/api/historique/999/annuler").status_code == 404


def test_revenir_a_un_instant(application):
    with TestClient(application) as client:
        repere = time.time()
        client.post(f"/api/reglages/{ID_NETTETE}", json={"valeur": 20})
        client.post(f"/api/reglages/{ID_CONTRASTE}", json={"valeur": 90})
        client.post(f"/api/reglages/{ID_NETTETE}", json={"valeur": 30})

        resultat = client.post("/api/historique/revenir", json={"horodatage": repere}).json()
        assert len(resultat["resultats"]) == 3
        assert all(r["ok"] for r in resultat["resultats"])

        reglages = client.get("/api/reglages").json()["reglages"]["picture"]
        assert reglages["sharpness"] == 10
        assert reglages["contrast"] == 100


# ------------------------------------------------------------------ presets

def test_creer_lister_obtenir_preset(application):
    with TestClient(application) as client:
        reponse = client.post("/api/presets", json={"nom": "mon-preset"})
        assert reponse.status_code == 200, reponse.text
        cree = reponse.json()
        assert cree["nom"] == "mon-preset"
        ids = {e["entree_id"] for e in cree["entrees"]}
        assert ID_NETTETE in ids and ID_EARC in ids

        # Les réglages d'image portent le mode capturé, les autres non.
        par_id = {e["entree_id"]: e for e in cree["entrees"]}
        assert par_id[ID_NETTETE]["mode_image"] == "expert2"
        assert par_id[ID_EARC]["mode_image"] is None

        liste = client.get("/api/presets").json()
        assert liste == [{"nom": "mon-preset", "cree_le": cree["cree_le"],
                          "nombre_reglages": len(cree["entrees"])}]

        obtenu = client.get("/api/presets/mon-preset").json()
        assert obtenu == cree


def test_creer_preset_nom_existant_refuse(application):
    with TestClient(application) as client:
        client.post("/api/presets", json={"nom": "double"})
        reponse = client.post("/api/presets", json={"nom": "double"})
        assert reponse.status_code == 409


def test_preset_sous_ensemble_choisi(application):
    with TestClient(application) as client:
        cree = client.post("/api/presets", json={
            "nom": "partiel", "entrees": [ID_NETTETE],
        }).json()
        assert [e["entree_id"] for e in cree["entrees"]] == [ID_NETTETE]


def test_supprimer_preset(application):
    with TestClient(application) as client:
        client.post("/api/presets", json={"nom": "a-supprimer"})
        assert client.delete("/api/presets/a-supprimer").status_code == 200
        assert client.get("/api/presets/a-supprimer").status_code == 404
        assert client.delete("/api/presets/a-supprimer").status_code == 404


def test_preset_inconnu_404(application):
    with TestClient(application) as client:
        assert client.get("/api/presets/inconnu").status_code == 404
        assert client.post("/api/presets/inconnu/appliquer").status_code == 404


def test_importer_preset(application):
    with TestClient(application) as client:
        donnees = {
            "nom": "importe",
            "entrees": [{
                "entree_id": ID_NETTETE, "categorie": "picture", "cle": "sharpness",
                "valeur": 15, "mode_image": "expert2",
            }],
        }
        reponse = client.post("/api/presets/import", json=donnees)
        assert reponse.status_code == 200
        assert client.get("/api/presets/importe").json()["entrees"] == donnees["entrees"]

        # Sans `remplacer`, un second import du même nom est refusé.
        assert client.post("/api/presets/import", json=donnees).status_code == 409
        donnees["remplacer"] = True
        assert client.post("/api/presets/import", json=donnees).status_code == 200


def test_appliquer_preset_complet_bascule_le_mode_si_necessaire(application, faux_client):
    with TestClient(application) as client:
        # Capture en mode expert2 (sharpness=10, pictureMode inclus).
        client.post("/api/presets", json={"nom": "expert2-tel-quel"})

        # On passe en expert1 et on modifie sharpness dans ce mode.
        faux_client.valeurs["picture"]["pictureMode"] = "expert1"
        faux_client.valeurs["picture"]["sharpness"] = 5
        # Resynchronise le cache serveur comme le ferait une notification TV.
        client.app.state.televiseur.etat["picture"].update(
            {"pictureMode": "expert1", "sharpness": 5})

        resultat = client.post("/api/presets/expert2-tel-quel/appliquer").json()
        assert resultat["echecs"] == []
        cles_appliquees = {e["cle"] for e in resultat["appliques"]}
        assert {"pictureMode", "sharpness"} <= cles_appliquees

        reglages = client.get("/api/reglages").json()
        assert reglages["mode_image"] == "expert2"
        assert reglages["reglages"]["picture"]["sharpness"] == 10


def test_ecriture_refusee_par_le_televiseur_renvoie_400(application, faux_client):
    faux_client.refuser.add(("picture", "sharpness"))
    with TestClient(application) as client:
        reponse = client.post(f"/api/reglages/{ID_NETTETE}", json={"valeur": 12})
        assert reponse.status_code == 400
        assert "refusée par le téléviseur" in reponse.json()["detail"]
        assert client.get("/api/historique").json() == []


def test_preset_avec_une_entree_refusee_continue_et_la_reporte_en_echec(application, faux_client):
    with TestClient(application) as client:
        client.post("/api/presets", json={
            "nom": "avec-refus", "entrees": [ID_NETTETE, ID_CONTRASTE],
        })
        faux_client.refuser.add(("picture", "sharpness"))
        # Les deux valeurs diffèrent des valeurs capturées, sinon l'écriture
        # n'a rien à changer d'observable.
        client.app.state.televiseur.etat["picture"]["sharpness"] = 1
        faux_client.valeurs["picture"]["sharpness"] = 1
        client.app.state.televiseur.etat["picture"]["contrast"] = 1
        faux_client.valeurs["picture"]["contrast"] = 1

        resultat = client.post("/api/presets/avec-refus/appliquer").json()
        assert [e["cle"] for e in resultat["appliques"]] == ["contrast"]
        assert len(resultat["echecs"]) == 1
        assert resultat["echecs"][0]["cle"] == "sharpness"
        assert "refusée par le téléviseur" in resultat["echecs"][0]["raison"]
        # L'écriture non refusée a bien été appliquée malgré l'échec de l'autre.
        assert faux_client.valeurs["picture"]["contrast"] == 100


def test_appliquer_preset_partiel_echoue_si_mode_different(application, faux_client):
    with TestClient(application) as client:
        # Preset partiel : ne capture pas pictureMode, seulement la netteté.
        client.post("/api/presets", json={"nom": "nettete-seule", "entrees": [ID_NETTETE]})

        faux_client.valeurs["picture"]["pictureMode"] = "expert1"
        client.app.state.televiseur.etat["picture"]["pictureMode"] = "expert1"

        resultat = client.post("/api/presets/nettete-seule/appliquer").json()
        assert resultat["appliques"] == []
        assert len(resultat["echecs"]) == 1
        assert "expert2" in resultat["echecs"][0]["raison"]

        # En revenant au bon mode, l'application réussit.
        faux_client.valeurs["picture"]["pictureMode"] = "expert2"
        client.app.state.televiseur.etat["picture"]["pictureMode"] = "expert2"
        resultat = client.post("/api/presets/nettete-seule/appliquer").json()
        assert len(resultat["appliques"]) == 1
        assert resultat["echecs"] == []
