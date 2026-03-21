"""
Copy this file, rename it, and update the constants plus choose_move().

Required API:
- BOT_SLUG: unique short identifier used by the server and UI
- BOT_NAME: display name shown to the host
- BOT_DESCRIPTION: short summary shown in the lobby
- choose_move(game, trace_component): return a BotMove

The server remains authoritative:
- game is the current GameState
- trace_component is the engine helper used by built-in heuristic bots
- your bot only chooses among legal placements from game.current_turn.legal_moves
"""

from __future__ import annotations

from backend.bots.heuristic_utils import BotMove


IS_TEMPLATE = True
BOT_SLUG = "template"
BOT_NAME = "Template Bot"
BOT_DESCRIPTION = "Example file showing the custom bot API."


def choose_move(game, trace_component) -> BotMove:
    move = game.current_turn.legal_moves[0]
    return BotMove(
        x=move["x"],
        y=move["y"],
        rotation=move["rotation"],
        feature_id=move["meeple_options"][0]["feature_id"],
    )
