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

What choose_move() receives:
- game: the live GameState for the current turn
  - game.players: ordered list of PlayerState objects
  - game.turn_index: index of the active player in game.players
  - game.current_turn.tile_id: tile that must be placed this turn
  - game.current_turn.legal_moves: every legal placement for that tile
  - game.board: placed tiles keyed by (x, y)
  - game.message_log: recent game messages
- trace_component(game, placed_tile, feature_id): helper used by the built-in bots
  - useful if you want to inspect how a tentative road/city/field connects
  - optional; simple bots can ignore it

Structure of each legal move in game.current_turn.legal_moves:
- x, y: board coordinate where the tile may be placed
- rotation: clockwise quarter-turn count from 0 to 3
- meeple_options: list of legal meeple choices for that placement
  - each option has:
    - feature_id: None for "no meeple", otherwise the feature identifier on the placed tile
    - kind: one of city, road, monastery, field, or None for no meeple
    - label: human-readable text

What choose_move() must return:
- a BotMove instance
- x, y, and rotation must match one of the legal moves
- feature_id must be either:
  - None, for no meeple
  - one of the feature_id values from that move's meeple_options

Minimal implementation strategy:
- pick one item from game.current_turn.legal_moves
- pick one item from that move's meeple_options
- return BotMove(x=..., y=..., rotation=..., feature_id=...)

Important constraints:
- do not mutate game state directly
- do not place tiles or meeples by editing game.board
- do not invent moves that are not present in legal_moves
- the server will still validate the returned move
"""

from __future__ import annotations

from backend.bots.heuristic_utils import BotMove


IS_TEMPLATE = True
BOT_SLUG = "template"
BOT_NAME = "Template Bot"
BOT_DESCRIPTION = "Example file showing the custom bot API."


def choose_move(game, trace_component) -> BotMove:
    """
    Example implementation:
    - select the first legal tile placement
    - select the first legal meeple option for that placement
    - return that choice as a BotMove

    Replace this with your own move-selection logic.
    """
    move = game.current_turn.legal_moves[0]
    return BotMove(
        x=move["x"],
        y=move["y"],
        rotation=move["rotation"],
        feature_id=move["meeple_options"][0]["feature_id"],
    )
