from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_navigation import (
    NAVIGATION_POLICIES,
    NavEdge,
    NavNode,
    NavigationAdversary,
    NavigationHeuristic,
    NavigationMode,
    NavigationQuery,
    NavigationRuntime,
    NavigationSource,
    SteeringNeighbor,
    attach_navigation_build,
    build_navigation_runtime,
    canonical_navigation_patches,
    canonical_navigation_query,
    canonical_navigation_source,
    compile_navigation_build,
    navigation_policy,
)
from skeleton.jeeves.game_engine_runtime import (
    ExecutableGameEngineLab,
)


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_every_era_has_navigation_policy(
    era: EngineEra,
) -> None:
    policy = navigation_policy(
        era
    )

    assert era in NAVIGATION_POLICIES
    assert policy.era is era
    assert policy.max_nodes >= 1
    assert policy.max_edges >= 1
    assert policy.max_path_nodes >= 1


def test_navigation_capability_ladder_progresses_historically() -> None:
    assert (
        navigation_policy(
            EngineEra.PONG
        ).mode
        is NavigationMode.DIRECT
    )
    assert (
        navigation_policy(
            EngineEra.EIGHT_BIT
        ).mode
        is NavigationMode.GRID_BFS
    )
    assert (
        navigation_policy(
            EngineEra.SIXTEEN_BIT
        ).mode
        is NavigationMode.GRID_ASTAR
    )
    assert (
        navigation_policy(
            EngineEra.EARLY_3D
        ).mode
        is NavigationMode.WAYPOINT_ASTAR
    )
    assert (
        navigation_policy(
            EngineEra.SHADER
        ).mode
        is NavigationMode.NAVMESH_ASTAR
    )
    assert (
        navigation_policy(
            EngineEra.OPEN_WORLD
        ).mode
        is NavigationMode.HIERARCHICAL
    )
    assert (
        navigation_policy(
            EngineEra.MODERN
        ).mode
        is NavigationMode.CROWD_HIERARCHICAL
    )
    assert (
        navigation_policy(
            EngineEra.NEXT
        ).mode
        is NavigationMode.MULTI_LAYER
    )
    assert not navigation_policy(
        EngineEra.PONG
    ).dynamic_obstacles
    assert navigation_policy(
        EngineEra.FIXED_3D
    ).dynamic_obstacles
    assert not navigation_policy(
        EngineEra.FIXED_3D
    ).smoothing
    assert navigation_policy(
        EngineEra.SHADER
    ).smoothing
    assert navigation_policy(
        EngineEra.MODERN
    ).crowd_steering


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_canonical_navigation_build_is_deterministic_and_attested(
    era: EngineEra,
) -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        era
    )
    source = canonical_navigation_source(
        era
    )

    first = compile_navigation_build(
        era,
        source,
    )
    second = compile_navigation_build(
        era,
        source,
    )

    assert first == second
    assert len(first.source_digest) == 64
    assert len(first.policy_digest) == 64
    assert len(first.manifest_digest) == 64

    attached = attach_navigation_build(
        sandbox,
        source,
    )
    report = NavigationAdversary().evaluate(
        attached,
        source,
    )

    assert report.passed
    assert report.score == 1.0
    assert {
        "manifest",
        "inventory",
        "integrity",
        "replay",
        "optimality",
        "snapshot",
        "dynamic",
        "hierarchy",
        "steering",
    } == {
        probe.name
        for probe
        in report.probes
    }
    assert ExecutableGameEngineLab().evaluate(
        attached
    ).passed


def test_pong_direct_navigation_requires_direct_edge() -> None:
    source = NavigationSource(
        (
            NavNode(
                "start",
                0,
                0,
            ),
            NavNode(
                "middle",
                1,
                0,
            ),
            NavNode(
                "goal",
                2,
                0,
            ),
        ),
        (
            NavEdge(
                "start",
                "middle",
                10,
            ),
            NavEdge(
                "middle",
                "goal",
                10,
            ),
        ),
    )
    runtime = NavigationRuntime(
        EngineEra.PONG,
        source,
    )

    result = runtime.path(
        NavigationQuery(
            "start",
            "goal",
        )
    )

    assert not result.found
    assert result.path == ()
    assert result.total_cost is None


