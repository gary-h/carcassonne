from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.engine.game_engine import InvalidMoveError
from backend.storage.game_store import game_store

router = APIRouter()


class CreateGameRequest(BaseModel):
    seed: Optional[int] = None


class JoinGameRequest(BaseModel):
    name: Optional[str] = None


@router.post("/create")
def create_game(payload: CreateGameRequest | None = None):
    game = game_store.create_game(seed=None if payload is None else payload.seed)
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
        player = game_store.engine.add_player(game, name=payload.name)
    except InvalidMoveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "player_id": player.id,
        "game": game_store.engine.serialize(game, viewer_player_id=player.id),
    }


@router.get("/{game_id}")
def get_game(game_id: str, player_id: Optional[str] = None):
    game = game_store.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game_store.engine.serialize(game, viewer_player_id=player_id)
