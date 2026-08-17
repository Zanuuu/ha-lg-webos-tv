from conftest import attendre


async def test_connexion_et_instantane(televiseur):
    await televiseur.demarrer()
    assert await attendre(lambda: televiseur.etat_connexion == "connecte")
    assert televiseur.mode_image == "expert2"
    assert televiseur.etat["picture"]["sharpness"] == 10
    await televiseur.arreter()
    assert televiseur.etat_connexion == "deconnecte"


async def test_notification_normalise_les_types(televiseur, faux_client):
    await televiseur.demarrer()
    await attendre(lambda: televiseur.etat_connexion == "connecte")

    evenements = []

    async def espion(evt):
        evenements.append(evt)

    televiseur.abonner(espion)
    # Le vrai téléviseur notifie les nombres en chaînes.
    await faux_client.notifier("picture", {"contrast": "85", "pictureMode": "expert1"})
    assert televiseur.etat["picture"]["contrast"] == 85
    assert televiseur.mode_image == "expert1"
    changements = [e for e in evenements if e["type"] == "changement"]
    assert changements == [{
        "type": "changement", "categorie": "picture",
        "reglages": {"contrast": 85, "pictureMode": "expert1"},
    }]
    await televiseur.arreter()


async def test_ecriture_avec_relecture(televiseur):
    await televiseur.demarrer()
    await attendre(lambda: televiseur.etat_connexion == "connecte")
    resultat = await televiseur.ecrire("picture", "sharpness", 25)
    assert resultat == {
        "ancienne": 10, "nouvelle": 25, "confirme": True, "mode_image": "expert2",
    }
    await televiseur.arreter()
