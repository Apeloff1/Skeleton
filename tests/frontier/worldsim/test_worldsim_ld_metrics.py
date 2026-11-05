"""Wally LD notes on #4268: structural diversity, heading-aware streaming, structured variety."""
import random

from skeleton.frontier.worldsim.navigation import NavGrid
from skeleton.frontier.worldsim.procgen import (
    GenerationResult, layout_features, measure_structural, structural_distance)
from skeleton.frontier.worldsim.quality_arena import (
    WorldCandidate, score, score_structured, structured_variety)
from skeleton.frontier.worldsim.streaming import StreamBudget, plan_tick, plan_tick_directed

CORRIDOR = ["#######", "#.....#", "#######"]
CORRIDOR_SHIFTED = ["#######", "#......", "#######"]  # one cell differs
CROSS = ["###.###", "###.###", ".......", "###.###", "###.###"]
LOOP = ["#####", "#...#", "#.#.#", "#...#", "#####"]


def _res(rows):
    return GenerationResult(0, {"rows": rows}, True, (), "d")


def test_layout_features_distinguish_shapes():
    c, x, l = layout_features(CORRIDOR), layout_features(CROSS), layout_features(LOOP)
    assert c["rooms"] == 1 and c["dead_ends"] > 0 and c["loops"] == 0
    assert x["branching"] > 0 and c["branching"] == 0
    assert l["loops"] > 0 and l["dead_ends"] == 0


def test_structural_distance_ignores_cosmetic_but_sees_structure():
    near = structural_distance(layout_features(CORRIDOR), layout_features(CORRIDOR_SHIFTED))
    far = structural_distance(layout_features(CORRIDOR), layout_features(LOOP))
    assert near < far
    assert structural_distance(layout_features(LOOP), layout_features(LOOP)) == 0


def test_measure_structural_flags_lookalike_batch():
    same = measure_structural([_res(CORRIDOR), _res(CORRIDOR_SHIFTED)])
    varied = measure_structural([_res(CORRIDOR), _res(CROSS), _res(LOOP)])
    assert varied.mean_structural_distance > same.mean_structural_distance
    assert varied.distinct_layouts == 1.0 and same.distinct_layouts == 0.0


def _sizes(r=3):
    return {(x, y): 10 for x in range(-r, r + 1) for y in range(-r, r + 1)}


def test_directed_streaming_loads_ahead_first():
    b = StreamBudget(memory_bytes=10_000, max_loads_per_tick=3, radius=3)
    plan = plan_tick_directed((0, 0), (1, 0), [], _sizes(), b)
    assert plan.load[0] == (0, 0)
    assert all(c[0] > 0 for c in plan.load[1:])
    nearest = plan_tick((0, 0), [], _sizes(), b)
    assert set(plan.load) != set(nearest.load)


def test_directed_streaming_zero_heading_matches_nearest_first_set():
    b = StreamBudget(memory_bytes=10_000, max_loads_per_tick=9, radius=3)
    assert set(plan_tick_directed((0, 0), (0, 0), [], _sizes(), b).load) == \
        set(plan_tick((0, 0), [], _sizes(), b).load)


def test_directed_streaming_path_and_behind_radius():
    b = StreamBudget(memory_bytes=10_000, max_loads_per_tick=3, radius=3)
    path = [(0, 3), (0, 2)]
    plan = plan_tick_directed((0, 0), (1, 0), [], _sizes(), b, path=path)
    assert plan.load[0] == (0, 0) and set(plan.load[1:]) == set(path)
    full = StreamBudget(memory_bytes=10_000, max_loads_per_tick=100, radius=3)
    p2 = plan_tick_directed((0, 0), (1, 0), [(-3, 0)], _sizes(), full, behind_radius=1)
    assert (-3, 0) in p2.unload and all(c[0] >= -1 for c in p2.load)


