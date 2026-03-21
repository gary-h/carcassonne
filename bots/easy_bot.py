from __future__ import annotations

import random

from backend.bots.heuristic_utils import BotMove, score_move


BOT_SLUG = "easy"
BOT_NAME = "Easy Bot"
BOT_DESCRIPTION = "Loose heuristic bot that prefers simple immediate gains."


def choose_move(game, trace_component) -> BotMove:
    assert game.current_turn is not None
    current_player = game.players[game.turn_index % len(game.players)]
    scored_moves: list[tuple[tuple, BotMove]] = []

    for move in game.current_turn.legal_moves:
        for option in move["meeple_options"]:
            if option["feature_id"] is not None and current_player.meeples_available <= 0:
                continue
            details = score_move(
                game,
                trace_component=trace_component,
                x=move["x"],
                y=move["y"],
                rotation=move["rotation"],
                feature_id=option["feature_id"],
            )
            score = (
                details["immediate_points"],
                details["completes_feature"],
                details["meeple_priority"],
                details["placement_tiebreak"],
                details["rotation_tiebreak"],
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

    scored_moves.sort(key=lambda item: item[0], reverse=True)
    return random.choice(scored_moves[: min(4, len(scored_moves))])[1]