def test_eight_bit_bfs_finds_stable_shortest_hop_path() -> None:
    runtime = build_navigation_runtime(
        EngineEra.EIGHT_BIT
    )
    query = canonical_navigation_query(
        EngineEra.EIGHT_BIT
    )

    first = runtime.path(
        query
    )
    second = runtime.path(
        query
    )

    assert first == second
    assert first.found
    assert first.path[0] == "n0_0"
    assert first.path[-1] == "n4_4"
    assert len(first.path) == 9
    assert first.total_cost == 80


def test_sixteen_bit_astar_honors_weighted_edges() -> None:
    source = NavigationSource(
        (
            NavNode(
                "start",
                0,
                0,
            ),
            NavNode(
                "short",
                1,
                0,
            ),
            NavNode(
                "detour_a",
                0,
                1,
            ),
            NavNode(
                "detour_b",
                1,
                1,
            ),
            NavNode(
                "goal",
                2,
                0,
            ),
        ),
        (
            NavEdge(
                "start",
                "short",
                50,
            ),
            NavEdge(
                "short",
                "goal",
                50,
            ),
            NavEdge(
                "start",
                "detour_a",
                10,
            ),
            NavEdge(
                "detour_a",
                "detour_b",
                10,
            ),
            NavEdge(
                "detour_b",
                "goal",
                20,
            ),
        ),
    )
    runtime = NavigationRuntime(
        EngineEra.SIXTEEN_BIT,
        source,
    )

    result = runtime.path(
        NavigationQuery(
            "start",
            "goal",
        )
    )

    assert result.path == (
        "start",
        "detour_a",
        "detour_b",
        "goal",
    )
    assert result.total_cost == 40


