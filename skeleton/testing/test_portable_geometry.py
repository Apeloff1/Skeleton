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

def test_bresenham_line_exact_integer_pixel_coverage():
    assert bresenham_line((0,0),(3,0))==((0,0),(1,0),(2,0),(3,0))
    assert bresenham_line((0,0),(3,3))==((0,0),(1,1),(2,2),(3,3))
    assert bresenham_line((3,0),(0,0))==tuple(reversed(bresenham_line((0,0),(3,0))))
    with pytest.raises(GeometryError):
        bresenham_line((-1,0),(0,0))
