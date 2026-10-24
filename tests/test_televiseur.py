import asyncio

import pytest
from bscpylgtv.exceptions import PyLGTVCmdError

from .conftest import attendre


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
        "origine": "manuel",
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


async def test_cle_refusee_demande_un_nouvel_appairage(televiseur, faux_client):
    """Après une mise à jour du firmware, le téléviseur refuse l'ancienne clé
    (401 not registered) sans que bscpylgtv ne lève d'erreur : la boucle
    s'arrête sur « appairage_requis » (réauthentification côté HA) au lieu
    de réessayer en boucle."""
    faux_client.non_enregistre = True
    etats = []

    async def espion(evt):
        if evt["type"] == "connexion":
            etats.append(evt["etat"])

    televiseur.abonner(espion)
    await televiseur.demarrer()
    assert await attendre(lambda: televiseur._tache.done())
    assert etats[-1] == "appairage_requis"
    assert "connecte" not in etats
    await televiseur.arreter()


async def test_tous_les_abonnements_en_echec_nannonce_pas_connecte(faux_client):
    """Si aucun abonnement n'aboutit, le service ne doit pas se déclarer
    connecté avec un état vide."""
    from custom_components.lg_webos_tv.televiseur import Televiseur

    async def abonnement_refuse(rappel, uri, payload):
        raise RuntimeError("refusé")

    faux_client.subscribe = abonnement_refuse

    async def fabrique():
        return faux_client

    televiseur = Televiseur(hote="test", client_key="cle", fabrique_client=fabrique)
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
    """Ni setSystemSettings ni alertes accordés : lecture seule."""
    from custom_components.lg_webos_tv.televiseur import EcritureImpossible

    faux_client.permission_ecriture = False
    faux_client.permission_alerte = False
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


async def test_ecriture_par_alerte_sous_webos_11(televiseur, faux_client):
    """webOS 11 : setSystemSettings refusé, écriture par le pont createAlert."""
    faux_client.permission_ecriture = False
    await televiseur.demarrer()
    assert await attendre(lambda: televiseur.etat_connexion == "connecte")
    assert televiseur.instantane()["ecriture_possible"] is True
    assert televiseur.voie_ecriture == "alerte"
    resultat = await televiseur.ecrire("picture", "sharpness", 25)
    assert resultat == {
        "ancienne": 10, "nouvelle": 25, "confirme": True, "mode_image": "expert2",
    }
    assert faux_client.appels_luna == [
        ("com.webos.settingsservice/setSystemSettings",
         {"category": "picture", "settings": {"sharpness": 25}}),
    ]
    await televiseur.arreter()


async def test_valeur_ignoree_par_alerte_non_confirmee(televiseur, faux_client):
    """Le pont est muet : une valeur refusée n'apparaît pas à la relecture."""
    faux_client.permission_ecriture = False
    faux_client.refuser.add(("picture", "contrast"))
    await televiseur.demarrer()
    assert await attendre(lambda: televiseur.etat_connexion == "connecte")
    resultat = await televiseur.ecrire("picture", "contrast", 999)
    assert resultat["confirme"] is False
    assert resultat["nouvelle"] == 100
    await televiseur.arreter()


async def test_sonde_ecriture_sans_effet_quand_permise(televiseur, faux_client):
    await televiseur.demarrer()
    assert await attendre(lambda: televiseur.etat_connexion == "connecte")
    assert televiseur.instantane()["ecriture_possible"] is True
    assert "sondePermissionEcriture" not in faux_client.valeurs["picture"]
    await televiseur.arreter()


# ------------------------------------------------------------- appairage

class ClientAppairage:
    """Client bscpylgtv minimal pour `appairer`."""

    def __init__(self, cle="nouvelle-cle", non_enregistre=False, connexion=None):
        self.client_key = None
        self._cle = cle
        self.non_enregistre = non_enregistre
        self._connexion = connexion
        self.deconnecte = False

    async def connect(self):
        if self._connexion is not None:
            raise self._connexion
        self.client_key = self._cle

    async def request(self, uri, payload=None):
        if self.non_enregistre:
            raise PyLGTVCmdError({"error": "401 insufficient permissions (not registered)"})
        return {"settings": {"pictureMode": "vivid"}}

    async def disconnect(self):
        self.deconnecte = True


async def test_appairer_renvoie_la_cle(monkeypatch):
    import custom_components.lg_webos_tv.televiseur as module

    client = ClientAppairage()

    async def construire(hote, **options):
        assert "storage" in options  # aucun stockage sur disque
        return client

    monkeypatch.setattr(module, "_construire_client", construire)
    assert await module.appairer("test") == "nouvelle-cle"
    assert client.deconnecte


