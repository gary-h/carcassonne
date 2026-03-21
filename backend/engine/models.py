from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class PlayerState:
    id: str
    name: str
    color: str
    is_bot: bool = False
    bot_policy: Optional[str] = None
    score: int = 0
    meeples_available: int = 7


@dataclass
class MeeplePlacement:
    player_id: str
    feature_id: str
    kind: str


@dataclass
class PlacedTile:
    tile_id: str
    rotation: int
    x: int
    y: int
    meeple: Optional[MeeplePlacement] = None


@dataclass
class CurrentTurn:
    tile_id: str
    legal_moves: List[dict]


@dataclass
class GameState:
    game_id: str
    status: str = "waiting"
    host_player_id: Optional[str] = None
    max_players: int = 5
    initial_meeples: int = 7
    use_void_cards: bool = False
    pending_bot_counts: Dict[str, int] = field(default_factory=dict)
    players: List[PlayerState] = field(default_factory=list)
    board: Dict[Tuple[int, int], PlacedTile] = field(default_factory=dict)
    deck: List[str] = field(default_factory=list)
    discarded_tiles: List[str] = field(default_factory=list)
    turn_index: int = 0
    current_turn: Optional[CurrentTurn] = None
    winner_ids: List[str] = field(default_factory=list)
    message_log: List[str] = field(default_factory=list)
    completed_features: Set[str] = field(default_factory=set)
