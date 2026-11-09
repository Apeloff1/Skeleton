"""Wally's minor follow-ups on #4593: gated rank, capped path look-ahead, tile fallback flag."""
import pytest

from skeleton.frontier.worldsim.navigation import NavGrid
from skeleton.frontier.worldsim.quality_arena import (
    TileLayoutError, WorldCandidate, rank, score, tile_layout)
from skeleton.frontier.worldsim.streaming import StreamBudget, StreamingError, plan_tick


def _cand(wid, rows, objectives, kinds=("a",) * 9, **kw):
    return WorldCandidate(wid, NavGrid.from_rows(rows), (0, 0), objectives, tuple(kinds), 1.0, **kw)


def test_rank_unreachable_world_scores_zero_and_ranks_last():
    ok = _cand("ok", ["...", "...", "..."], ((2, 2),))
    bad = _cand("bad", ["..#", ".#.", "#.."], ((2, 2),))
    out = rank([bad, ok], 10.0)
    assert [s.world_id for s in out] == ["ok", "bad"]
    assert out[1].total == 0.0 and not out[1].passed
    assert "unreachable_objectives" in out[1].failures


def test_rank_accepts_gates_and_keeps_order_for_clean_worlds():
    from skeleton.frontier.worldsim.navigation import GateSpec
    a = _cand("a", ["...", "...", "..."], ((2, 2),))
    b = _cand("b", ["...", "...", "..."], ((1, 1),))
    out = rank([b, a], 10.0, gates=GateSpec())
    assert all(s.passed for s in out)
    assert [s.world_id for s in out] == sorted([s.world_id for s in out], key=lambda w: w)


def _sizes(n):
    return {(x, y): 1 for x in range(-n, n + 1) for y in range(-n, n + 1)}


def test_path_lookahead_caps_far_path_cells():
    b = StreamBudget(10_000, 1_000, 1)
    path = [(i, 0) for i in range(1, 8)]
    plan = plan_tick((0, 0), (), _sizes(8), b, path=path)
    xs = {c[0] for c in plan.load if c[1] == 0 and c[0] > 1}
    assert xs == {2, 3}  # radius 1 + default look-ahead 2
    plan0 = plan_tick((0, 0), (), _sizes(8), b, path=path, path_lookahead=0)
    assert max(max(abs(c[0]), abs(c[1])) for c in plan0.load) == 1


def test_path_cells_beyond_radius_load_after_near_cells():
    b = StreamBudget(10_000, 1_000, 1)
    plan = plan_tick((0, 0), (), _sizes(5), b, path=[(1, 0), (2, 0), (3, 0)])
    dists = [max(abs(c[0]), abs(c[1])) for c in plan.load]
    first_far = next(i for i, d in enumerate(dists) if d > 1)
    assert all(d <= 1 for d in dists[:first_far]) and all(d > 1 for d in dists[first_far:])


def test_negative_path_lookahead_rejected():
    with pytest.raises(StreamingError):
        plan_tick((0, 0), (), _sizes(2), StreamBudget(10, 10, 1), path=[(1, 0)], path_lookahead=-1)


def test_tile_layout_fallback_flagged_not_silent():
    c = _cand("m", ["...", "...", "..."], ((2, 2),), kinds=("a", "b", "a", "b"))
    tiles, fb = tile_layout(c)
    assert fb and tiles == [["a", "b", "a", "b"]]
    assert "tile_layout_fallback" in score(c, 10.0).warnings
    assert score(c, 10.0).passed  # warning only, not a failure
    with pytest.raises(TileLayoutError):
        score(c, 10.0, strict_tiles=True)


def test_tile_layout_match_has_no_flag():
    c = _cand("m", ["...", "...", "..."], ((2, 2),))
    assert tile_layout(c)[1] is False and score(c, 10.0).warnings == ()


def test_rank_softlocked_world_fails_even_though_goal_reachable():
    from skeleton.frontier.worldsim.navigation import GateSpec
    # one-way drop away from the key leaves the exit gate unopenable: softlock
    g = [".....", ".####"]
    spec = GateSpec(gates={(4, 0): "k"}, keys={(0, 1): "k"}, one_way=frozenset({((1, 0), (2, 0))}))
    soft = WorldCandidate("soft", NavGrid.from_rows(g), (0, 0), ((4, 0),), ("a",) * 10, 1.0)
    clean = _cand("clean", ["...", "...", "..."], ((2, 2),))
    out = rank([soft, clean], 10.0, gates=spec)
    assert out[0].world_id == "clean"
    assert out[1].total == 0.0 and not out[1].passed and "softlock" in out[1].failures
