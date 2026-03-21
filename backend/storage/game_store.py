from __future__ import annotations

from threading import Lock
from typing import Dict, Optional

from backend.bots.heuristic_bot import BasicHeuristicBot
from backend.engine.game_engine import GameEngine
from backend.engine.models import GameState


class GameStore:
    def __init__(self) -> None:
        self.games: Dict[str, GameState] = {}
        self.engine = GameEngine()
        self._lock = Lock()
        self.basic_bot = BasicHeuristicBot()

    def create_game(self, seed: Optional[int] = None, *, pending_basic_bot_count: int = 0) -> GameState:
        with self._lock:
            game = self.engine.create_game(seed=seed)
            game.pending_basic_bot_count = min(max(pending_basic_bot_count, 0), game.max_players - 1)
            self.games[game.game_id] = game
            return game

    def get_game(self, game_id: str) -> Optional[GameState]:
        return self.games.get(game_id)

    def add_player(self, game_id: str, *, name: Optional[str] = None, is_bot: bool = False):
        with self._lock:
            game = self.games[game_id]
            player = self.engine.add_player(game, name=name, is_bot=is_bot)
            if not is_bot and game.pending_basic_bot_count > 0:
                for index in range(game.pending_basic_bot_count):
                    bot_name = "Bot" if game.pending_basic_bot_count == 1 else f"Bot {index + 1}"
                    self.engine.add_player(game, name=bot_name, is_bot=True)
                game.pending_basic_bot_count = 0
            return player

    def start_game(self, game_id: str, player_id: str) -> GameState:
        with self._lock:
            game = self.games[game_id]
            self.engine.start_game(game, player_id)
            self._run_bot_turns(game)
            return game

    def submit_move(self, game_id: str, *, player_id: str, x: int, y: int, rotation: int, feature_id: Optional[str]) -> GameState:
        with self._lock:
            game = self.games[game_id]
            self.engine.submit_turn(
                game,
                player_id=player_id,
                x=x,
                y=y,
                rotation=rotation,
                feature_id=feature_id,
            )
            self._run_bot_turns(game)
            return game

    def _run_bot_turns(self, game: GameState) -> None:
        while game.status == "active" and game.current_turn is not None:
            current_player = game.players[game.turn_index % len(game.players)]
            if not current_player.is_bot:
                return
            move = self.basic_bot.choose_move(game, self.engine._trace_feature_component)
            self.engine.submit_turn(
                game,
                player_id=current_player.id,
                x=move.x,
                y=move.y,
                rotation=move.rotation,
                feature_id=move.feature_id,
            )


game_store = GameStore()