def test_navigation_source_rejects_heuristic_overestimate_edge() -> None:
    source = NavigationSource(
        (
            NavNode(
                "a",
                0,
                0,
                0,
            ),
            NavNode(
                "b",
                3,
                4,
                0,
            ),
        ),
        (
            NavEdge(
                "a",
                "b",
                49,
            ),
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="admissible heuristic",
    ):
        compile_navigation_build(
            EngineEra.EARLY_3D,
            source,
        )


def test_grid_bfs_rejects_nonuniform_edge_costs() -> None:
    source = NavigationSource(
        (
            NavNode(
                "a",
                0,
                0,
            ),
            NavNode(
                "b",
                1,
                0,
            ),
            NavNode(
                "c",
                2,
                0,
            ),
        ),
        (
            NavEdge(
                "a",
                "b",
                10,
            ),
            NavEdge(
                "b",
                "c",
                11,
            ),
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="uniform edge costs",
    ):
        compile_navigation_build(
            EngineEra.EIGHT_BIT,
            source,
        )


def test_2d_navigation_rejects_nonzero_z() -> None:
    source = NavigationSource(
        (
            NavNode(
                "a",
                0,
                0,
                1,
            ),
            NavNode(
                "b",
                1,
                0,
                1,
            ),
        ),
        (
            NavEdge(
                "a",
                "b",
                10,
            ),
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="nonzero z",
    ):
        compile_navigation_build(
            EngineEra.SIXTEEN_BIT,
            source,
        )


def test_dynamic_obstacles_are_gated_by_era() -> None:
    runtime = build_navigation_runtime(
        EngineEra.EARLY_3D
    )

    with pytest.raises(
        GameEngineLabError,
        match="dynamic navigation obstacles unavailable",
    ):
        runtime.set_blocked(
            "n1_0",
            True,
        )


def test_fixed_3d_dynamic_obstacle_reroutes_around_blocked_node() -> None:
    runtime = build_navigation_runtime(
        EngineEra.FIXED_3D
    )
    query = canonical_navigation_query(
        EngineEra.FIXED_3D
    )
    baseline = runtime.path(
        query
    )
    assert baseline.found
    middle = baseline.path[1]

    runtime.set_blocked(
        middle,
        True,
    )
    rerouted = runtime.path(
        query
    )

    assert rerouted.found
    assert middle not in rerouted.path
    assert rerouted != baseline


def test_dynamic_penalty_can_change_optimal_route() -> None:
    source = NavigationSource(
        (
            NavNode(
                "start",
                0,
                0,
                0,
            ),
            NavNode(
                "upper",
                1,
                1,
                0,
            ),
            NavNode(
                "lower",
                1,
                -1,
                0,
            ),
            NavNode(
                "goal",
                2,
                0,
                0,
            ),
        ),
        (
            NavEdge(
                "start",
                "upper",
                20,
            ),
            NavEdge(
                "upper",
                "goal",
                20,
            ),
            NavEdge(
                "start",
                "lower",
                20,
            ),
            NavEdge(
                "lower",
                "goal",
                20,
            ),
        ),
    )
    runtime = NavigationRuntime(
        EngineEra.HD,
        source,
    )
    query = NavigationQuery(
        "start",
        "goal",
    )
    baseline = runtime.path(
        query
    )

    runtime.set_penalty(
        baseline.path[1],
        100,
    )
    changed = runtime.path(
        query
    )

    assert changed.path != baseline.path
    assert (
        baseline.path[1]
        not in changed.path
    )
    assert changed.total_cost == 40


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.OPEN_WORLD,
        EngineEra.MODERN,
        EngineEra.NEXT,
    ],
)
def test_hierarchical_eras_emit_deterministic_region_route(
    era: EngineEra,
) -> None:
    runtime = build_navigation_runtime(
        era
    )
    query = canonical_navigation_query(
        era
    )

    first = runtime.path(
        query
    )
    second = runtime.path(
        query
    )

    assert first == second
    assert first.found
    assert len(first.region_route) >= 2
    assert (
        first.region_route[0]
        == runtime.nodes[
            query.start
        ].region
    )
    assert (
        first.region_route[-1]
        == runtime.nodes[
            query.goal
        ].region
    )


def test_shader_navigation_smoothing_uses_valid_graph_shortcuts() -> None:
    runtime = build_navigation_runtime(
        EngineEra.SHADER
    )

    result = runtime.path(
        canonical_navigation_query(
            EngineEra.SHADER
        )
    )

    assert result.found
    assert result.smoothed
    assert result.path == (
        "n0_0",
        "n0_4",
        "n4_4",
    )
    assert result.total_cost == 80


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.MODERN,
        EngineEra.NEXT,
    ],
)
def test_crowd_steering_is_order_invariant_and_bounded(
    era: EngineEra,
) -> None:
    runtime = build_navigation_runtime(
        era
    )
    left = SteeringNeighbor(
        "left",
        -0.5,
        0.0,
    )
    front = SteeringNeighbor(
        "front",
        0.5,
        0.25,
    )

    first = runtime.steer(
        agent_x=0.0,
        agent_z=0.0,
        desired_x=1.0,
        desired_z=0.0,
        neighbors=(
            left,
            front,
        ),
    )
    second = runtime.steer(
        agent_x=0.0,
        agent_z=0.0,
        desired_x=1.0,
        desired_z=0.0,
        neighbors=(
            front,
            left,
        ),
    )

    assert first == second
    assert set(first.considered) == {
        "front",
        "left",
    }
    assert (
        first.velocity_x ** 2
        + first.velocity_z ** 2
        <= 1.000000000001
    )


def test_pre_modern_navigation_rejects_crowd_steering() -> None:
    runtime = build_navigation_runtime(
        EngineEra.OPEN_WORLD
    )

    with pytest.raises(
        GameEngineLabError,
        match="crowd steering unavailable",
    ):
        runtime.steer(
            agent_x=0.0,
            agent_z=0.0,
            desired_x=1.0,
            desired_z=0.0,
        )


