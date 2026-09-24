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


async def test_cle_refusee_force_un_nouvel_appairage(faux_client):
    """Après une mise à jour du firmware, le téléviseur refuse l'ancienne clé
    (401 not registered) sans que bscpylgtv ne lève d'erreur : le service
    doit le détecter et relancer un appairage (demande sur l'écran)."""
    from app.televiseur import Televiseur

    appels = []

    async def fabrique(forcer_appairage=False):
        appels.append(forcer_appairage)
        # La demande d'appairage acceptée rend une clé valide.
        faux_client.non_enregistre = not forcer_appairage
        return faux_client

    televiseur = Televiseur(hote="test", fabrique_client=fabrique)
    televiseur.delai_appairage = 0
    etats = []

    async def espion(evt):
        if evt["type"] == "connexion":
            etats.append(evt["etat"])

    televiseur.abonner(espion)
    await televiseur.demarrer()
    assert await attendre(lambda: televiseur.etat_connexion == "connecte")
    assert appels == [False, True]
    assert "appairage" in etats
    assert televiseur.mode_image == "expert2"
    await televiseur.arreter()


async def test_tous_les_abonnements_en_echec_nannonce_pas_connecte(faux_client):
    """Si aucun abonnement n'aboutit, le service ne doit pas se déclarer
    connecté avec un état vide."""
    from app.televiseur import Televiseur

    async def abonnement_refuse(rappel, uri, payload):
        raise RuntimeError("refusé")

    faux_client.subscribe = abonnement_refuse

    async def fabrique(forcer_appairage=False):
        return faux_client

    televiseur = Televiseur(hote="test", fabrique_client=fabrique)
    etats = []

    async def espion(evt):
        if evt["type"] == "connexion":
            etats.append(evt["etat"])

    televiseur.abonner(espion)
    await televiseur.demarrer()
    await attendre(lambda: "deconnecte" in etats, delai=1.0)
    assert "connecte" not in etats
    await televiseur.arreter()


async def test_permission_ecriture_refusee_passe_en_consultation(televiseur, faux_client):
    """webOS 11 : lecture accordée, écriture refusée au manifeste non signé."""
    from app.televiseur import EcritureImpossible

    faux_client.permission_ecriture = False
    evenements = []

    async def espion(evt):
        evenements.append(evt)

    televiseur.abonner(espion)
    await televiseur.demarrer()
    assert await attendre(lambda: televiseur.etat_connexion == "connecte")
    assert televiseur.instantane()["ecriture_possible"] is False
    assert {"type": "ecriture", "possible": False} in evenements
    assert televiseur.mode_image == "expert2"
    try:
        await televiseur.ecrire("picture", "sharpness", 25)
        raise AssertionError("écriture acceptée en mode consultation")
    except EcritureImpossible:
        pass
    assert faux_client.valeurs["picture"]["sharpness"] == 10
    await televiseur.arreter()


async def test_sonde_ecriture_sans_effet_quand_permise(televiseur, faux_client):
    await televiseur.demarrer()
    assert await attendre(lambda: televiseur.etat_connexion == "connecte")
    assert televiseur.instantane()["ecriture_possible"] is True
    assert "sondePermissionEcriture" not in faux_client.valeurs["picture"]
    await televiseur.arreter()


async def test_etat_appairage_pendant_la_demande_sans_cle(monkeypatch):
    """Sans clé stockée, connect() attend l'acceptation sur l'écran de la TV :
    l'état doit déjà être « appairage » pendant cette attente."""
    import app.televiseur as module

    etats_pendant_connect = []

    class ClientSansCle:
        client_key = None

        @classmethod
        async def create(cls, *args, **kwargs):
            return cls()

        async def connect(self):
            etats_pendant_connect.append(televiseur.etat_connexion)

    monkeypatch.setattr(module, "WebOsClient", ClientSansCle)
    televiseur = module.Televiseur(hote="test")
    await televiseur._creer_client()
    assert etats_pendant_connect == ["appairage"]


async def test_etat_inchange_avec_cle_stockee(monkeypatch):
    import app.televiseur as module

    etats_pendant_connect = []

    class ClientAvecCle:
        client_key = "cle"

        @classmethod
        async def create(cls, *args, **kwargs):
            return cls()

        async def connect(self):
            etats_pendant_connect.append(televiseur.etat_connexion)

    monkeypatch.setattr(module, "WebOsClient", ClientAvecCle)
    televiseur = module.Televiseur(hote="test")
    await televiseur._changer_etat("connexion")
    await televiseur._creer_client()
    assert etats_pendant_connect == ["connexion"]
