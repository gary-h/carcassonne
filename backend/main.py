from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Carcassonne Backend")

from backend.api.games import router as games_router
from backend.api.moves import router as moves_router

app.include_router(games_router, prefix="/games", tags=["games"])
app.include_router(moves_router, prefix="/moves", tags=["moves"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_ROOT = PROJECT_ROOT / "frontend"
ASSET_ROOT = PROJECT_ROOT / "assets"

app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")
app.mount("/assets", StaticFiles(directory=ASSET_ROOT), name="assets")


@app.get("/")
def display():
    return FileResponse(STATIC_ROOT / "index.html")
