from __future__ import annotations

from threading import Lock
from typing import Dict, Optional

from backend.bots.heuristic_bot import BOT_POLICIES
from backend.engine.game_engine import GameEngine
from backend.engine.models import GameState


class GameStore:
    def __init__(self) -> None:
        self.games: Dict[str, GameState] = {}
        self.engine = GameEngine()
        self._lock = Lock()

    def create_game(self, seed: Optional[int] = None, *, pending_bot_counts: Optional[Dict[str, int]] = None) -> GameState:
        with self._lock:
            game = self.engine.create_game(seed=seed)
            requested = pending_bot_counts or {}
            normalized = {key: max(0, int(value)) for key, value in requested.items() if key in BOT_POLICIES}
            total = sum(normalized.values())
            if total > game.max_players - 1:
                remaining = game.max_players - 1
                trimmed: Dict[str, int] = {}
                for key in ("easy", "medium", "hard"):
                    count = min(normalized.get(key, 0), remaining)
                    trimmed[key] = count
                    remaining -= count
                normalized = trimmed
            game.pending_bot_counts = normalized
            self.games[game.game_id] = game
            return game

    def get_game(self, game_id: str) -> Optional[GameState]:
        return self.games.get(game_id)

    def add_player(self, game_id: str, *, name: Optional[str] = None, is_bot: bool = False):
        with self._lock:
            game = self.games[game_id]
            player = self.engine.add_player(game, name=name, is_bot=is_bot)
            if not is_bot and game.pending_bot_counts:
                self._materialize_pending_bots(game)
            return player

    def create_bot_only_game(self, seed: Optional[int] = None, *, pending_bot_counts: Optional[Dict[str, int]] = None) -> GameState:
        with self._lock:
            game = self.engine.create_game(seed=seed)
            requested = pending_bot_counts or {}
            normalized = {key: max(0, int(value)) for key, value in requested.items() if key in BOT_POLICIES}
            total = sum(normalized.values())
            if total < 2:
                raise ValueError("Bot-only games require at least two bots.")
            if total > game.max_players:
                remaining = game.max_players
                trimmed: Dict[str, int] = {}
                for key in ("easy", "medium", "hard"):
                    count = min(normalized.get(key, 0), remaining)
                    trimmed[key] = count
                    remaining -= count
                normalized = trimmed
            game.pending_bot_counts = normalized
            self.games[game.game_id] = game
            self._materialize_pending_bots(game)
            self.engine.start_game(game, game.host_player_id)
            return game

    def start_game(self, game_id: str, player_id: str) -> GameState:
        with self._lock:
            game = self.games[game_id]
            self.engine.start_game(game, player_id)
            if self._has_human_player(game):
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

    def advance_bot_only_game(self, game_id: str, steps: int = 1) -> GameState:
        with self._lock:
            game = self.games[game_id]
            if self._has_human_player(game):
                return game
            self._run_bot_turns(game, max_turns=steps)
            return game

    def _run_bot_turns(self, game: GameState, max_turns: Optional[int] = None) -> None:
        turns_run = 0
        while game.status == "active" and game.current_turn is not None:
            if max_turns is not None and turns_run >= max_turns:
                return
            current_player = game.players[game.turn_index % len(game.players)]
            if not current_player.is_bot:
                return
            policy = BOT_POLICIES.get(current_player.bot_policy or "easy", BOT_POLICIES["easy"])
            move = policy.choose_move(game, self.engine._trace_feature_component)
            self.engine.submit_turn(
                game,
                player_id=current_player.id,
                x=move.x,
                y=move.y,
                rotation=move.rotation,
                feature_id=move.feature_id,
            )
            turns_run += 1

    def _materialize_pending_bots(self, game: GameState) -> None:
        if not game.pending_bot_counts:
            return
        for policy_name in ("easy", "medium", "hard"):
            count = game.pending_bot_counts.get(policy_name, 0)
            for index in range(count):
                self.engine.add_player(
                    game,
                    name=self._bot_name(policy_name, index, count),
                    is_bot=True,
                    bot_policy=policy_name,
                )
        game.pending_bot_counts = {}

    def _bot_name(self, policy_name: str, index: int, count: int) -> str:
        label = policy_name.title()
        if count == 1:
            return f"{label} Bot"
        return f"{label} Bot {index + 1}"

    def _has_human_player(self, game: GameState) -> bool:
        return any(not player.is_bot for player in game.players)


game_store = GameStore()
