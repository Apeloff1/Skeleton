from __future__ import annotations

import json

import pytest

from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_legacy import (
    InputButton,
    InputFrame,
)
from skeleton.jeeves.game_engine_modern import (
    DEFAULT_ADAPTIVE_POLICY,
    MODERN_ERAS,
    AdaptivePolicy,
    DataOrientedMachine,
    HdDeferredMachine,
    ModernEngineAdversary,
    ModernEngineLab,
    NextHybridMachine,
    OpenWorldMachine,
    build_modern_engine_tree,
    compile_adaptive_policy,
    compile_modern_tuning,
    create_modern_machine,
    default_modern_tuning,
    modern_hardware,
)


@pytest.mark.parametrize("era", MODERN_ERAS)
def test_modern_adversary_passes_canonical_engine(
    era: EngineEra,
) -> None:
    report = ModernEngineAdversary().evaluate(era)
    assert report.passed
    assert report.score == 1.0
    assert report.failed == ()
    assert {
        "file_tree",
        "configuration",
        "determinism",
        "render_passes",
        "streaming_bound",
        "snapshot",
        "rollback_contract",
        "policy_boundary",
    } == {probe.name for probe in report.probes}


@pytest.mark.parametrize(
    ("era", "machine_type"),
    [
        (EngineEra.HD, HdDeferredMachine),
        (EngineEra.OPEN_WORLD, OpenWorldMachine),
        (EngineEra.MODERN, DataOrientedMachine),
        (EngineEra.NEXT, NextHybridMachine),
    ],
)
def test_modern_factory_builds_era_specific_machine(
    era: EngineEra,
    machine_type: type,
) -> None:
    assert isinstance(create_modern_machine(era), machine_type)


def test_non_modern_machine_request_fails_closed() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="modern runtime unavailable",
    ):
        create_modern_machine(EngineEra.SHADER)


@pytest.mark.parametrize("era", MODERN_ERAS)
def test_modern_tree_carries_ecs_jobs_streaming_and_pipeline(
    era: EngineEra,
) -> None:
    tree = build_modern_engine_tree(era, "immersive_sim")

    assert {
        "engine/modern_pipeline.json",
        "engine/ecs_schema.json",
        "engine/jobs.json",
        "engine/streaming.json",
        "engine/modern_tuning.json",
        "engine/modern_runtime.py",
        "tests/modern_acceptance.json",
    } <= set(tree.files)
    assert (
        compile_modern_tuning(era, tree)
        == default_modern_tuning(era)
    )


def test_next_tree_carries_non_executable_bounded_policy() -> None:
    tree = build_modern_engine_tree(EngineEra.NEXT)
    raw = json.loads(tree.read("engine/adaptive_policy.json"))
    policy = compile_adaptive_policy(tree)

    assert raw["executable_code"] is False
    assert policy == DEFAULT_ADAPTIVE_POLICY
    assert len(policy.coefficients) == 4


@pytest.mark.parametrize(
    "coefficients",
    [
        (2.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, float("inf"), 0.0),
    ],
)
def test_adaptive_policy_rejects_unbounded_coefficients(
    coefficients: tuple[float, ...],
) -> None:
    with pytest.raises(GameEngineLabError):
        AdaptivePolicy(coefficients)


def test_adaptive_policy_is_rejected_by_pre_next_eras() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="adaptive policy unsupported",
    ):
        create_modern_machine(
            EngineEra.MODERN,
            policy=DEFAULT_ADAPTIVE_POLICY,
        )


@pytest.mark.parametrize("era", (EngineEra.MODERN, EngineEra.NEXT))
def test_rollback_recovers_prior_tick(
    era: EngineEra,
) -> None:
    machine = create_modern_machine(era)

    for tick in range(24):
        machine.step(
            InputFrame(
                tick,
                InputButton.UP | InputButton.RIGHT,
            )
        )
    assert machine.tick == 24

    machine.rollback(6)

    assert machine.tick == 18


@pytest.mark.parametrize("era", (EngineEra.HD, EngineEra.OPEN_WORLD))
def test_pre_rollback_eras_fail_closed(
    era: EngineEra,
) -> None:
    machine = create_modern_machine(era)
    machine.step(InputFrame(0))

    with pytest.raises(
        GameEngineLabError,
        match="rollback unavailable",
    ):
        machine.rollback(1)


def test_modern_gpu_driven_instances_have_stable_batch_order() -> None:
    machine = DataOrientedMachine()
    frame = machine.step(InputFrame(0))

    keys = [
        (
            row.material,
            row.mesh,
            row.lod,
            row.entity_id,
        )
        for row in frame.instances
    ]
    assert keys == sorted(keys)
    assert machine.spec.gpu_driven


