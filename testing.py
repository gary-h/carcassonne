from fastapi.testclient import TestClient

from backend.main import app
from backend.engine.models import GameState, MeeplePlacement, PlacedTile, PlayerState
from backend.storage.game_store import game_store


def main() -> None:
    client = TestClient(app)

    bot_catalog = client.get("/games/bots")
    bot_catalog.raise_for_status()
    bot_slugs = {bot["slug"] for bot in bot_catalog.json()["bots"]}
    assert {"easy", "medium", "hard"}.issubset(bot_slugs)
    assert "template" not in bot_slugs

    create = client.post("/games/create", json={})
    create.raise_for_status()
    game_id = create.json()["game_id"]
    print("Created game:", game_id)

    join_a = client.post(f"/games/{game_id}/join", json={"name": "Alice"})
    join_a.raise_for_status()
    player_a = join_a.json()["player_id"]

    join_b = client.post(f"/games/{game_id}/join", json={"name": "Bob"})
    join_b.raise_for_status()
    player_b = join_b.json()["player_id"]
    join_c = client.post(f"/games/{game_id}/join", json={"name": "Cara"})
    join_c.raise_for_status()
    join_d = client.post(f"/games/{game_id}/join", json={"name": "Dan"})
    join_d.raise_for_status()
    join_e = client.post(f"/games/{game_id}/join", json={"name": "Eve"})
    join_e.raise_for_status()
    print("Players:", player_a, player_b, join_c.json()["player_id"], join_d.json()["player_id"], join_e.json()["player_id"])

    join_f = client.post(f"/games/{game_id}/join", json={"name": "Frank"})
    assert join_f.status_code == 400

    start = client.post(f"/games/{game_id}/start", json={"player_id": player_a})
    start.raise_for_status()

    state = client.get(f"/games/{game_id}", params={"player_id": player_a}).json()
    for turn in range(8):
        if state["status"] != "active":
            break
        move = state["current_turn"]["legal_moves"][0]
        response = client.post(
            f"/moves/{game_id}/submit",
            json={
                "player_id": state["current_player_id"],
                "x": move["x"],
                "y": move["y"],
                "rotation": move["rotation"],
                "feature_id": None,
            },
        )
        response.raise_for_status()
        state = response.json()["game"]
        print(f"Turn {turn + 1}: {state['messages'][-1]}")

    print("Scores:", [(player["name"], player["score"]) for player in state["players"]])

    # Regression check: the engine must not allow a road edge to touch the start tile's city edge.
    regression_game = game_store.engine.create_game(seed=1)
    game_store.engine.add_player(regression_game, "A")
    game_store.engine.add_player(regression_game, "B")
    game_store.engine.start_game(regression_game, regression_game.host_player_id)
    assert regression_game.current_turn is not None
    if regression_game.current_turn.tile_id == "curve":
        illegal = [
            move
            for move in regression_game.current_turn.legal_moves
            if (move["x"], move["y"]) == (0, -1)
        ]
        assert not illegal, "Illegal city-road match exposed above the start tile."

    # Endgame farm scoring: one farmer adjacent to one completed city should score 3.
    farm_game = GameState(game_id="farm-check")
    farm_game.players.extend(
        [
            PlayerState(id="farmer", name="Farmer", color="red"),
            PlayerState(id="other", name="Other", color="blue"),
        ]
    )
    farm_game.status = "finished"
    base_field_id = next(
        feature["id"]
        for feature in game_store.engine.tile_summary("city_cap")["features"]
        if feature["kind"] == "field"
    )
    farm_game.board[(0, 0)] = PlacedTile(
        tile_id="city_cap",
        rotation=0,
        x=0,
        y=0,
        meeple=MeeplePlacement(player_id="farmer", feature_id=base_field_id, kind="field"),
    )
    farm_game.players[0].meeples_available -= 1
    farm_game.board[(0, -1)] = PlacedTile(tile_id="city_cap", rotation=2, x=0, y=-1)
    game_store.engine._finalize_game(farm_game)
    assert farm_game.players[0].score == 3, "Farm scoring should award 3 points per completed adjacent city."

    # Bot path: creating a mixed game with bots should allow humans to join and bots to respond.
    bot_create = client.post("/games/create", json={"bot_counts": {"easy": 1, "medium": 1, "hard": 1}})
    bot_create.raise_for_status()
    bot_game_id = bot_create.json()["game_id"]
    bot_join = client.post(f"/games/{bot_game_id}/join", json={"name": "Solo"})
    bot_join.raise_for_status()
    bot_player_id = bot_join.json()["player_id"]
    bot_state = bot_join.json()["game"]
    bots = [player for player in bot_state["players"] if player["is_bot"]]
    assert len(bots) == 3, "Expected exactly three bot players in a mixed bot game."
    assert {player["bot_policy"] for player in bots} == {"easy", "medium", "hard"}

    extra_human = client.post(f"/games/{bot_game_id}/join", json={"name": "Friend"})
    extra_human.raise_for_status()

    bot_start = client.post(f"/games/{bot_game_id}/start", json={"player_id": bot_player_id})
    bot_start.raise_for_status()
    bot_state = bot_start.json()["game"]
    human_move = bot_state["current_turn"]["legal_moves"][0]
    bot_response = client.post(
        f"/moves/{bot_game_id}/submit",
        json={
            "player_id": bot_player_id,
            "x": human_move["x"],
            "y": human_move["y"],
            "rotation": human_move["rotation"],
            "feature_id": None,
        },
    )
    bot_response.raise_for_status()
    post_bot_state = bot_response.json()["game"]
    assert len(post_bot_state["board"]) >= len(bot_state["board"]) + 2, "Bot should make its move immediately after the human move."

    # Bot-only path: creating with only bots should auto-start and advance without a human player.
    bot_only_create = client.post("/games/create", json={"bot_counts": {"easy": 1, "hard": 1}, "bot_only": True})
    bot_only_create.raise_for_status()
    bot_only_state = bot_only_create.json()["game"]
    assert bot_only_state["status"] == "active"
    assert len(bot_only_state["players"]) == 2
    assert all(player["is_bot"] for player in bot_only_state["players"])
    assert bot_only_state["current_turn"] is not None
    before_tiles = len(bot_only_state["board"])
    advanced_state = client.get(f"/games/{bot_only_create.json()['game_id']}").json()
    assert len(advanced_state["board"]) > before_tiles or advanced_state["status"] == "finished"


if __name__ == "__main__":
    main()
