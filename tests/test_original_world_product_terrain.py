"""Real, persistent sparse terrain, collision, rendering and finite resources."""
from __future__ import annotations

from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_product_terrain import (
    TerrainAction, create_terrain, chunk_key, cell_at,
    chunk_cells, step_terrain, terrain_save, terrain_restore,
    validate_terrain, _base_cell,
)

DESIGN = "a" * 64


def do(world, verb, x=None, y=None, amount=1):
    if x is None:
        x, y = world.position
    return step_terrain(world, TerrainAction(verb, x, y, amount))[0]


def test_sparse_negative_chunks_and_reproducible_cells() -> None:
    s = create_terrain(DESIGN)
    assert chunk_key(-1, -1) == (-1, -1)
    assert chunk_key(-32, -32) == (-1, -1)
    assert chunk_key(-33, -33) == (-2, -2)
    assert chunk_key(32, 31) == (1, 0)
    assert cell_at(s, 1234, -5678) == cell_at(create_terrain(DESIGN), 1234, -5678)
    assert len(chunk_cells(s, 0, 0)) == 32**2
    assert len(s.edits) == 0
    assert cell_at(s, 0, 0).kind == "meadow"


def test_actual_finite_terrain_harvest_and_non_minting_regression() -> None:
    s = create_terrain(DESIGN)
    assert s.lumber == 3 and s.masonry == 3
    s = do(s, "chop", amount=2)
    assert s.lumber == 5 and cell_at(s, 0, 0).wood == 1
    s = do(s, "chop")
    assert cell_at(s, 0, 0).wood == 0
    with pytest.raises(FoundationError):
        do(s, "chop")
    s = do(s, "mine", amount=2)
    assert s.masonry == 5 and cell_at(s, 0, 0).stone == 0
    with pytest.raises(FoundationError):
        do(s, "mine")
    s = do(s, "forage", amount=3)
    assert cell_at(s, 0, 0).food == 0
    s = do(s, "draw", amount=2)
    assert cell_at(s, 0, 0).water == 0
    assert terrain_restore(terrain_save(s)) == s


def test_building_requires_material_and_persists_on_exact_tile() -> None:
    s = create_terrain(DESIGN)
    s = do(s, "build_hearth")
    assert s.shelter == 1
    assert s.lumber == 1 and s.masonry == 2
    assert cell_at(s, 0, 0).building == "hearth"
    with pytest.raises(FoundationError):
        do(s, "build_mill")
    before = s.energy
    s = do(s, "end_turn", x=0, y=0)
    assert s.turns == 1 and s.energy == before + 1


def test_real_terrain_collision_requires_bridge_or_bounded_jump() -> None:
    s = create_terrain(DESIGN)
    hazard = None
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        c = cell_at(s, dx, dy)
        if c.blocking:
            hazard = (dx, dy)
            break
    if hazard is None:
        # Choose another deterministic design with adjacent marsh or cliff.
        for i in range(1, 128):
            trial = create_terrain(f"{i:064x}")
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if cell_at(trial, dx, dy).blocking:
                    s, hazard = trial, (dx, dy)
                    break
            if hazard is not None:
                break
    assert hazard is not None
    with pytest.raises(FoundationError):
        do(s, "walk", *hazard)
    after = do(s, "bridge", *hazard)
    assert after.lumber == s.lumber - 2
    assert after.masonry == s.masonry - 1
    assert cell_at(after, *hazard).bridge
    # A high edge may still require jumping; the bridge removes solid collision.
    result = do(after, "jump", *hazard)
    assert result.position == hazard


def test_walk_requires_true_grid_adjacency_not_teleport_or_diagonal() -> None:
    s = create_terrain(DESIGN)
    for target in ((5, 0), (1, 1), (-2, -2)):
        with pytest.raises(FoundationError):
            do(s, "walk", *target)


def test_sparse_overlay_does_not_mutate_other_chunk_resources() -> None:
    s = create_terrain(DESIGN)
    remote_before = cell_at(s, 1025, -2048)
    s = do(s, "chop")
    assert cell_at(s, 1025, -2048) == remote_before
    assert len(s.edits) == 1
    assert s.events == 1
    assert s.event_head != "0" * 64


def test_tampering_with_natural_stock_cannot_create_resources_from_edits() -> None:
    s = do(create_terrain(DESIGN), "chop")
    bad = replace(s, edits=tuple(replace(e, wood=500) for e in s.edits))
    with pytest.raises(FoundationError):
        validate_terrain(bad)
    corrupted = json.loads(terrain_save(s))
    corrupted["payload"]["state"]["lumber"] = 999
    with pytest.raises(FoundationError):
        terrain_restore(json.dumps(corrupted))


def test_invalid_grid_bounds_type_and_extra_actions_fail_closed() -> None:
    s = create_terrain(DESIGN)
    for action in (
        TerrainAction("walk", 1, 1),
        TerrainAction("walk", 1 << 25, 0),
        TerrainAction("mine", 0, 0, True),
        TerrainAction("fly", 0, 0),
        TerrainAction("forage", 0, 0, 4),
    ):
        old = asdict(s)
        with pytest.raises(FoundationError):
            step_terrain(s, action)
        assert asdict(s) == old
