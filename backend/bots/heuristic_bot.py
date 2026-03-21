from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.engine.models import GameState, PlacedTile
from backend.engine.tile_library import TILE_LIBRARY, rotated_features


@dataclass(frozen=True)
class BotMove:
    x: int
    y: int
    rotation: int
    feature_id: Optional[str]


class BasicHeuristicBot:
    def choose_move(self, game: GameState, trace_component) -> BotMove:
        assert game.current_turn is not None
        current_player = game.players[game.turn_index % len(game.players)]
        best_score = None
        best_move: Optional[BotMove] = None

        for move in game.current_turn.legal_moves:
            for option in move["meeple_options"]:
                if option["feature_id"] is not None and current_player.meeples_available <= 0:
                    continue
                score = self._score_move(
                    game,
                    trace_component=trace_component,
                    x=move["x"],
                    y=move["y"],
                    rotation=move["rotation"],
                    feature_id=option["feature_id"],
                )
                candidate = BotMove(
                    x=move["x"],
                    y=move["y"],
                    rotation=move["rotation"],
                    feature_id=option["feature_id"],
                )
                if best_score is None or score > best_score:
                    best_score = score
                    best_move = candidate

        assert best_move is not None
        return best_move

    def _score_move(self, game: GameState, *, trace_component, x: int, y: int, rotation: int, feature_id: Optional[str]) -> tuple:
        assert game.current_turn is not None
        tile_id = game.current_turn.tile_id
        tile = TILE_LIBRARY[tile_id]
        placed_tile = PlacedTile(tile_id=tile_id, rotation=rotation, x=x, y=y)

        immediate_points = 0
        completes_feature = 0
        for feature in rotated_features(tile, rotation):
            if feature.kind not in {"city", "road"}:
                continue
            component = trace_component(game, placed_tile, feature.id)
            if component["is_complete"]:
                completes_feature += 1
                immediate_points += component["score"]

        monastery_bonus = 0
        meeple_priority = 0
        if feature_id is not None:
            selected_feature = next(feature for feature in rotated_features(tile, rotation) if feature.id == feature_id)
            meeple_priority = {"city": 4, "road": 3, "monastery": 2, "field": 1}.get(selected_feature.kind, 0)
            if selected_feature.kind == "monastery":
                monastery_bonus = sum(
                    1
                    for dx in (-1, 0, 1)
                    for dy in (-1, 0, 1)
                    if (x + dx, y + dy) in game.board or (dx == 0 and dy == 0)
                )

        placement_tiebreak = -(abs(x) + abs(y))
        return (immediate_points, completes_feature, monastery_bonus, meeple_priority, placement_tiebreak, -rotation)
