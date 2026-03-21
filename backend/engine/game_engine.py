from __future__ import annotations

import random
from collections import Counter, deque
from typing import Dict, List, Optional, Set, Tuple
from uuid import uuid4

from backend.engine.models import CurrentTurn, GameState, MeeplePlacement, PlacedTile, PlayerState
from backend.engine.tile_library import OPPOSITE_DIRECTION, OPPOSITE_PORT, START_TILE_ID, STEP_BY_DIRECTION, STEP_BY_PORT, TILE_LIBRARY, rotated_features, rotate_edges


PLAYER_COLORS = ["red", "blue", "green", "yellow", "black"]
MIN_PLAYERS = 2
MAX_PLAYERS = 5


class InvalidMoveError(ValueError):
    pass


class GameEngine:
    def create_game(self, seed: Optional[int] = None) -> GameState:
        game_id = uuid4().hex[:8]
        rng = random.Random(seed if seed is not None else game_id)
        deck: List[str] = []
        for tile_id, tile in TILE_LIBRARY.items():
            if tile_id == START_TILE_ID:
                continue
            deck.extend([tile_id] * tile.count)
        rng.shuffle(deck)
        game = GameState(game_id=game_id, deck=deck, max_players=MAX_PLAYERS)
        game.board[(0, 0)] = PlacedTile(tile_id=START_TILE_ID, rotation=0, x=0, y=0)
        game.message_log.append("Game created. Share the game ID with other players, then start when ready.")
        return game

    def add_player(self, game: GameState, name: Optional[str] = None, is_bot: bool = False) -> PlayerState:
        if game.status != "waiting":
            raise InvalidMoveError("This game has already started.")
        if len(game.players) >= game.max_players:
            raise InvalidMoveError(f"This game already has the maximum of {game.max_players} players.")
        player = PlayerState(
            id=uuid4().hex[:8],
            name=(name or f"Player {len(game.players) + 1}").strip() or f"Player {len(game.players) + 1}",
            color=PLAYER_COLORS[len(game.players)],
            is_bot=is_bot,
            bot_policy="basic_heuristic" if is_bot else None,
        )
        game.players.append(player)
        if game.host_player_id is None:
            game.host_player_id = player.id
            game.message_log.append(f"{player.name} joined as host.")
        else:
            game.message_log.append(f"{player.name} joined the game." if not is_bot else f"{player.name} bot joined the game.")
        if len(game.players) >= MIN_PLAYERS and len(game.players) < game.max_players:
            game.message_log.append("Host can start the game at any time.")
        if len(game.players) == game.max_players:
            game.message_log.append("Lobby is full. Host can start the game.")
        return player

    def start_game(self, game: GameState, player_id: str) -> None:
        if game.status != "waiting":
            raise InvalidMoveError("This game has already started.")
        if game.host_player_id != player_id:
            raise InvalidMoveError("Only the host can start the game.")
        if len(game.players) < MIN_PLAYERS:
            raise InvalidMoveError(f"At least {MIN_PLAYERS} players are required to start.")
        host = self._player_by_id(game, player_id)
        game.status = "active"
        game.message_log.append(f"{host.name} started the game.")
        self._prepare_turn(game)

    def submit_turn(
        self,
        game: GameState,
        *,
        player_id: str,
        x: int,
        y: int,
        rotation: int,
        feature_id: Optional[str] = None,
    ) -> None:
        self._require_active_game(game)
        player = self._current_player(game)
        if player.id != player_id:
            raise InvalidMoveError("It is not this player's turn.")
        if game.current_turn is None:
            raise InvalidMoveError("There is no active turn to play.")

        rotation = rotation % 4
        chosen_move = None
        for move in game.current_turn.legal_moves:
            if move["x"] == x and move["y"] == y and move["rotation"] == rotation:
                chosen_move = move
                break
        if chosen_move is None:
            raise InvalidMoveError("That placement is not legal for the current tile.")

        if feature_id is not None and feature_id not in {option["feature_id"] for option in chosen_move["meeple_options"]}:
            raise InvalidMoveError("That meeple placement is not legal for the selected tile placement.")

        placed_tile = PlacedTile(tile_id=game.current_turn.tile_id, rotation=rotation, x=x, y=y)
        tile_def = TILE_LIBRARY[placed_tile.tile_id]
        if feature_id is not None:
            if player.meeples_available <= 0:
                raise InvalidMoveError("This player has no meeples available.")
            feature = next(feature for feature in rotated_features(tile_def, rotation) if feature.id == feature_id)
            placed_tile.meeple = MeeplePlacement(player_id=player.id, feature_id=feature_id, kind=feature.kind)
            player.meeples_available -= 1

        game.board[(x, y)] = placed_tile
        self._score_after_placement(game, placed_tile)
        self._advance_turn(game)

    def serialize(self, game: GameState, viewer_player_id: Optional[str] = None) -> dict:
        current_player = self._current_player(game) if game.status == "active" and game.players else None
        current_turn = None
        if game.current_turn is not None:
            current_turn = {
                "tile_id": game.current_turn.tile_id,
                "tile": self.tile_summary(game.current_turn.tile_id),
                "legal_moves": game.current_turn.legal_moves,
            }
        occupied_x = [x for x, _ in game.board.keys()]
        occupied_y = [y for _, y in game.board.keys()]
        viewport = {
            "min_x": min(occupied_x) - 2,
            "max_x": max(occupied_x) + 2,
            "min_y": min(occupied_y) - 2,
            "max_y": max(occupied_y) + 2,
        }
        return {
            "game_id": game.game_id,
            "status": game.status,
            "host_player_id": game.host_player_id,
            "max_players": game.max_players,
            "min_players_to_start": MIN_PLAYERS,
            "players": [
                {
                    "id": player.id,
                    "name": player.name,
                    "color": player.color,
                    "is_bot": player.is_bot,
                    "bot_policy": player.bot_policy,
                    "score": player.score,
                    "meeples_available": player.meeples_available,
                }
                for player in game.players
            ],
            "board": [
                {
                    "x": tile.x,
                    "y": tile.y,
                    "rotation": tile.rotation,
                    "tile_id": tile.tile_id,
                    "tile": self.tile_summary(tile.tile_id),
                    "meeple": None
                    if tile.meeple is None
                    else {
                        "player_id": tile.meeple.player_id,
                        "feature_id": tile.meeple.feature_id,
                        "kind": tile.meeple.kind,
                    },
                }
                for tile in sorted(game.board.values(), key=lambda item: (item.y, item.x))
            ],
            "current_player_id": current_player.id if current_player else None,
            "viewer_player_id": viewer_player_id,
            "current_turn": current_turn,
            "remaining_tiles": len(game.deck),
            "discarded_tiles": len(game.discarded_tiles),
            "winner_ids": game.winner_ids,
            "messages": game.message_log[-12:],
            "viewport": viewport,
            "catalog": [self.tile_summary(tile_id) for tile_id in TILE_LIBRARY.keys()],
        }

    def tile_summary(self, tile_id: str) -> dict:
        tile = TILE_LIBRARY[tile_id]
        return {
            "id": tile.id,
            "name": tile.name,
            "image_path": f"/assets/img/tiles/{tile.image_name}",
            "edges": tile.edges,
            "features": [
                {
                    "id": feature.id,
                    "kind": feature.kind,
                    "edges": list(feature.edges),
                    "center": feature.center,
                    "score_bonus": feature.score_bonus,
                }
                for feature in tile.features
            ],
        }

    def _prepare_turn(self, game: GameState) -> None:
        while game.deck:
            tile_id = game.deck.pop(0)
            legal_moves = self._legal_moves(game, tile_id)
            if legal_moves:
                game.current_turn = CurrentTurn(tile_id=tile_id, legal_moves=legal_moves)
                current_player = self._current_player(game)
                game.message_log.append(f"{current_player.name}'s turn with {TILE_LIBRARY[tile_id].name}.")
                return
            game.discarded_tiles.append(tile_id)
            game.message_log.append(f"{TILE_LIBRARY[tile_id].name} was discarded because it had no legal placement.")
        self._finalize_game(game)

    def _advance_turn(self, game: GameState) -> None:
        if game.status != "active":
            return
        game.turn_index = (game.turn_index + 1) % len(game.players)
        self._prepare_turn(game)

    def _legal_moves(self, game: GameState, tile_id: str) -> List[dict]:
        positions = self._candidate_positions(game)
        legal_moves: List[dict] = []
        tile = TILE_LIBRARY[tile_id]
        for x, y in sorted(positions):
            for rotation in range(4):
                rotated_edge_map = rotate_edges(tile.edges, rotation)
                if not self._matches_neighbors(game, x, y, rotated_edge_map):
                    continue
                meeple_options = self._legal_meeple_options(game, tile_id, x, y, rotation)
                legal_moves.append(
                    {
                        "x": x,
                        "y": y,
                        "rotation": rotation,
                        "meeple_options": meeple_options,
                    }
                )
        return legal_moves

    def _candidate_positions(self, game: GameState) -> Set[Tuple[int, int]]:
        positions: Set[Tuple[int, int]] = set()
        for x, y in game.board.keys():
            for dx, dy in STEP_BY_DIRECTION.values():
                target = (x + dx, y + dy)
                if target not in game.board:
                    positions.add(target)
        return positions

    def _matches_neighbors(self, game: GameState, x: int, y: int, edges: Dict[str, str]) -> bool:
        has_neighbor = False
        for direction, (dx, dy) in STEP_BY_DIRECTION.items():
            neighbor = game.board.get((x + dx, y + dy))
            if neighbor is None:
                continue
            has_neighbor = True
            neighbor_edges = rotate_edges(TILE_LIBRARY[neighbor.tile_id].edges, neighbor.rotation)
            if edges[direction] != neighbor_edges[OPPOSITE_DIRECTION[direction]]:
                return False
        return has_neighbor

    def _legal_meeple_options(self, game: GameState, tile_id: str, x: int, y: int, rotation: int) -> List[dict]:
        tile = TILE_LIBRARY[tile_id]
        options: List[dict] = [{"feature_id": None, "kind": None, "label": "No meeple"}]
        placed = PlacedTile(tile_id=tile_id, rotation=rotation, x=x, y=y)
        for feature in rotated_features(tile, rotation):
            component = self._trace_feature_component(game, placed, feature.id)
            if any(item["meeple"] is not None for item in component["members"]):
                continue
            options.append(
                {
                    "feature_id": feature.id,
                    "kind": feature.kind,
                    "label": f"{'Farm' if feature.kind == 'field' else feature.kind.title()} ({feature.id})",
                }
            )
        return options

    def _score_after_placement(self, game: GameState, placed_tile: PlacedTile) -> None:
        seen: Set[Tuple[Tuple[int, int], str]] = set()
        tile = TILE_LIBRARY[placed_tile.tile_id]
        for feature in rotated_features(tile, placed_tile.rotation):
            key = ((placed_tile.x, placed_tile.y), feature.id)
            if key in seen or feature.kind not in {"city", "road"}:
                continue
            component = self._trace_feature_component(game, placed_tile, feature.id)
            for member in component["feature_keys"]:
                seen.add(member)
            if component["is_complete"]:
                self._award_component(game, component, completed=True)

        monastery_targets = {(placed_tile.x, placed_tile.y)}
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                monastery_targets.add((placed_tile.x + dx, placed_tile.y + dy))
        for target in monastery_targets:
            tile_at_target = game.board.get(target)
            if tile_at_target is None or tile_at_target.meeple is None or tile_at_target.meeple.kind != "monastery":
                continue
            if self._is_monastery_complete(game, tile_at_target.x, tile_at_target.y):
                component = {
                    "kind": "monastery",
                    "members": [{"position": target, "meeple": tile_at_target.meeple}],
                    "score": 9,
                }
                self._award_component(game, component, completed=True)

    def _award_component(self, game: GameState, component: dict, *, completed: bool) -> None:
        meeples = [item["meeple"] for item in component["members"] if item["meeple"] is not None]
        if not meeples:
            return
        counts = Counter(meeple.player_id for meeple in meeples)
        highest = max(counts.values())
        winners = [player_id for player_id, count in counts.items() if count == highest]
        points = component["score"]
        for player in game.players:
            if player.id in winners:
                player.score += points
        if component["kind"] != "field":
            for item in component["members"]:
                meeple = item["meeple"]
                if meeple is None:
                    continue
                tile = game.board[item["position"]]
                if tile.meeple is not None:
                    tile.meeple = None
                    owner = self._player_by_id(game, meeple.player_id)
                    owner.meeples_available += 1
        kind = component["kind"]
        if completed:
            game.message_log.append(f"Completed {kind} for {points} point(s).")

    def _trace_feature_component(self, game: GameState, seed_tile: PlacedTile, feature_id: str) -> dict:
        queue = deque([((seed_tile.x, seed_tile.y), feature_id)])
        visited: Set[Tuple[Tuple[int, int], str]] = set()
        members: List[dict] = []
        tiles_seen: Set[Tuple[int, int]] = set()
        feature_keys: Set[Tuple[Tuple[int, int], str]] = set()
        kind: Optional[str] = None
        score_bonus = 0
        is_complete = True
        adjacent_completed_cities: Set[frozenset[Tuple[Tuple[int, int], str]]] = set()

        while queue:
            position, current_feature_id = queue.popleft()
            if (position, current_feature_id) in visited:
                continue
            visited.add((position, current_feature_id))
            feature_keys.add((position, current_feature_id))
            tile = self._tile_at_position(game, seed_tile, position)
            if tile is None:
                continue
            tile_def = TILE_LIBRARY[tile.tile_id]
            feature = next(item for item in rotated_features(tile_def, tile.rotation) if item.id == current_feature_id)
            kind = feature.kind
            score_bonus += feature.score_bonus
            members.append({"position": position, "meeple": tile.meeple if tile.meeple and tile.meeple.feature_id == current_feature_id else None})
            tiles_seen.add(position)
            if feature.center and feature.kind == "monastery":
                continue
            if feature.kind == "field":
                for city_feature_id in feature.adjacent_cities:
                    city_component = self._trace_feature_component(game, tile, city_feature_id)
                    if city_component["is_complete"]:
                        adjacent_completed_cities.add(frozenset(city_component["feature_keys"]))
            for port in feature.edges:
                dx, dy = STEP_BY_PORT[port]
                neighbor_position = (position[0] + dx, position[1] + dy)
                neighbor_tile = self._tile_at_position(game, seed_tile, neighbor_position)
                if neighbor_tile is None:
                    if feature.kind in {"road", "city"}:
                        is_complete = False
                    continue
                neighbor_def = TILE_LIBRARY[neighbor_tile.tile_id]
                neighbor_features = rotated_features(neighbor_def, neighbor_tile.rotation)
                match = None
                for neighbor_feature in neighbor_features:
                    if neighbor_feature.kind != feature.kind:
                        continue
                    if OPPOSITE_PORT[port] in neighbor_feature.edges:
                        match = neighbor_feature
                        break
                if match is None:
                    if feature.kind in {"road", "city"}:
                        is_complete = False
                    continue
                queue.append((neighbor_position, match.id))

        score = 0
        if kind == "road":
            score = len(tiles_seen)
        elif kind == "city":
            score = len(tiles_seen) * 2 + score_bonus * 2 if is_complete else len(tiles_seen) + score_bonus
        elif kind == "field":
            score = len(adjacent_completed_cities) * 3
        return {
            "kind": kind,
            "members": members,
            "score": score,
            "is_complete": is_complete,
            "feature_keys": feature_keys,
            "adjacent_completed_cities": adjacent_completed_cities,
        }

    def _is_monastery_complete(self, game: GameState, x: int, y: int) -> bool:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (x + dx, y + dy) not in game.board:
                    return False
        return True

    def _finalize_game(self, game: GameState) -> None:
        game.status = "finished"
        seen_features: Set[Tuple[Tuple[int, int], str]] = set()
        seen_fields: Set[Tuple[Tuple[int, int], str]] = set()
        for tile in list(game.board.values()):
            if tile.meeple is None:
                continue
            if tile.meeple.kind == "monastery":
                score = sum(
                    1
                    for dx in (-1, 0, 1)
                    for dy in (-1, 0, 1)
                    if (tile.x + dx, tile.y + dy) in game.board
                )
                owner = self._player_by_id(game, tile.meeple.player_id)
                owner.score += score
                owner.meeples_available += 1
                tile.meeple = None
                continue
            if tile.meeple.kind == "field":
                feature_key = ((tile.x, tile.y), tile.meeple.feature_id)
                if feature_key in seen_fields:
                    continue
                component = self._trace_feature_component(game, tile, tile.meeple.feature_id)
                seen_fields.update(component["feature_keys"])
                self._award_component(game, component, completed=False)
                continue
            feature_key = ((tile.x, tile.y), tile.meeple.feature_id)
            if feature_key in seen_features:
                continue
            component = self._trace_feature_component(game, tile, tile.meeple.feature_id)
            seen_features.update(component["feature_keys"])
            self._award_component(game, component, completed=False)

        high_score = max((player.score for player in game.players), default=0)
        game.winner_ids = [player.id for player in game.players if player.score == high_score]
        game.current_turn = None
        game.message_log.append("Game finished.")

    def _player_by_id(self, game: GameState, player_id: str) -> PlayerState:
        for player in game.players:
            if player.id == player_id:
                return player
        raise InvalidMoveError("Player not found.")

    def _tile_at_position(self, game: GameState, seed_tile: PlacedTile, position: Tuple[int, int]) -> Optional[PlacedTile]:
        if (seed_tile.x, seed_tile.y) == position:
            return game.board.get(position, seed_tile)
        return game.board.get(position)

    def _current_player(self, game: GameState) -> PlayerState:
        return game.players[game.turn_index % len(game.players)]

    def _require_active_game(self, game: GameState) -> None:
        if game.status == "waiting":
            raise InvalidMoveError("The host must start the game once at least two players have joined.")
        if game.status == "finished":
            raise InvalidMoveError("This game has already finished.")
