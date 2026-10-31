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
