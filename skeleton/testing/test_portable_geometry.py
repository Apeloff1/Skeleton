"""Deterministic spatial geometry tests for original game port targets."""
from fractions import Fraction
import pytest
from skeleton.ai.game_builder.portable_kernels.geometry import (
    GeometryError, walkable_tile_neighbors, bresenham_line, line_of_sight,
    flood_fill, distance_field, astar_path, rect_intersects, swept_aabb_hit,
    shelf_pack_rectangles, camera_clamp,
)

def test_walkable_neighbors_ordering_and_wall_bounds():
    grid=("#####","#S..#","#.#G#","#####")
    assert walkable_tile_neighbors(grid,(1,1))==((2,1),(1,2))
    with pytest.raises(GeometryError):
        walkable_tile_neighbors(grid,(0,0))
    with pytest.raises(GeometryError):
        walkable_tile_neighbors(("x",),(0,0))
