from starlette.testclient import TestClient

ID_NETTETE = "image.parametres-avances.clarte.ajuster-nettete"


def test_ecriture_par_entree_et_historique(application):
    with TestClient(application) as client:
        reponse = client.post(f"/api/reglages/{ID_NETTETE}", json={"valeur": 25})
        assert reponse.status_code == 200, reponse.text
        corps = reponse.json()
        assert corps["confirme"] is True
        assert corps["ancienne"] == 10
        assert corps["nouvelle"] == 25
        assert corps["mode_image"] == "expert2"

        histo = client.get("/api/historique").json()
        assert len(histo) == 1
        assert histo[0]["entree_id"] == ID_NETTETE
        assert histo[0]["cle"] == "sharpness"
        assert histo[0]["ancienne"] == 10
        assert histo[0]["nouvelle"] == 25
        assert histo[0]["mode_image"] == "expert2"


def test_ecriture_hors_bornes_refusee(application):
    with TestClient(application) as client:
        reponse = client.post(f"/api/reglages/{ID_NETTETE}", json={"valeur": 999})
        assert reponse.status_code == 400
        assert client.get("/api/historique").json() == []


def test_ecriture_entree_inconnue_ou_non_pilotable(application):
    with TestClient(application) as client:
        assert client.post("/api/reglages/nexiste.pas",
                           json={"valeur": 1}).status_code == 404
        # Entrée affichée « À régler sur la TV ».
        assert client.post("/api/reglages/image.assistant-image-personnalisee",
                           json={"valeur": 1}).status_code == 400


def test_ecriture_liste_valide_les_choix(application):
    with TestClient(application) as client:
        bonne = client.post("/api/reglages/general.economie-energie.fonction-economie-energie",
                            json={"valeur": "min"})
        assert bonne.status_code == 200
        mauvaise = client.post("/api/reglages/general.economie-energie.fonction-economie-energie",
                               json={"valeur": "turbo"})
        assert mauvaise.status_code == 400


def test_arbre_et_etat(application):
    with TestClient(application) as client:
        arbre = client.get("/api/arbre").json()
        assert [s["id"] for s in arbre["sections"]] == ["image", "son", "general", "assistance"]
        etat = client.get("/api/etat").json()
        assert etat["connexion"] == "connecte"
        assert etat["mode_image"] == "expert2"


def test_websocket_instantane_et_changement(application):
    with TestClient(application) as client:
        with client.websocket_connect("/api/ws") as ws:
            premier = ws.receive_json()
            assert premier["type"] == "instantane"
            assert premier["mode_image"] == "expert2"
            assert premier["reglages"]["picture"]["sharpness"] == 10

            client.post(f"/api/reglages/{ID_NETTETE}", json={"valeur": 30})
            changement = ws.receive_json()
            assert changement == {
                "type": "changement", "categorie": "picture",
                "reglages": {"sharpness": 30},
            }


def test_ecriture_en_mode_consultation_refusee_403(application, faux_client):
    faux_client.permission_ecriture = False
    with TestClient(application) as client:
        assert client.get("/api/reglages").json()["ecriture_possible"] is False
        reponse = client.post(f"/api/reglages/{ID_NETTETE}", json={"valeur": 25})
        assert reponse.status_code == 403
        assert "webOS 11" in reponse.json()["detail"]
        assert client.get("/api/historique").json() == []
