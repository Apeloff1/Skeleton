"""Disk-backed infinite-style frontier behavior and bounded execution tests."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.game.generation.original_world_frontier import (
    ACTIONS, CHUNK, MAX_COORD, MIN_COORD, FrontierAction, FrontierError,
    SparseFrontier, chunk_of, generated_tile,
)


def play(world, verb, option="", amount=1):
    return world.act(FrontierAction(verb, option, amount))


def advance(world, turns=1):
    for _ in range(turns):
        play(world, "end_turn")


def test_coordinate_space_is_sparse_not_preallocated() -> None:
    assert CHUNK == 16
    assert chunk_of(-1, -1) == (-1, -1)
    assert chunk_of(16, 16) == (1, 1)
    assert generated_tile("seed", 12, -25) == generated_tile("seed", 12, -25)
    assert generated_tile("seed", 12, -25) != generated_tile("seed", 13, -25)
    assert generated_tile("seed", MAX_COORD, MIN_COORD).x == MAX_COORD
    with pytest.raises(FrontierError):
        generated_tile("seed", MAX_COORD + 1, 0)
    with pytest.raises(FrontierError):
        generated_tile("seed", 0, MIN_COORD - 1)


@pytest.mark.parametrize("world_id", [
    "topology-02", "ecology-03", "civilization-01", "serenity-05",
])
def test_four_authored_laws_support_streamed_terrain(world_id) -> None:
    with SparseFrontier(":memory:", world_id, "streaming") as world:
        assert world.player().x == 0
        assert world.player().y == 0
        assert world.visited_count() == 1
        assert world.modified_count() == 0
        assert len(world.nearby_map(3).splitlines()) == 8
        assert len(world.passages()) >= 2
        assert world.tile() == generated_tile("streaming", 0, 0)
        assert world.world_id == world_id


def test_movement_crosses_chunk_boundaries_and_persists_discovery(tmp_path) -> None:
    path = tmp_path / "frontier.sqlite3"
    with SparseFrontier(path, "serenity-05", "adventure") as world:
        for i in range(18):
            if world.player().actions == 0:
                advance(world)
            play(world, "move", "east")
        assert world.player().x == 18
        assert world.visited_count() == 19
        assert world.modified_count() == 0
        assert chunk_of(world.player().x, 0) == (1, 0)
        first_head = world.player().event_head
    with SparseFrontier(path, "serenity-05", "adventure") as loaded:
        assert loaded.player().x == 18
        assert loaded.visited_count() == 19
        assert loaded.player().event_head == first_head
        with pytest.raises(FrontierError):
            SparseFrontier(path, "serenity-05", "different-seed")


def test_harvesting_depletes_specific_tile_and_keeps_other_tiles_independent() -> None:
    with SparseFrontier(":memory:", "serenity-05", "scarcity") as game:
        start = game.tile()
        play(game, "forage", amount=3)
        assert game.tile().food == start.food - 3
        assert game.player().food == 6
        play(game, "move", "east")
        assert game.tile() == generated_tile("scarcity", 1, 0)
        play(game, "move", "west")
        assert game.tile().food == start.food - 3
        assert game.modified_count() == 1
        assert game.visited_count() == 2


def test_lazy_regeneration_requires_elapsed_world_time() -> None:
    with SparseFrontier(":memory:", "serenity-05", "regen") as game:
        food = game.tile().food
        while game.tile().food > 0 and game.player().actions > 0:
            play(game, "forage")
        depleted = game.tile().food
        advance(game, 3)
        assert game.tile().food == depleted
        advance(game, 1)
        assert game.tile().food >= min(food, depleted + 1)


def test_civic_settlement_requires_honored_resource_backed_oath() -> None:
    with SparseFrontier(":memory:", "civilization-01", "civic") as game:
        with pytest.raises(FrontierError):
            play(game, "settle")
        play(game, "pledge")
        play(game, "fulfill")
        play(game, "settle")
        assert game.tile().structure == "village"
        assert game.player().honored == 1
        assert game.player().promises == 0
        with pytest.raises(FrontierError):
            play(game, "settle")


def test_seamless_topology_has_stable_backbone_and_shifting_routes() -> None:
    with SparseFrontier(":memory:", "topology-02", "maze") as game:
        assert "east" in game.passages()
        assert "west" in game.passages()
        assert "north" in game.passages()
        assert "south" in game.passages()
        advance(game, 1)
        assert "east" in game.passages()
        assert "west" in game.passages()
        assert "north" in game.passages()  # fixed every fifth x column
        play(game, "move", "east")
        choices = set(game.passages())
        assert {"east", "west"}.issubset(choices)


def test_ecology_rain_conservation_and_quilt_play() -> None:
    with SparseFrontier(":memory:", "ecology-03", "wet") as game:
        play(game, "redirect_rain", "west", 2)
        assert game.player().rain_west == 8
        assert game.player().rain_east == 4
        advance(game, 20)
        assert game.player().rain_west + game.player().rain_east == 12
    with SparseFrontier(":memory:", "serenity-05", "cozy") as game:
        play(game, "weave", amount=2)
        assert game.player().quilt == 4
        assert game.player().wood == 1
        with pytest.raises(FrontierError):
            play(game, "redirect_rain", "west")


def test_crop_and_resource_repair_realize_local_changes() -> None:
    with SparseFrontier(":memory:", "serenity-05", "farm") as game:
        play(game, "plant", amount=2)
        assert game.tile().crop == 2
        play(game, "irrigate")
        assert game.tile().fertility >= 3
        play(game, "harvest")
        assert game.tile().crop == 1
        assert game.player().food == 5
        advance(game)
        assert game.tile().crop == 1


def test_every_player_action_has_a_bound_effect_or_gated_precondition() -> None:
    assert len(ACTIONS) == 21
    for verb in ACTIONS:
        with SparseFrontier(":memory:", "serenity-05", "action:"+verb) as game:
            if verb == "move":
                action = FrontierAction("move", "east")
            elif verb == "redirect_rain":
                action = FrontierAction("redirect_rain", "west")
            else:
                action = FrontierAction(verb)
            before = game.player()
            if verb in {"irrigate", "harvest", "repair", "fulfill",
                        "redirect_rain"}:
                with pytest.raises(FrontierError):
                    game.act(action)
            else:
                receipt = game.act(action)
                assert receipt.event_count == before.event_count + 1
                assert receipt.event_id == game.player().event_head


def test_invalid_action_does_not_mutate_sqlite(tmp_path) -> None:
    with SparseFrontier(tmp_path / "s.db", "ecology-03", "fail-closed") as world:
        before = world.player()
        prior = world.tile()
        bad = (
            FrontierAction("missing"),
            FrontierAction("forage", amount=True),
            FrontierAction("forage", amount=0),
            FrontierAction("forage", amount=4),
            FrontierAction("move", option="teleport"),
            FrontierAction("redirect_rain", option="unknown"),
        )
        for action in bad:
            with pytest.raises(FrontierError):
                world.act(action)
            assert world.player() == before
            assert world.tile() == prior
        assert world.modified_count() == 0


def test_repeat_simulation_produces_exact_same_chain() -> None:
    receipts = []
    for _ in range(2):
        with SparseFrontier(":memory:", "serenity-05", "replay") as game:
            chain = []
            for action in (
                FrontierAction("weave", amount=2),
                FrontierAction("forage"),
                FrontierAction("move", "east"),
                FrontierAction("end_turn"),
                FrontierAction("scout"),
                FrontierAction("move", "south"),
            ):
                chain.append(game.act(action).event_id)
            receipts.append((chain, game.player(), game.tile()))
    assert receipts[0] == receipts[1]


def test_runtime_rejects_unimplemented_catalog_worlds_and_invalid_seeds() -> None:
    with pytest.raises(FrontierError):
        SparseFrontier(":memory:", "time-01", "seed")
    with pytest.raises(FrontierError):
        SparseFrontier(":memory:", "serenity-05", "")
