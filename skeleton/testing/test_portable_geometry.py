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

def test_line_of_sight_blocks_wall_and_bounds_endpoints():
    grid=("S..G",".##.","....")
    assert line_of_sight(grid,(0,0),(3,0))
    assert not line_of_sight(grid,(0,2),(3,0))
    with pytest.raises(GeometryError):
        line_of_sight(grid,(0,0),(10,10))

def test_flood_fill_excludes_isolated_rooms_and_orders_coordinates():
    grid=("#####","#S#G#","#.#.#","#####")
    assert flood_fill(grid,(1,1))==((1,1),(1,2))
    assert flood_fill(grid,(3,1))==((3,1),(3,2))
    with pytest.raises(GeometryError):
        flood_fill(grid,(2,1))

def test_distance_field_routes_around_hard_walls():
    grid=("S..","##.","..G")
    assert distance_field(grid,(0,0))==(
        (0,1,2),(-1,-1,3),(6,5,4))
    with pytest.raises(GeometryError):
        distance_field(grid,(0,1))

def test_astar_is_shortest_deterministic_and_refuses_wall_endpoints():
    grid=("S..","##.","..G")
    route=astar_path(grid,(0,0),(2,2))
    assert route[0]==(0,0) and route[-1]==(2,2)
    assert len(route)==distance_field(grid,(0,0))[2][2]+1
    assert route==astar_path(grid,(0,0),(2,2))
    assert astar_path(("S#G",),(0,0),(2,0))==()
    with pytest.raises(GeometryError):
        astar_path(grid,(1,1),(2,2))

def test_rect_collision_uses_half_open_nonpenetrating_boundaries():
    assert rect_intersects((0,0,3,3),(2,2,3,3))
    assert not rect_intersects((0,0,2,2),(2,0,2,2))
    assert not rect_intersects((0,0,2,2),(0,2,2,2))
    with pytest.raises(GeometryError):
        rect_intersects((0,0,0,2),(0,0,1,1))

def test_swept_aabb_reports_exact_fraction_for_contact():
    assert swept_aabb_hit((0,0,2,2),(4,0,2,2),4,0)==Fraction(1,2)
    assert swept_aabb_hit((0,0,2,2),(0,4,2,2),0,4)==Fraction(1,2)
    assert swept_aabb_hit((0,0,2,2),(2,0,2,2),-4,0) is None
    assert swept_aabb_hit((0,0,2,2),(1,1,2,2),3,3)==Fraction(0)
    with pytest.raises(GeometryError):
        swept_aabb_hit((0,0,2,2),(4,0,2,2),4096,0)

def test_sprite_atlas_packing_is_deterministic_and_nonoverlapping():
    sizes=((8,8),(8,16),(16,8),(4,4))
    placed=shelf_pack_rectangles(sizes,24)
    assert placed==((0,0,8,8),(8,0,8,16),(0,16,16,8),(16,16,4,4))
    assert all(not rect_intersects(a,b) for i,a in enumerate(placed) for b in placed[i+1:])
    with pytest.raises(GeometryError):
        shelf_pack_rectangles(((32,8),),16)
    with pytest.raises(GeometryError):
        shelf_pack_rectangles(((8,512),)*8,8)

def test_camera_clamp_supports_large_world_and_small_viewports():
    assert camera_clamp((50,40),(100,80),(20,10))==(40,35)
    assert camera_clamp((99,79),(100,80),(20,10))==(80,70)
    assert camera_clamp((0,0),(100,80),(20,10))==(0,0)
    assert camera_clamp((5,5),(10,10),(20,20))==(0,0)
    with pytest.raises(GeometryError):
        camera_clamp((100,0),(100,80),(20,10))
