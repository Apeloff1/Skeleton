import pytest

from skeleton.forge.ai_builder.procgen import (BspConfig, GraphConfig, ProcgenError, Streams, bsp_layout,
                                               graph_layout, lock_gates, place_locks, solve, solve_layout)
from skeleton.forge.ai_builder.procgen.layout import Rect, bfs_depths, carve_l


def bsp(seed, **kw):
    return bsp_layout(Streams(seed).stream("dungeon/bsp"), BspConfig(**kw))


def graph(seed, **kw):
    return graph_layout(Streams(seed).stream("dungeon/graph"), GraphConfig(**kw))


@pytest.mark.parametrize("make", [bsp, graph])
def test_layout_deterministic_and_seed_sensitive(make):
    a, b, c = make(5), make(5), make(6)
    assert a.digest() == b.digest() and a.tiles() == b.tiles()
    assert a.digest() != c.digest()


@pytest.mark.parametrize("make", [bsp, graph])
@pytest.mark.parametrize("seed", range(6))
def test_layout_connected_rooms_disjoint_in_bounds(make, seed):
    lay = make(seed)
    adj = lay.adjacency()
    assert len(bfs_depths(adj, lay.start)) == len(lay.rooms)
    rects = [r.rect for r in lay.rooms]
    for i, r in enumerate(rects):
        assert r.x2 <= lay.width and r.y2 <= lay.height
        for o in rects[i + 1:]:
            assert not r.intersects(o)
    assert lay.critical_path[0] == lay.start and lay.critical_path[-1] == lay.goal
    assert lay.room(lay.goal).depth == len(lay.critical_path) - 1
    # goal is a farthest room from start
    assert lay.room(lay.goal).depth == max(r.depth for r in lay.rooms)
    tiles = lay.tiles()
    assert len(tiles) == lay.height and all(len(row) == lay.width for row in tiles)
    assert sum(row.count("S") for row in tiles) == 1 and sum(row.count("G") for row in tiles) == 1


def test_bsp_config_validation():
    with pytest.raises(ProcgenError):
        BspConfig(min_leaf=3)
    with pytest.raises(ProcgenError):
        GraphConfig(rooms=1)


def test_carve_l_connects_endpoints():
    cells = carve_l((1, 1), (5, 4), True)
    assert cells[0] == (1, 1) and cells[-1] == (5, 4) and len(cells) == len(set(cells)) == 8
    for (x0, y0), (x1, y1) in zip(cells, cells[1:]):
        assert abs(x0 - x1) + abs(y0 - y1) == 1


def test_rect_validation():
    with pytest.raises(ProcgenError):
        Rect(0, 0, 0, 3)


@pytest.mark.parametrize("make", [bsp, graph])
@pytest.mark.parametrize("seed", range(8))
def test_keys_always_solvable(make, seed):
    lay = make(seed)
    locked = place_locks(lay, Streams(seed).stream("dungeon/keys"), 3)
    sol = solve_layout(locked)
    assert sol.solvable and not sol.unreachable
    assert set(sol.order) <= set(locked.locks().values())
    assert locked.goal not in locked.keys.values()
    gates = lock_gates(locked)
    assert set(gates) == set(locked.locks().values())


def test_keys_on_critical_path_in_order():
    lay = place_locks(bsp(1), Streams(1).stream("k"), 3)
    path = lay.critical_path
    idx = {tuple(sorted(p)): i for i, p in enumerate(zip(path, path[1:]))}
    order = [k for _, k in sorted((idx[e], k) for e, k in lay.locks().items())]
    assert order == sorted(order)  # key1 gates earlier than key2 ...


def test_locks_prefer_gating_edges():
    gated = 0
    for seed in range(10):
        lay = place_locks(bsp(seed, loops=0.0), Streams(seed).stream("k"), 2)  # pure tree: every edge gates
        assert all(v > 0 for v in lock_gates(lay).values())
        gated += len(solve_layout(lay).order)
    assert gated > 0


def test_solver_detects_unsolvable():
    adj = {"a": ["b"], "b": ["a", "c"], "c": ["b"]}
    sol = solve(adj, "a", "c", {("b", "c"): "k1"}, {"k1": "c"})  # key behind its own door
    assert not sol.solvable and sol.stuck_on == ("k1",)
    ok = solve(adj, "a", "c", {("b", "c"): "k1"}, {"k1": "a"})
    assert ok.solvable and ok.order == ("k1",) and ok.steps == 2


def test_zero_locks_is_noop():
    lay = bsp(2)
    assert place_locks(lay, Streams(2).stream("k"), 0).locks() == {}
