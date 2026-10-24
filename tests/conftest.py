"""Fixtures communes : téléviseur simulé, activation de l'intégration."""

import asyncio

import pytest
from bscpylgtv.exceptions import PyLGTVCmdError

from custom_components.lg_webos_tv.historique import Historique
from custom_components.lg_webos_tv.presets import Presets
from custom_components.lg_webos_tv.televiseur import (CLE_SONDE_ECRITURE,
                                                      Televiseur)

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


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
        # Écritures que le téléviseur doit refuser, ex. {("picture", "gamma")}
        # — simule une valeur hors plage ou une clé non acceptée.
        self.refuser: set[tuple[str, str]] = set()
        # Clé client refusée par le téléviseur (ex. après une mise à jour du
        # firmware) : toute requête répond 401, comme le vrai.
        self.non_enregistre = False
        # webOS 11 : WRITE_SETTINGS refusée aux manifestes non signés.
        self.permission_ecriture = True
        # Pont createAlert (WRITE_NOTIFICATION_TOAST, accordée sans signature).
        self.permission_alerte = True
        self.appels_luna = []

    def _verifier_enregistrement(self, ident):
        if self.non_enregistre:
            raise PyLGTVCmdError({
                "type": "error", "id": ident, "payload": {},
                "error": "401 insufficient permissions (not registered)"})

    async def subscribe(self, rappel, uri, payload):
        self._verifier_enregistrement(len(self.rappels))
        categorie = payload["category"]
        if categorie not in self.valeurs:
            raise RuntimeError(f"catégorie {categorie} non simulée")
        self.rappels[categorie] = rappel
        return {"settings": dict(self.valeurs[categorie]), "subscribed": True}

    async def request(self, uri, payload=None):
        self._verifier_enregistrement(0)
        if uri == "com.webos.service.update/getCurrentSWInformation":
            return {"returnValue": True, "product_name": "webOSTV 11.2.0",
                    "major_ver": "43", "minor_ver": "21.77"}
        categorie = payload.get("category")
        if uri == "settings/getSystemSettings":
            valeurs = self.valeurs.get(categorie, {})
            return {"settings": {k: valeurs[k] for k in payload["keys"] if k in valeurs}}
        if uri == "settings/setSystemSettings":
            if not self.permission_ecriture:
                raise PyLGTVCmdError({"type": "error", "id": 0, "payload": {},
                                      "error": "401 insufficient permissions"})
            for cle in payload["settings"]:
                if cle == CLE_SONDE_ECRITURE:
                    # Comme l'adaptateur du firmware : clé hors liste rejetée
                    # avant toute écriture.
                    raise PyLGTVCmdError({"payload": {"errorText":
                        f"Some keys are not allowed for the request. ( {cle} )"}})
                if (categorie, cle) in self.refuser:
                    raise PyLGTVCmdError({
                        "payload": {"errorText": f"Out of range: {cle}"}})
            self.valeurs.setdefault(categorie, {}).update(payload["settings"])
            # Comme le vrai téléviseur : l'écriture déclenche la notification
            # d'abonnement (valeurs telles qu'écrites).
            rappel = self.rappels.get(categorie)
            if rappel is not None:
                await rappel({"settings": dict(payload["settings"]),
                              "returnValue": True})
            return {"returnValue": True}
        if uri == "system.notifications/closeAlert":
            self._verifier_alerte()
            # Comme le firmware pour un identifiant d'alerte inconnu.
            raise PyLGTVCmdError({"error": "500 Application error",
                                  "payload": {"errorText": "Alert Id parse error"}})
        raise RuntimeError(f"uri non simulée : {uri}")

    def _verifier_alerte(self):
        if not self.permission_alerte:
            raise PyLGTVCmdError({"type": "error", "id": 0, "payload": {},
                                  "error": "401 insufficient permissions"})

    async def luna_request(self, uri, params):
        """Pont createAlert : muet, une valeur refusée est ignorée."""
        self._verifier_alerte()
        self.appels_luna.append((uri, params))
        categorie = params["category"]
        if any((categorie, cle) in self.refuser for cle in params["settings"]):
            return {"returnValue": True}
        self.valeurs.setdefault(categorie, {}).update(params["settings"])
        rappel = self.rappels.get(categorie)
        if rappel is not None:
            await rappel({"settings": dict(params["settings"]), "returnValue": True})
        return {"returnValue": True}

    async def connect(self):
        pass

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
    return Televiseur(hote="test", client_key="cle", fabrique_client=fabrique)


@pytest.fixture
def historique(tmp_path):
    return Historique(tmp_path / "historique.sqlite")


@pytest.fixture
def presets(tmp_path):
    return Presets(tmp_path / "presets.sqlite")


async def attendre(condition, delai=2.0):
    """Attend qu'une condition devienne vraie (boucle de test)."""
    for _ in range(int(delai / 0.01)):
        if condition():
            return True
        await asyncio.sleep(0.01)
    return condition()
