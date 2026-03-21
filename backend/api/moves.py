from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.bots.loader import BotLoadError
from backend.engine.game_engine import InvalidMoveError
from backend.storage.game_store import game_store


router = APIRouter()


class SubmitMoveRequest(BaseModel):
    player_id: str
    x: int
    y: int
    rotation: int
    feature_id: Optional[str] = None


@router.post("/{game_id}/submit")
def submit_move(game_id: str, payload: SubmitMoveRequest):
    game = game_store.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    try:
        game = game_store.submit_move(
            game_id,
            player_id=payload.player_id,
            x=payload.x,
            y=payload.y,
            rotation=payload.rotation,
            feature_id=payload.feature_id,
        )
    except (InvalidMoveError, BotLoadError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"game": game_store.engine.serialize(game, viewer_player_id=payload.player_id)}