def test_structured_variety_penalises_noise():
    rng = random.Random(7)
    kinds = "abcd"
    noise = [[rng.choice(kinds) for _ in range(16)] for _ in range(16)]
    regions = [[kinds[(x // 8) + 2 * (y // 8)] for x in range(16)] for y in range(16)]
    mono = [["a"] * 16 for _ in range(16)]
    assert structured_variety(regions) > 0.8
    assert structured_variety(noise) < 0.15
    assert structured_variety(mono) == 0.0


def test_score_structured_ranks_regions_over_noise():
    rng = random.Random(1)
    grid = NavGrid.from_rows(["....", "....", "....", "...."])
    noise = [[rng.choice("abcd") for _ in range(4)] for _ in range(4)]
    regions = [["a", "a", "b", "b"], ["a", "a", "b", "b"], ["c", "c", "d", "d"], ["c", "c", "d", "d"]]
    kinds = tuple(k for r in noise for k in r)
    cand = WorldCandidate("w", grid, (0, 0), ((3, 3),), kinds, 1.0)
    assert score_structured(cand, 5.0, regions).total > score_structured(cand, 5.0, noise).total
    assert score(cand, 5.0).passed == score_structured(cand, 5.0, regions).passed


# --- Re-review at b4f0d4c6: the reviewed functions themselves use the new behaviour ---
from skeleton.frontier.worldsim.navigation import GateSpec, gated_states
from skeleton.frontier.worldsim.procgen import _distance, measure
from skeleton.frontier.worldsim.quality_arena import pacing_score, score_paced


def test_procgen_distance_and_measure_are_structural_for_layouts():
    assert _distance({"rows": CORRIDOR}, {"rows": CORRIDOR_SHIFTED}) < \
        _distance({"rows": CORRIDOR}, {"rows": LOOP})
    lookalike = measure([_res(CORRIDOR), _res(CORRIDOR_SHIFTED)])
    varied = measure([_res(CORRIDOR), _res(CROSS), _res(LOOP)])
    assert lookalike.diversity == 0.0 and varied.diversity == 1.0
    assert varied.mean_pairwise_distance > lookalike.mean_pairwise_distance
    # non-layout artifacts keep key-wise distance
    assert _distance({"a": 1, "b": 2}, {"a": 1, "b": 3}) == 0.5


def test_plan_tick_uses_heading_when_given_default_unchanged():
    b = StreamBudget(memory_bytes=10_000, max_loads_per_tick=3, radius=3)
    directed = plan_tick((0, 0), [], _sizes(), b, heading=(1, 0))
    assert directed == plan_tick_directed((0, 0), (1, 0), [], _sizes(), b)
    assert all(c[0] > 0 for c in directed.load[1:])
    plain = plan_tick((0, 0), [], _sizes(), b)
    assert plain.load[0] == (0, 0) and directed.load != plain.load


def test_score_variety_is_structured_not_unique_ratio():
    grid = NavGrid.from_rows(["...."] * 4)
    regions = ("a", "a", "b", "b") * 2 + ("c", "c", "d", "d") * 2
    rng = random.Random(3)
    noise = tuple(rng.choice("abcd") for _ in range(16))
    r = score(WorldCandidate("r", grid, (0, 0), (), regions, 1.0), 5.0).parts["variety"]
    n = score(WorldCandidate("n", grid, (0, 0), (), noise, 1.0), 5.0).parts["variety"]
    assert r > n and r == structured_variety([list(regions[i:i + 4]) for i in range(0, 16, 4)])


GOOD_CURVE = [0.1, 0.3, 0.2, 0.6, 0.5, 1.0]


def test_score_paced_softlock_is_hard_fail():
    # spawn (0,0) -> one-way drop into (2,0); exit gate (3,0) needs key never available
    grid = NavGrid.from_rows(["....."])
    gates = GateSpec(gates={(3, 0): "red"}, one_way=frozenset({((1, 0), (2, 0))}))
    c = WorldCandidate("s", grid, (0, 0), ((4, 0),), ("a",), 1.0)
    s = score_paced(c, 10, GOOD_CURVE, [0, 4, 8], gates=gates)
    assert s.total == 0.0 and not s.passed and "softlock" in s.failures


def test_score_paced_unreachable_is_hard_fail():
    c = WorldCandidate("u", NavGrid.from_rows([".#."]), (0, 0), ((2, 0),), ("a",), 1.0)
    s = score_paced(c, 10, GOOD_CURVE, [0, 4, 8])
    assert s.total == 0.0 and not s.passed and "unreachable_objectives" in s.failures


def test_pacing_counts_each_plateau_run_once():
    one_long = [0.1] * 9 + [0.2, 0.1, 1.0]   # one long plateau
    # peak late (0.5) + relief 1/3*0.5 - one plateau (0.1); per-step counting would subtract 0.6
    assert pacing_score(one_long) == 0.566667
    two_runs = [0.1] * 4 + [0.2] * 4 + [0.1, 0.1, 0.1, 1.0]
    assert pacing_score(two_runs) < pacing_score(one_long)


def test_gated_states_bfs_order_with_deque():
    grid = NavGrid.from_rows(["k.D."])
    spec = GateSpec(gates={(2, 0): "k"}, keys={(0, 0): "k"})
    states = gated_states(grid, spec, (0, 0))
    assert {cell for cell, _ in states} == {(0, 0), (1, 0), (2, 0), (3, 0)}
    assert list(states)[0] == ((0, 0), frozenset({"k"}))
