import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import arbre, config, restauration
from .historique import Historique
from .presets import PresetExistant, PresetInconnu, Presets, capturer_snapshot
from .televiseur import Televiseur

log = logging.getLogger(__name__)

# Build du frontend (frontend/dist), servi par le même processus en production.
# En développement, le frontend tourne à part via `npm run dev`.
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


class Ecriture(BaseModel):
    valeur: Any


class EcritureBrute(BaseModel):
    categorie: str
    cle: str
    valeur: Any


class CreerPreset(BaseModel):
    nom: str
    entrees: list[str] | None = None  # sous-ensemble d'ids ; None = tout ce qui est pilotable


class ImporterPreset(BaseModel):
    nom: str
    entrees: list[dict[str, Any]]
    remplacer: bool = False


class RevenirA(BaseModel):
    horodatage: float


class FiltreIngress:
    """En mode app Home Assistant, seule l'IP du proxy Ingress du Superviseur
    est acceptée (contrainte de sécurité des apps avec ingress), sauf si
    l'utilisateur a explicitement ouvert l'accès direct (option acces_lan).

    Middleware ASGI pur : un middleware HTTP FastAPI ne couvrirait pas le
    WebSocket. La configuration est relue à chaque requête pour rester
    surchargeable par les tests.
    """

    AUTORISES_LOCAUX = ("127.0.0.1", "::1")

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] in ("http", "websocket")
                and config.MODE_APP_HA and not config.ACCES_LAN):
            client = scope.get("client")
            hote = client[0] if client else ""
            if hote != config.INGRESS_PROXY_IP and hote not in self.AUTORISES_LOCAUX:
                if scope["type"] == "http":
                    reponse = JSONResponse(
                        {"detail": "Accès réservé à l'Ingress Home Assistant"},
                        status_code=403)
                    await reponse(scope, receive, send)
                else:
                    await send({"type": "websocket.close", "code": 4403})
                return
        await self.app(scope, receive, send)


