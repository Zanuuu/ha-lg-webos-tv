import asyncio

import pytest

from app.historique import Historique
from app.main import creer_app
from app.televiseur import Televiseur


class FauxClient:
    """Simule le téléviseur : lectures/écritures getSystemSettings et
    notifications d'abonnement (avec nombres en chaînes, comme le vrai)."""

    def __init__(self):
        self.valeurs = {
            "picture": {
                "sharpness": 10, "contrast": 100, "backlight": 80,
                "pictureMode": "expert2", "energySaving": "off",
            },
            "sound": {"soundMode": "standard", "eArcSupport": "on"},
        }
        self.rappels = {}

    async def subscribe(self, rappel, uri, payload):
        categorie = payload["category"]
        if categorie not in self.valeurs:
            raise RuntimeError(f"catégorie {categorie} non simulée")
        self.rappels[categorie] = rappel
        return {"settings": dict(self.valeurs[categorie]), "subscribed": True}

    async def request(self, uri, payload):
        categorie = payload.get("category")
        if uri == "settings/getSystemSettings":
            valeurs = self.valeurs.get(categorie, {})
            return {"settings": {k: valeurs[k] for k in payload["keys"] if k in valeurs}}
        if uri == "settings/setSystemSettings":
            self.valeurs.setdefault(categorie, {}).update(payload["settings"])
            # Comme le vrai téléviseur : l'écriture déclenche la notification
            # d'abonnement (valeurs telles qu'écrites).
            rappel = self.rappels.get(categorie)
            if rappel is not None:
                await rappel({"settings": dict(payload["settings"]),
                              "returnValue": True})
            return {"returnValue": True}
        raise RuntimeError(f"uri non simulée : {uri}")

    async def disconnect(self):
        pass

    async def notifier(self, categorie, reglages):
        """Simule une notification (changement fait à la télécommande)."""
        self.valeurs.setdefault(categorie, {}).update(reglages)
        await self.rappels[categorie]({"settings": reglages, "returnValue": True})


@pytest.fixture
def faux_client():
    return FauxClient()


@pytest.fixture
def televiseur(faux_client):
    async def fabrique():
        return faux_client
    return Televiseur(hote="test", fabrique_client=fabrique)


@pytest.fixture
def historique(tmp_path):
    return Historique(tmp_path / "historique.sqlite")


@pytest.fixture
def application(televiseur, historique):
    return creer_app(televiseur=televiseur, historique=historique)


async def attendre(condition, delai=2.0):
    """Attend qu'une condition devienne vraie (boucle de test)."""
    for _ in range(int(delai / 0.01)):
        if condition():
            return True
        await asyncio.sleep(0.01)
    return condition()