def test_navigation_snapshot_restores_dynamic_state_exactly() -> None:
    runtime = build_navigation_runtime(
        EngineEra.MODERN
    )
    runtime.set_blocked(
        "n1_0",
        True,
    )
    runtime.set_penalty(
        "n0_1",
        37,
    )
    snapshot = runtime.snapshot()
    expected = runtime.fingerprint()

    runtime.set_blocked(
        "n1_0",
        False,
    )
    runtime.set_penalty(
        "n0_1",
        0,
    )
    assert runtime.fingerprint() != expected

    runtime.restore(
        snapshot
    )

    assert runtime.fingerprint() == expected
    assert runtime.snapshot() == snapshot


def test_navigation_snapshot_tamper_is_rejected_without_state_change() -> None:
    runtime = build_navigation_runtime(
        EngineEra.MODERN
    )
    runtime.set_blocked(
        "n1_0",
        True,
    )
    snapshot = runtime.snapshot()
    before = runtime.fingerprint()
    forged = replace(
        snapshot,
        digest="0" * 64,
    )

    with pytest.raises(
        GameEngineLabError,
        match="digest mismatch",
    ):
        runtime.restore(
            forged
        )

    assert runtime.fingerprint() == before


def test_navigation_manifest_tamper_is_detected_and_repaired() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.OPEN_WORLD
    )
    source = canonical_navigation_source(
        EngineEra.OPEN_WORLD
    )
    attached = attach_navigation_build(
        sandbox,
        source,
    )
    path = (
        "navigation/compiled/"
        "manifest.json"
    )
    broken = attached.apply(
        (
            SandboxPatch(
                path,
                "{}",
                attached.tree.file_digest(
                    path
                ),
            ),
        )
    )

    before = NavigationAdversary().evaluate(
        broken,
        source,
    )
    assert not before.passed
    assert "manifest" in before.failed

    repaired = broken.apply(
        canonical_navigation_patches(
            broken,
            source,
        )
    )

    assert NavigationAdversary().evaluate(
        repaired,
        source,
    ).passed


def test_untracked_compiled_navigation_is_detected_and_removed() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.NEXT
    )
    source = canonical_navigation_source(
        EngineEra.NEXT
    )
    attached = attach_navigation_build(
        sandbox,
        source,
    )
    rogue = (
        "navigation/compiled/"
        "rogue.json"
    )
    broken = attached.apply(
        (
            SandboxPatch(
                rogue,
                "{}",
            ),
        )
    )

    report = NavigationAdversary().evaluate(
        broken,
        source,
    )
    assert not report.passed
    assert "inventory" in report.failed

    repaired = broken.apply(
        canonical_navigation_patches(
            broken,
            source,
        )
    )

    assert rogue not in repaired.tree.files
    assert NavigationAdversary().evaluate(
        repaired,
        source,
    ).passed


def test_runtime_quality_accepts_attested_navigation_evidence() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.MODERN
    )
    attached = attach_navigation_build(
        sandbox,
        canonical_navigation_source(
            EngineEra.MODERN
        ),
    )

    report = lab.evaluate(
        attached
    )

    assert report.passed
    assert report.contract_mismatches == ()


def test_jeeves_compiles_evaluates_and_queries_navigation() -> None:
    jeeves = Jeeves()
    sandbox = jeeves.build_game_engine(
        EngineEra.MODERN,
        gameplay_dialect=
            "action_adventure",
    )
    source = canonical_navigation_source(
        EngineEra.MODERN
    )

    compiled = (
        jeeves.compile_game_navigation(
            sandbox,
            source,
        )
    )
    report = (
        jeeves.evaluate_game_navigation(
            compiled,
            source,
        )
    )
    runtime = jeeves.game_navigation(
        EngineEra.MODERN,
        source,
    )
    result = (
        jeeves.query_game_navigation(
            runtime,
            canonical_navigation_query(
                EngineEra.MODERN
            ),
        )
    )

    assert report.passed
    assert result.found
    assert result.path[0] == "n0_0"
    assert result.path[-1] == "n4_4"
    assert len(result.digest) == 64
    assert (
        jeeves.evaluate_game_engine(
            compiled
        ).passed
    )
