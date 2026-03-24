from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

from backend.bots.loader import BotLoadError, BotRegistry
from backend.engine.game_engine import GameEngine
from backend.engine.models import GameState


ARCHIVE_ROOT = Path(__file__).resolve().parents[2] / "saved_games"


class GameStore:
    def __init__(self) -> None:
        self.games: Dict[str, GameState] = {}
        self.engine = GameEngine()
        self.bot_registry = BotRegistry()
        ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def create_game(
        self,
        seed: Optional[int] = None,
        *,
        pending_bot_counts: Optional[Dict[str, int]] = None,
        use_void_cards: bool = False,
        use_creepassonne: bool = False,
        initial_meeples: int = 7,
    ) -> GameState:
        with self._lock:
            game = self.engine.create_game(
                seed=seed,
                use_void_cards=use_void_cards,
                use_creepassonne=use_creepassonne,
                initial_meeples=initial_meeples,
            )
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
            self._record_history(game, "game_created", "Game created.")
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

    def list_archives(self) -> list[dict]:
        archives: list[dict] = []
        for path in sorted(ARCHIVE_ROOT.glob("*.json"), reverse=True):
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            archives.append(payload["summary"])
        return archives

    def load_archive(self, archive_id: str) -> dict:
        path = ARCHIVE_ROOT / f"{archive_id}.json"
        if not path.exists():
            raise FileNotFoundError(archive_id)
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def add_player(self, game_id: str, *, name: Optional[str] = None, is_bot: bool = False):
        with self._lock:
            game = self.games[game_id]
            player = self.engine.add_player(game, name=name, is_bot=is_bot)
            if not is_bot and game.pending_bot_counts:
                self._materialize_pending_bots(game)
            self._record_history(game, "player_joined", f"{player.name} joined the game.", player_id=player.id)
            return player

    def create_bot_only_game(
        self,
        seed: Optional[int] = None,
        *,
        pending_bot_counts: Optional[Dict[str, int]] = None,
        use_void_cards: bool = False,
        use_creepassonne: bool = False,
        initial_meeples: int = 7,
    ) -> GameState:
        with self._lock:
            game = self.engine.create_game(
                seed=seed,
                use_void_cards=use_void_cards,
                use_creepassonne=use_creepassonne,
                initial_meeples=initial_meeples,
            )
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
            self._record_history(game, "game_created", "Bot-only game created.")
            self._record_history(game, "game_started", "Bot-only game started automatically.", player_id=game.host_player_id)
            self._save_archive_if_finished(game)
            return game

    def start_game(self, game_id: str, player_id: str) -> GameState:
        with self._lock:
            game = self.games[game_id]
            self.engine.start_game(game, player_id)
            self._record_history(game, "game_started", "Game started.", player_id=player_id)
            if self._has_human_player(game):
                self._run_bot_turns(game)
            self._save_archive_if_finished(game)
            return game

    def submit_move(self, game_id: str, *, player_id: str, x: int, y: int, rotation: int, feature_id: Optional[str]) -> GameState:
        with self._lock:
            game = self.games[game_id]
            self._apply_turn(game, player_id=player_id, x=x, y=y, rotation=rotation, feature_id=feature_id)
            self._run_bot_turns(game)
            self._save_archive_if_finished(game)
            return game

    def advance_bot_only_game(self, game_id: str, steps: int = 1) -> GameState:
        with self._lock:
            game = self.games[game_id]
            if self._has_human_player(game):
                return game
            self._run_bot_turns(game, max_turns=steps)
            self._save_archive_if_finished(game)
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
            self._apply_turn(
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
                self._record_history(
                    game,
                    "bot_inserted",
                    f"{self._bot_name(definition.name, index, count)} joined as a bot.",
                )
        game.pending_bot_counts = {}

    def _bot_name(self, label: str, index: int, count: int) -> str:
        if count == 1:
            return label
        return f"{label} {index + 1}"

    def _has_human_player(self, game: GameState) -> bool:
        return any(not player.is_bot for player in game.players)

    def _apply_turn(self, game: GameState, *, player_id: str, x: int, y: int, rotation: int, feature_id: Optional[str]) -> None:
        before_messages = len(game.message_log)
        self.engine.submit_turn(
            game,
            player_id=player_id,
            x=x,
            y=y,
            rotation=rotation,
            feature_id=feature_id,
        )
        description = " ".join(game.message_log[before_messages:]) or "Turn applied."
        self._record_history(game, "turn_played", description, player_id=player_id)

    def _record_history(self, game: GameState, event_type: str, description: str, player_id: Optional[str] = None) -> None:
        game.history.append(
            {
                "index": len(game.history),
                "type": event_type,
                "description": description,
                "player_id": player_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "snapshot": self.engine.serialize(game),
            }
        )

    def _save_archive_if_finished(self, game: GameState) -> None:
        if game.status != "finished" or game.archive_saved:
            return
        archive_id = f"{game.game_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        payload = {
            "archive_id": archive_id,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "archive_id": archive_id,
                "game_id": game.game_id,
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "players": [player.name for player in game.players],
                "winner_ids": list(game.winner_ids),
                "winner_names": [player.name for player in game.players if player.id in game.winner_ids],
                "final_scores": {player.name: player.score for player in game.players},
                "turn_count": len([entry for entry in game.history if entry["type"] == "turn_played"]),
                "use_void_cards": game.use_void_cards,
                "use_creepassonne": game.use_creepassonne,
                "initial_meeples": game.initial_meeples,
            },
            "final_state": self.engine.serialize(game),
            "history": game.history,
        }
        path = ARCHIVE_ROOT / f"{archive_id}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        game.archive_saved = True


game_store = GameStore()
