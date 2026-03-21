from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.engine.game_engine import InvalidMoveError
from backend.storage.game_store import game_store

router = APIRouter()


class CreateGameRequest(BaseModel):
    seed: Optional[int] = None
    easy_bot_count: int = 0
    medium_bot_count: int = 0
    hard_bot_count: int = 0
    bot_only: bool = False


class JoinGameRequest(BaseModel):
    name: Optional[str] = None


class StartGameRequest(BaseModel):
    player_id: str


@router.post("/create")
def create_game(payload: CreateGameRequest | None = None):
    pending_bot_counts = {
        "easy": 0 if payload is None else payload.easy_bot_count,
        "medium": 0 if payload is None else payload.medium_bot_count,
        "hard": 0 if payload is None else payload.hard_bot_count,
    }
    if payload is not None and payload.bot_only:
        total_bots = sum(pending_bot_counts.values())
        if total_bots < 2:
            raise HTTPException(status_code=400, detail="Bot-only games require at least two bots.")
        game = game_store.create_bot_only_game(
            seed=payload.seed,
            pending_bot_counts=pending_bot_counts,
        )
    else:
        game = game_store.create_game(
            seed=None if payload is None else payload.seed,
            pending_bot_counts=pending_bot_counts,
        )
    return {
        "game_id": game.game_id,
        "game": game_store.engine.serialize(game),
    }


@router.post("/{game_id}/join")
def join_game(game_id: str, payload: JoinGameRequest):
    game = game_store.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    try:
        player = game_store.add_player(game_id, name=payload.name)
    except InvalidMoveError as exc:
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
    except InvalidMoveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"game": game_store.engine.serialize(game, viewer_player_id=payload.player_id)}


@router.get("/{game_id}")
def get_game(game_id: str, player_id: Optional[str] = None):
    game = game_store.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if player_id is None:
        game = game_store.advance_bot_only_game(game_id, steps=1)
    return game_store.engine.serialize(game, viewer_player_id=player_id)