@pytest.mark.parametrize("client", [
    ClientAppairage(cle=None),
    ClientAppairage(non_enregistre=True),
    ClientAppairage(connexion=OSError("injoignable")),
])
async def test_appairer_echec(monkeypatch, client):
    import custom_components.lg_webos_tv.televiseur as module

    async def construire(hote, **options):
        return client

    monkeypatch.setattr(module, "_construire_client", construire)
    with pytest.raises(module.AppairageEchoue):
        await module.appairer("test")
    assert client.deconnecte


async def test_ecriture_par_alerte_confirmee_par_la_notification(televiseur, faux_client):
    """La notification (≈ 0,1 s sur le vrai téléviseur) confirme sans
    relecture, y compris quand elle porte la valeur en chaîne."""
    faux_client.permission_ecriture = False
    await televiseur.demarrer()
    assert await attendre(lambda: televiseur.etat_connexion == "connecte")
    televiseur.delai_notification = 5.0  # la relecture ne doit pas servir

    luna_origine = faux_client.luna_request

    async def luna_notifie_en_chaine(uri, params):
        await luna_origine(uri, {**params, "settings": {
            cle: str(v) for cle, v in params["settings"].items()}})

    faux_client.luna_request = luna_notifie_en_chaine
    lectures = []
    requete_origine = faux_client.request

    async def espion(uri, payload=None):
        lectures.append(uri)
        return await requete_origine(uri, payload)

    faux_client.request = espion
    resultat = await asyncio.wait_for(televiseur.ecrire("picture", "sharpness", 25), 1.0)
    assert resultat["confirme"] is True
    assert resultat["nouvelle"] == 25
    assert lectures == []
    assert televiseur._attentes == {}
    await televiseur.arreter()


# ------------------------------------------------------- origine des changements

async def origines_pendant(televiseur, action):
    evenements = []

    async def espion(evt):
        if evt["type"] == "changement":
            evenements.append((evt["origine"], dict(evt["reglages"])))

    televiseur.abonner(espion)
    await action()
    televiseur.desabonner(espion)
    return evenements


@pytest.mark.parametrize("voie_alerte", [False, True])
async def test_nos_ecritures_sont_reconnues(televiseur, faux_client, voie_alerte):
    faux_client.permission_ecriture = not voie_alerte
    await televiseur.demarrer()
    assert await attendre(lambda: televiseur.etat_connexion == "connecte")
    evenements = await origines_pendant(
        televiseur, lambda: televiseur.ecrire("picture", "sharpness", 25))
    assert evenements == [("application", {"sharpness": 25})]
    await televiseur.arreter()


async def test_telecommande_reglages_rapides_et_cascade(televiseur, faux_client):
    await televiseur.demarrer()
    assert await attendre(lambda: televiseur.etat_connexion == "connecte")

    async def scenario():
        await faux_client.notifier("picture", {"backlight": "60"})
        await faux_client.notifier("picture", {"pictureMode": "cinema"},
                                   caller="com.webos.app.quicksettings")
        await faux_client.notifier("picture", {"backlight": "40", "contrast": "85"},
                                   caller=None)
        await faux_client.notifier("picture", {"backlight": 41},
                                   caller="com.webos.app.starfish_flutter_systemui")

    evenements = await origines_pendant(televiseur, scenario)
    assert evenements == [
        ("manuel", {"backlight": 60}),
        ("manuel", {"pictureMode": "cinema"}),
        ("cascade", {"backlight": 40, "contrast": 85}),
        # Pont d'alerte d'un autre client que nous.
        ("autre_application", {"backlight": 41}),
    ]
    await televiseur.arreter()


async def test_notification_tardive_de_notre_ecriture(televiseur, faux_client):
    """Une écriture non confirmée à temps, appliquée plus tard par le
    téléviseur, reste reconnue comme nôtre (et non comme une autre
    application) quand sa notification arrive enfin."""
    faux_client.permission_ecriture = False
    faux_client.refuser.add(("picture", "sharpness"))  # rien n'arrive à temps
    await televiseur.demarrer()
    assert await attendre(lambda: televiseur.etat_connexion == "connecte")
    resultat = await televiseur.ecrire("picture", "sharpness", 25)
    assert resultat["confirme"] is False
    evenements = await origines_pendant(televiseur, lambda: faux_client.notifier(
        "picture", {"sharpness": "25"}, caller="com.webos.app.starfish_flutter_systemui"))
    assert evenements == [("application", {"sharpness": 25})]
    await televiseur.arreter()


async def test_stockage_de_cle_accepte_par_bscpylgtv():
    """bscpylgtv vérifie le stockage fourni par isinstance(StorageProto) :
    construit avec le vrai client (sans connexion), il doit être accepté."""
    from custom_components.lg_webos_tv.televiseur import (_CleEnMemoire,
                                                          _construire_client)

    stockage = _CleEnMemoire()
    client = await _construire_client("192.0.2.10", storage=stockage)
    assert client.storage is stockage
    assert client.client_key is None