def creer_app(televiseur: Televiseur | None = None,
              historique: Historique | None = None,
              presets: Presets | None = None) -> FastAPI:
    @asynccontextmanager
    async def cycle_de_vie(app: FastAPI):
        app.state.televiseur = televiseur or Televiseur()
        app.state.historique = historique or Historique()
        app.state.presets = presets or Presets()
        await app.state.televiseur.demarrer()
        try:
            yield
        finally:
            await app.state.televiseur.arreter()

    app = FastAPI(title="Réglages LG OLED 65 G5", lifespan=cycle_de_vie)
    app.add_middleware(FiltreIngress)

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/etat")
    async def etat() -> dict:
        tv: Televiseur = app.state.televiseur
        return {"connexion": tv.etat_connexion, "mode_image": tv.mode_image}

    @app.get("/api/arbre")
    async def arbre_menus() -> dict:
        return arbre.charger()

    @app.get("/api/reglages")
    async def reglages() -> dict:
        tv: Televiseur = app.state.televiseur
        return tv.instantane()

    def _lever_si_echec_ecriture(resultat: dict) -> None:
        if resultat["ok"]:
            return
        raison = resultat.get("raison", "")
        if raison == "téléviseur injoignable":
            raise HTTPException(503, raison)
        if raison.startswith("refusée par le téléviseur"):
            raise HTTPException(400, raison)

    @app.post("/api/reglages/{entree_id}")
    async def ecrire_reglage(entree_id: str, corps: Ecriture) -> dict:
        try:
            resultat = await restauration.ecrire_par_entree(
                app.state.televiseur, app.state.historique, entree_id, corps.valeur)
        except arbre.EntreeInconnue:
            raise HTTPException(404, f"Entrée inconnue : {entree_id}")
        except arbre.EntreeNonPilotable:
            raise HTTPException(400, f"Entrée non pilotable par l'API : {entree_id}")
        except arbre.ValeurInvalide as exc:
            raise HTTPException(400, f"Valeur invalide : {exc}")
        _lever_si_echec_ecriture(resultat)
        return resultat

    @app.post("/api/reglages-bruts")
    async def ecrire_reglage_brut(corps: EcritureBrute) -> dict:
        # Accès direct catégorie/clé, sans validation par l'arbre : réservé
        # aux clés que l'arbre ne représente pas finement (tableaux de
        # balance des blancs, clés génériques).
        resultat = await restauration.ecrire(
            app.state.televiseur, app.state.historique, None,
            corps.categorie, corps.cle, corps.valeur)
        _lever_si_echec_ecriture(resultat)
        return resultat

    @app.get("/api/historique")
    async def lister_historique(limite: int = 100) -> list[dict]:
        return await app.state.historique.lister(limite)

    @app.post("/api/historique/{id_}/annuler")
    async def annuler_historique(id_: int) -> dict:
        resultat = await restauration.annuler_ecriture(
            app.state.televiseur, app.state.historique, id_)
        if not resultat["ok"] and resultat.get("raison") == "entrée d'historique introuvable":
            raise HTTPException(404, resultat["raison"])
        return resultat

    @app.post("/api/historique/revenir")
    async def revenir_historique(corps: RevenirA) -> dict:
        resultats = await restauration.revenir_a(
            app.state.televiseur, app.state.historique, corps.horodatage)
        return {"resultats": resultats}

    @app.get("/api/presets")
    async def lister_presets() -> list[dict]:
        return await app.state.presets.lister()

    @app.post("/api/presets")
    async def creer_preset(corps: CreerPreset) -> dict:
        tv: Televiseur = app.state.televiseur
        snapshot = capturer_snapshot(tv.etat, tv.mode_image, corps.entrees)
        if not snapshot:
            raise HTTPException(
                400, "Aucun réglage pilotable à capturer (sélection vide, ou "
                     "valeurs pas encore lues depuis le téléviseur)")
        try:
            return await app.state.presets.sauvegarder(corps.nom, snapshot)
        except PresetExistant:
            raise HTTPException(409, f"Un preset nommé « {corps.nom} » existe déjà")

    @app.get("/api/presets/{nom}")
    async def obtenir_preset(nom: str) -> dict:
        preset = await app.state.presets.recuperer(nom)
        if preset is None:
            raise HTTPException(404, f"Preset inconnu : {nom}")
        return preset

    @app.delete("/api/presets/{nom}")
    async def supprimer_preset(nom: str) -> dict:
        if not await app.state.presets.supprimer(nom):
            raise HTTPException(404, f"Preset inconnu : {nom}")
        return {"supprime": nom}

    @app.post("/api/presets/import")
    async def importer_preset(corps: ImporterPreset) -> dict:
        try:
            return await app.state.presets.sauvegarder(
                corps.nom, corps.entrees, remplacer=corps.remplacer)
        except PresetExistant:
            raise HTTPException(
                409, f"Un preset nommé « {corps.nom} » existe déjà (utilisez remplacer)")

    @app.post("/api/presets/{nom}/appliquer")
    async def appliquer_preset(nom: str) -> dict:
        try:
            return await restauration.appliquer_preset(
                app.state.televiseur, app.state.historique, app.state.presets, nom)
        except PresetInconnu:
            raise HTTPException(404, f"Preset inconnu : {nom}")

    @app.websocket("/api/ws")
    async def canal(ws: WebSocket) -> None:
        tv: Televiseur = app.state.televiseur
        await ws.accept()

        async def envoyer(evenement: dict) -> None:
            await ws.send_json(evenement)

        await ws.send_json({"type": "instantane", **tv.instantane()})
        tv.abonner(envoyer)
        try:
            while True:
                # Le canal est descendant ; on ne lit que pour détecter la
                # fermeture par le client.
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            tv.desabonner(envoyer)

    if FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"),
                  name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> FileResponse:
            # Application monopage : toute route inconnue renvoie index.html.
            candidate = FRONTEND_DIST / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = creer_app()
