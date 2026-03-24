from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.bots.loader import BotLoadError
from backend.engine.game_engine import InvalidMoveError
from backend.storage.game_store import game_store

router = APIRouter()


class CreateGameRequest(BaseModel):
    seed: Optional[int] = None
    bot_counts: dict[str, int] = {}
    bot_only: bool = False
    use_void_cards: bool = False
    use_creepassonne: bool = False
    initial_meeples: int = 7


class JoinGameRequest(BaseModel):
    name: Optional[str] = None


class StartGameRequest(BaseModel):
    player_id: str


@router.post("/create")
def create_game(payload: CreateGameRequest | None = None):
    pending_bot_counts = {} if payload is None else payload.bot_counts
    if payload is not None and payload.bot_only:
        total_bots = sum(pending_bot_counts.values())
        if total_bots < 2:
            raise HTTPException(status_code=400, detail="Bot-only games require at least two bots.")
        try:
            game = game_store.create_bot_only_game(
                seed=payload.seed,
                pending_bot_counts=pending_bot_counts,
                use_void_cards=payload.use_void_cards,
                use_creepassonne=payload.use_creepassonne,
                initial_meeples=payload.initial_meeples,
            )
        except (ValueError, BotLoadError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        try:
            game = game_store.create_game(
                seed=None if payload is None else payload.seed,
                pending_bot_counts=pending_bot_counts,
                use_void_cards=False if payload is None else payload.use_void_cards,
                use_creepassonne=False if payload is None else payload.use_creepassonne,
                initial_meeples=7 if payload is None else payload.initial_meeples,
            )
        except BotLoadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "game_id": game.game_id,
        "game": game_store.engine.serialize(game),
    }


@router.get("/bots")
def list_bots():
    try:
        return {"bots": game_store.list_bots()}
    except BotLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/archives")
def list_archives():
    return {"archives": game_store.list_archives()}


@router.get("/archives/{archive_id}")
def get_archive(archive_id: str):
    try:
        return game_store.load_archive(archive_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Archive not found") from exc


@router.post("/{game_id}/join")
def join_game(game_id: str, payload: JoinGameRequest):
    game = game_store.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    try:
        player = game_store.add_player(game_id, name=payload.name)
    except (InvalidMoveError, BotLoadError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "player_id": player.id,
        "game": game_store.engine.serialize(game, viewer_player_id=player.id),
    }


@router.post("/{game_id}/start")
def start_game(game_id: str, payload: StartGameRequest):
    game = game_store.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    try:
        game = game_store.start_game(game_id, payload.player_id)
    except (InvalidMoveError, BotLoadError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"game": game_store.engine.serialize(game, viewer_player_id=payload.player_id)}


@router.get("/{game_id}")
def get_game(game_id: str, player_id: Optional[str] = None):
    game = game_store.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    try:
        if player_id is None:
            game = game_store.advance_bot_only_game(game_id, steps=1)
        return game_store.engine.serialize(game, viewer_player_id=player_id)
    except BotLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
