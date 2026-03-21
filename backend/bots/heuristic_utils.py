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


def choose_scored_move(scored_moves: list[tuple[tuple, BotMove]], *, top_band: int = 1, weighted_pick: float | None = None) -> BotMove:
    scored_moves.sort(key=lambda item: item[0], reverse=True)
    candidates = scored_moves[: min(top_band, len(scored_moves))]
    if weighted_pick is not None and len(candidates) > 1 and random.random() >= weighted_pick:
        return random.choice(candidates)
    return candidates[0][1] if top_band == 1 else random.choice(candidates)


def score_move(
    game: GameState,
    *,
    trace_component: Callable,
    x: int,
    y: int,
    rotation: int,
    feature_id: Optional[str],
) -> dict:
    assert game.current_turn is not None
    current_player = game.players[game.turn_index % len(game.players)]
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
    selected_kind = None
    if feature_id is not None:
        selected_feature = next(feature for feature in rotated_features(tile, rotation) if feature.id == feature_id)
        selected_kind = selected_feature.kind
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

    return {
        "immediate_points": immediate_points,
        "completes_feature": completes_feature,
        "open_feature_value": open_feature_value,
        "farm_value": farm_value,
        "city_risk": city_risk,
        "monastery_bonus": monastery_bonus,
        "meeple_priority": meeple_priority,
        "meeple_commitment": meeple_commitment,
        "defensive_value": defensive_value,
        "placement_tiebreak": -(abs(x) + abs(y)),
        "rotation_tiebreak": -rotation,
        "meeples_available": current_player.meeples_available,
        "selected_kind": selected_kind,
    }
