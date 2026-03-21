from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Optional

from backend.engine.models import GameState, PlacedTile
from backend.engine.tile_library import TILE_LIBRARY, rotated_features


@dataclass(frozen=True)
class BotMove:
    x: int
    y: int
    rotation: int
    feature_id: Optional[str]


class HeuristicBotPolicy:
    def __init__(self, difficulty: str) -> None:
        self.difficulty = difficulty

    def choose_move(self, game: GameState, trace_component: Callable) -> BotMove:
        assert game.current_turn is not None
        current_player = game.players[game.turn_index % len(game.players)]
        scored_moves: list[tuple[tuple, BotMove]] = []

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
                scored_moves.append(
                    (
                        score,
                        BotMove(
                            x=move["x"],
                            y=move["y"],
                            rotation=move["rotation"],
                            feature_id=option["feature_id"],
                        ),
                    )
                )

        assert scored_moves
        scored_moves.sort(key=lambda item: item[0], reverse=True)
        if self.difficulty == "easy":
            return random.choice(scored_moves[: min(4, len(scored_moves))])[1]
        if self.difficulty == "medium":
            top = scored_moves[: min(2, len(scored_moves))]
            return top[0][1] if random.random() < 0.8 else random.choice(top)[1]
        return scored_moves[0][1]

    def _score_move(self, game: GameState, *, trace_component, x: int, y: int, rotation: int, feature_id: Optional[str]) -> tuple:
        assert game.current_turn is not None
        tile_id = game.current_turn.tile_id
        tile = TILE_LIBRARY[tile_id]
        placed_tile = PlacedTile(tile_id=tile_id, rotation=rotation, x=x, y=y)

        immediate_points = 0
        completes_feature = 0
        open_feature_value = 0
        farm_value = 0
        city_risk = 0
        for feature in rotated_features(tile, rotation):
            if feature.kind in {"city", "road"}:
                component = trace_component(game, placed_tile, feature.id)
                if component["is_complete"]:
                    completes_feature += 1
                    immediate_points += component["score"]
                else:
                    open_feature_value += component["score"]
                    if feature.kind == "city":
                        city_risk += 1
            elif feature.kind == "field":
                component = trace_component(game, placed_tile, feature.id)
                farm_value = max(farm_value, component["score"])

        monastery_bonus = 0
        meeple_priority = 0
        meeple_commitment = 0
        defensive_value = 0
        if feature_id is not None:
            selected_feature = next(feature for feature in rotated_features(tile, rotation) if feature.id == feature_id)
            meeple_priority = {"city": 4, "road": 3, "monastery": 2, "field": 1}.get(selected_feature.kind, 0)
            meeple_commitment = 1
            if selected_feature.kind == "monastery":
                monastery_bonus = sum(
                    1
                    for dx in (-1, 0, 1)
                    for dy in (-1, 0, 1)
                    if (x + dx, y + dy) in game.board or (dx == 0 and dy == 0)
                )
            component = trace_component(game, placed_tile, selected_feature.id)
            opponent_ids = {
                member["meeple"].player_id
                for member in component["members"]
                if member["meeple"] is not None and member["meeple"].player_id != current_player.id
            }
            defensive_value = len(opponent_ids)

        placement_tiebreak = -(abs(x) + abs(y))
        if self.difficulty == "easy":
            return (immediate_points, completes_feature, meeple_priority, placement_tiebreak, -rotation)
        if self.difficulty == "medium":
            return (
                immediate_points,
                completes_feature,
                monastery_bonus,
                open_feature_value,
                farm_value,
                meeple_priority,
                -meeple_commitment,
                placement_tiebreak,
                -rotation,
            )
        return (
            immediate_points,
            completes_feature,
            defensive_value,
            monastery_bonus,
            farm_value,
            open_feature_value,
            meeple_priority,
            -city_risk,
            -meeple_commitment,
            placement_tiebreak,
            -rotation,
        )


BOT_POLICIES = {
    "easy": HeuristicBotPolicy("easy"),
    "medium": HeuristicBotPolicy("medium"),
    "hard": HeuristicBotPolicy("hard"),
}
