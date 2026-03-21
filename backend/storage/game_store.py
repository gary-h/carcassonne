from __future__ import annotations

from threading import Lock
from typing import Dict, Optional

from backend.engine.game_engine import GameEngine
from backend.engine.models import GameState


class GameStore:
    def __init__(self) -> None:
        self.games: Dict[str, GameState] = {}
        self.engine = GameEngine()
        self._lock = Lock()

    def create_game(self, seed: Optional[int] = None) -> GameState:
        with self._lock:
            game = self.engine.create_game(seed=seed)
            self.games[game.game_id] = game
            return game

    def get_game(self, game_id: str) -> Optional[GameState]:
        return self.games.get(game_id)


game_store = GameStore()
