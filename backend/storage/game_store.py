from __future__ import annotations

from threading import Lock
from typing import Dict, Optional

from backend.bots.loader import BotLoadError, BotRegistry
from backend.engine.game_engine import GameEngine
from backend.engine.models import GameState


class GameStore:
    def __init__(self) -> None:
        self.games: Dict[str, GameState] = {}
        self.engine = GameEngine()
        self.bot_registry = BotRegistry()
        self._lock = Lock()

    def create_game(
        self,
        seed: Optional[int] = None,
        *,
        pending_bot_counts: Optional[Dict[str, int]] = None,
        use_void_cards: bool = False,
    ) -> GameState:
        with self._lock:
            game = self.engine.create_game(seed=seed, use_void_cards=use_void_cards)
            requested = pending_bot_counts or {}
            known_slugs = {definition.slug for definition in self.bot_registry.list_bots()}
            normalized = {key: max(0, int(value)) for key, value in requested.items() if key in known_slugs}
            total = sum(normalized.values())
            if total > game.max_players - 1:
                remaining = game.max_players - 1
                trimmed: Dict[str, int] = {}
                for key in sorted(normalized.keys()):
                    count = min(normalized.get(key, 0), remaining)
                    trimmed[key] = count
                    remaining -= count
                normalized = trimmed
            game.pending_bot_counts = normalized
            self.games[game.game_id] = game
            return game

    def get_game(self, game_id: str) -> Optional[GameState]:
        return self.games.get(game_id)

    def list_bots(self) -> list[dict]:
        return [
            {
                "slug": definition.slug,
                "name": definition.name,
                "description": definition.description,
                "filename": definition.path.name,
            }
            for definition in self.bot_registry.list_bots()
        ]

    def add_player(self, game_id: str, *, name: Optional[str] = None, is_bot: bool = False):
        with self._lock:
            game = self.games[game_id]
            player = self.engine.add_player(game, name=name, is_bot=is_bot)
            if not is_bot and game.pending_bot_counts:
                self._materialize_pending_bots(game)
            return player

    def create_bot_only_game(
        self,
        seed: Optional[int] = None,
        *,
        pending_bot_counts: Optional[Dict[str, int]] = None,
        use_void_cards: bool = False,
    ) -> GameState:
        with self._lock:
            game = self.engine.create_game(seed=seed, use_void_cards=use_void_cards)
            requested = pending_bot_counts or {}
            known_slugs = {definition.slug for definition in self.bot_registry.list_bots()}
            normalized = {key: max(0, int(value)) for key, value in requested.items() if key in known_slugs}
            total = sum(normalized.values())
            if total < 2:
                raise ValueError("Bot-only games require at least two bots.")
            if total > game.max_players:
                remaining = game.max_players
                trimmed: Dict[str, int] = {}
                for key in sorted(normalized.keys()):
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
            if not current_player.bot_policy:
                return
            definition = self.bot_registry.get_bot(current_player.bot_policy)
            move = definition.choose_move(game, self.engine._trace_feature_component)
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
        definitions = {definition.slug: definition for definition in self.bot_registry.list_bots()}
        for policy_name in sorted(game.pending_bot_counts.keys()):
            count = game.pending_bot_counts.get(policy_name, 0)
            definition = definitions.get(policy_name)
            if definition is None:
                continue
            for index in range(count):
                self.engine.add_player(
                    game,
                    name=self._bot_name(definition.name, index, count),
                    is_bot=True,
                    bot_policy=policy_name,
                )
        game.pending_bot_counts = {}

    def _bot_name(self, label: str, index: int, count: int) -> str:
        if count == 1:
            return label
        return f"{label} {index + 1}"

    def _has_human_player(self, game: GameState) -> bool:
        return any(not player.is_bot for player in game.players)


game_store = GameStore()