def test_open_world_loaded_cells_are_bounded() -> None:
    machine = OpenWorldMachine()
    for tick in range(120):
        packet = machine.step(
            InputFrame(
                tick,
                InputButton.UP | InputButton.RIGHT,
            )
        )
        assert (
            len(packet.loaded_cells)
            <= machine.spec.max_stream_cells
        )


def test_next_policy_changes_motion_without_mutating_policy() -> None:
    policy = AdaptivePolicy((0.5, -0.2, 0.1, 0.05))
    first = NextHybridMachine(policy=policy)
    second = NextHybridMachine(policy=policy)

    script = tuple(
        InputFrame(
            tick,
            InputButton.UP
            | (
                InputButton.FIRE
                if tick % 11 == 0
                else InputButton.NONE
            ),
        )
        for tick in range(80)
    )
    packets_a = first.run(script)
    packets_b = second.run(script)

    assert packets_a == packets_b
    assert first.fingerprint() == second.fingerprint()
    assert first.policy == policy
    assert first.policy.coefficients == (0.5, -0.2, 0.1, 0.05)


def test_modern_snapshot_rejects_tamper() -> None:
    machine = DataOrientedMachine()
    machine.step(InputFrame(0))
    snapshot = machine.snapshot()
    forged = type(snapshot)(
        snapshot.era,
        snapshot.tick,
        snapshot.state,
        "0" * 64,
    )

    with pytest.raises(
        GameEngineLabError,
        match="digest mismatch",
    ):
        machine.restore(forged)


def test_corrupt_modern_tuning_is_repaired() -> None:
    lab = ModernEngineLab()
    sandbox = lab.create(
        EngineEra.MODERN,
        "immersive_sim",
    )
    path = "engine/modern_tuning.json"
    payload = json.loads(sandbox.tree.read(path))
    payload["stream_radius"] = 999
    broken = sandbox.apply(
        [
            SandboxPatch(
                path,
                json.dumps(payload),
                sandbox.tree.file_digest(path),
            )
        ]
    )

    assert not lab.evaluate(broken).passed
    result = lab.adversarial_improve(broken)

    assert result.promoted
    assert result.report.passed
    assert len(result.rounds) == 1
    assert result.rounds[0].accepted


def test_corrupt_next_policy_is_repaired() -> None:
    lab = ModernEngineLab()
    sandbox = lab.create(EngineEra.NEXT)
    path = "engine/adaptive_policy.json"
    payload = json.loads(sandbox.tree.read(path))
    payload["coefficients"] = [10, 0, 0, 0]
    broken = sandbox.apply(
        [
            SandboxPatch(
                path,
                json.dumps(payload),
                sandbox.tree.file_digest(path),
            )
        ]
    )

    assert not lab.evaluate(broken).passed
    result = lab.adversarial_improve(broken)

    assert result.promoted
    assert result.report.passed
    assert (
        compile_adaptive_policy(result.sandbox.tree)
        == DEFAULT_ADAPTIVE_POLICY
    )


def test_regressing_modern_candidate_is_not_promoted() -> None:
    lab = ModernEngineLab()
    sandbox = lab.create(EngineEra.OPEN_WORLD)
    path = "engine/modern_tuning.json"
    payload = json.loads(sandbox.tree.read(path))
    payload["stream_radius"] = 999
    broken = sandbox.apply(
        [
            SandboxPatch(
                path,
                json.dumps(payload),
                sandbox.tree.file_digest(path),
            )
        ]
    )

    def worse(current, report):
        del report
        return (
            SandboxPatch(
                "engine/streaming.json",
                None,
                current.tree.file_digest("engine/streaming.json"),
            ),
        )

    result = lab.adversarial_improve(
        broken,
        improver=worse,
    )

    assert not result.promoted
    assert len(result.rounds) == 1
    assert not result.rounds[0].accepted
    assert result.sandbox.tree.digest == broken.tree.digest


def test_render_graphs_are_distinct_across_hd_to_next() -> None:
    graphs = {
        era: modern_hardware(era).render_passes
        for era in MODERN_ERAS
    }

    assert len(set(graphs.values())) == len(MODERN_ERAS)
    assert "ray_queries" not in graphs[EngineEra.HD]
    assert "ray_queries" in graphs[EngineEra.MODERN]
    assert "adaptive_material" in graphs[EngineEra.NEXT]
