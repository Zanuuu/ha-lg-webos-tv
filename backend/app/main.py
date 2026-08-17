import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import arbre
from .historique import Historique
from .televiseur import ConnexionTvPerdue, Televiseur

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


def creer_app(televiseur: Televiseur | None = None,
              historique: Historique | None = None) -> FastAPI:
    @asynccontextmanager
    async def cycle_de_vie(app: FastAPI):
        app.state.televiseur = televiseur or Televiseur()
        app.state.historique = historique or Historique()
        await app.state.televiseur.demarrer()
        try:
            yield
        finally:
            await app.state.televiseur.arreter()

    app = FastAPI(title="Réglages LG OLED 65 G5", lifespan=cycle_de_vie)

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

    async def _ecrire(entree_id: str | None, categorie: str, cle: str,
                      valeur: Any) -> dict:
        tv: Televiseur = app.state.televiseur
        try:
            resultat = await tv.ecrire(categorie, cle, valeur)
        except ConnexionTvPerdue:
            raise HTTPException(503, "Téléviseur injoignable")
        if resultat["confirme"]:
            await app.state.historique.enregistrer(
                entree_id, categorie, cle,
                resultat["ancienne"], resultat["nouvelle"],
                resultat["mode_image"])
        return {"entree_id": entree_id, "categorie": categorie, "cle": cle,
                **resultat}

    @app.post("/api/reglages/{entree_id}")
    async def ecrire_reglage(entree_id: str, corps: Ecriture) -> dict:
        try:
            categorie, cle, valeur = arbre.preparer_ecriture(entree_id, corps.valeur)
        except arbre.EntreeInconnue:
            raise HTTPException(404, f"Entrée inconnue : {entree_id}")
        except arbre.EntreeNonPilotable:
            raise HTTPException(400, f"Entrée non pilotable par l'API : {entree_id}")
        except arbre.ValeurInvalide as exc:
            raise HTTPException(400, f"Valeur invalide : {exc}")
        return await _ecrire(entree_id, categorie, cle, valeur)

    @app.post("/api/reglages-bruts")
    async def ecrire_reglage_brut(corps: EcritureBrute) -> dict:
        # Accès direct catégorie/clé, sans validation par l'arbre : réservé
        # aux clés que l'arbre ne représente pas finement (tableaux de
        # balance des blancs, clés génériques).
        return await _ecrire(None, corps.categorie, corps.cle, corps.valeur)

    @app.get("/api/historique")
    async def lister_historique(limite: int = 100) -> list[dict]:
        return await app.state.historique.lister(limite)

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
