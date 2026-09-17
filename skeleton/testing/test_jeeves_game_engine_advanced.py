from __future__ import annotations

import json

import pytest

from skeleton.jeeves.game_engine_advanced import (
    ADVANCED_ERAS,
    DEFAULT_HYBRID_POLICY,
    AdvancedEngineAdversary,
    AdvancedEngineLab,
    HDRenderGraphMachine,
    HybridPolicy,
    ModernGpuMachine,
    NextHybridMachine,
    StreamedOpenWorldMachine,
    build_advanced_engine_tree,
    compile_advanced_tuning,
    compile_hybrid_policy,
    create_advanced_machine,
    default_advanced_tuning,
)
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_legacy import (
    InputButton,
    InputFrame,
)


@pytest.mark.parametrize("era", ADVANCED_ERAS)
def test_advanced_adversary_passes_canonical_engine(
    era: EngineEra,
) -> None:
    report = AdvancedEngineAdversary().evaluate(era)

    assert report.passed
    assert report.score == 1.0
    assert report.failed == ()
    assert {
        "file_tree",
        "compile",
        "determinism",
        "draw_budget",
        "snapshot",
        "pipeline",
        "era_contract",
    } == {
        probe.name
        for probe in report.probes
    }


@pytest.mark.parametrize(
    ("era", "machine_type"),
    [
        (
            EngineEra.HD,
            HDRenderGraphMachine,
        ),
        (
            EngineEra.OPEN_WORLD,
            StreamedOpenWorldMachine,
        ),
        (
            EngineEra.MODERN,
            ModernGpuMachine,
        ),
        (
            EngineEra.NEXT,
            NextHybridMachine,
        ),
    ],
)
def test_advanced_factory_builds_distinct_architecture(
    era: EngineEra,
    machine_type: type,
) -> None:
    assert isinstance(
        create_advanced_machine(era),
        machine_type,
    )


def test_non_advanced_runtime_request_fails_closed() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="advanced runtime unavailable",
    ):
        create_advanced_machine(
            EngineEra.SHADER
        )


def test_hd_engine_uses_explicit_render_graph_passes() -> None:
    machine = HDRenderGraphMachine()
    frame = machine.step()

    passes = {
        command.pass_name
        for command in frame.commands
    }

    assert {
        "gbuffer",
        "lighting",
        "post",
    } <= passes
    assert frame.loaded_cells == ()
    assert not machine.spec.streaming
    assert not machine.spec.gpu_driven


def test_open_world_streaming_is_sorted_and_bounded() -> None:
    machine = StreamedOpenWorldMachine()
    frame = machine.step(
        InputFrame(
            0,
            InputButton.UP,
        )
    )

    assert frame.loaded_cells
    assert (
        frame.loaded_cells
        == tuple(
            sorted(
                frame.loaded_cells
            )
        )
    )
    radius = int(
        machine.tuning[
            "stream_radius"
        ]
    )
    assert (
        len(frame.loaded_cells)
        == (radius * 2 + 1) ** 2
    )
    assert machine.spec.streaming
    assert not machine.spec.gpu_driven


def test_modern_engine_batches_gpu_indirect_draws() -> None:
    machine = ModernGpuMachine()
    frame = machine.step()

    assert frame.commands
    assert all(
        command.pass_name
        == "gpu_indirect"
        for command
        in frame.commands
    )
    assert frame.batches == len(
        frame.commands
    )
    assert machine.spec.gpu_driven


def test_modern_rollback_restores_state_identity() -> None:
    machine = ModernGpuMachine()
    frames = tuple(
        InputFrame(
            tick,
            InputButton.UP
            | (
                InputButton.RIGHT
                if tick < 15
                else InputButton.NONE
            ),
        )
        for tick in range(40)
    )
    machine.run(frames)

    target = next(
        snapshot
        for snapshot
        in machine.rollback_snapshots
        if snapshot.tick == 20
    )
    target_digest = target.digest

    machine.rollback_to_tick(20)

    assert machine.tick == 20
    assert machine.snapshot().digest == target_digest
    assert all(
        snapshot.tick <= 20
        for snapshot
        in machine.rollback_snapshots
    )


def test_modern_rollback_history_is_not_state_authority() -> None:
    machine = ModernGpuMachine()
    for tick in range(12):
        machine.step(
            InputFrame(
                tick,
                InputButton.UP,
            )
        )
    snapshot = machine.snapshot()
    before = machine.fingerprint()

    machine.restore(snapshot)

    assert machine.fingerprint() == before
    assert machine.rollback_snapshots == ()


def test_next_policy_adapts_without_code_mutation() -> None:
    machine = NextHybridMachine()
    original = machine.policy

    for tick in range(16):
        machine.step(
            InputFrame(
                tick,
                InputButton.UP,
            )
        )

    assert machine.policy != original
    assert machine.policy_updates == 16
    assert all(
        -1.0 <= weight <= 1.0
        for weight
        in machine.policy.weights
    )
    assert (
        machine.confidence
        >= machine.tuning[
            "confidence_floor"
        ]
    )


def test_next_policy_replay_is_deterministic() -> None:
    def run():
        machine = NextHybridMachine()
        packets = tuple(
            machine.step(
                InputFrame(
                    tick,
                    InputButton.UP
                    | (
                        InputButton.RIGHT
                        if tick % 7 == 0
                        else InputButton.NONE
                    ),
                )
            )
            for tick in range(50)
        )
        return (
            packets,
            machine.fingerprint(),
            machine.policy.digest,
        )

    assert run() == run()


def test_hybrid_policy_rejects_unbounded_weights() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="outside",
    ):
        HybridPolicy(
            (0.0, 1.5)
        )


def test_next_tree_declares_no_code_mutation() -> None:
    tree = build_advanced_engine_tree(
        EngineEra.NEXT,
        "action_adventure",
    )
    payload = json.loads(
        tree.read(
            "engine/hybrid_policy.json"
        )
    )

    assert (
        payload["code_mutation"]
        is False
    )
    assert (
        compile_hybrid_policy(tree)
        == DEFAULT_HYBRID_POLICY
    )


@pytest.mark.parametrize("era", ADVANCED_ERAS)
def test_advanced_tree_contains_runtime_contracts(
    era: EngineEra,
) -> None:
    tree = build_advanced_engine_tree(
        era,
        "action_adventure",
    )

    assert {
        "engine/advanced_pipeline.json",
        "engine/streaming.json",
        "engine/advanced_tuning.json",
        "assets/world_cells.json",
        "engine/advanced_runtime.py",
    } <= set(tree.files)

    assert (
        compile_advanced_tuning(
            era,
            tree,
        )
        == default_advanced_tuning(
            era
        )
    )


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.MODERN,
        EngineEra.NEXT,
    ],
)
def test_data_oriented_eras_carry_ecs_and_rollback_contracts(
    era: EngineEra,
) -> None:
    tree = build_advanced_engine_tree(
        era
    )

    assert {
        "engine/ecs_schema.json",
        "engine/rollback.json",
    } <= set(tree.files)


def test_corrupt_advanced_tuning_is_repaired() -> None:
    lab = AdvancedEngineLab()
    sandbox = lab.create(
        EngineEra.OPEN_WORLD,
        "action_adventure",
    )
    path = "engine/advanced_tuning.json"
    payload = json.loads(
        sandbox.tree.read(path)
    )
    payload["stream_radius"] = 999
    broken = sandbox.apply(
        [
            SandboxPatch(
                path,
                json.dumps(payload),
                sandbox.tree.file_digest(
                    path
                ),
            )
        ]
    )

    assert not lab.evaluate(
        broken
    ).passed

    result = lab.adversarial_improve(
        broken
    )

    assert result.promoted
    assert result.report.passed
    assert len(result.rounds) == 1
    assert result.rounds[0].accepted


def test_corrupt_next_policy_is_repaired() -> None:
    lab = AdvancedEngineLab()
    sandbox = lab.create(
        EngineEra.NEXT
    )
    path = "engine/hybrid_policy.json"
    payload = json.loads(
        sandbox.tree.read(path)
    )
    payload["weights"][0] = 5.0
    broken = sandbox.apply(
        [
            SandboxPatch(
                path,
                json.dumps(payload),
                sandbox.tree.file_digest(
                    path
                ),
            )
        ]
    )

    result = lab.adversarial_improve(
        broken
    )

    assert result.promoted
    assert result.report.passed
    assert (
        compile_hybrid_policy(
            result.sandbox.tree
        )
        == DEFAULT_HYBRID_POLICY
    )


def test_regressing_advanced_candidate_is_not_promoted() -> None:
    lab = AdvancedEngineLab()
    sandbox = lab.create(
        EngineEra.MODERN
    )
    path = "engine/advanced_tuning.json"
    payload = json.loads(
        sandbox.tree.read(path)
    )
    payload["cull_distance"] = 9999
    broken = sandbox.apply(
        [
            SandboxPatch(
                path,
                json.dumps(payload),
                sandbox.tree.file_digest(
                    path
                ),
            )
        ]
    )

    def worse(current, report):
        del report
        return (
            SandboxPatch(
                "engine/rollback.json",
                None,
                current.tree.file_digest(
                    "engine/rollback.json"
                ),
            ),
        )

    result = lab.adversarial_improve(
        broken,
        improver=worse,
    )

    assert not result.promoted
    assert len(result.rounds) == 1
    assert not result.rounds[0].accepted
    assert (
        result.sandbox.tree.digest
        == broken.tree.digest
    )


def test_advanced_snapshot_tamper_is_rejected() -> None:
    machine = NextHybridMachine()
    machine.step()
    snapshot = machine.snapshot()
    forged = replace_snapshot_digest(
        snapshot,
        "0" * 64,
    )

    with pytest.raises(
        GameEngineLabError,
        match="digest mismatch",
    ):
        machine.restore(forged)


def replace_snapshot_digest(
    snapshot,
    digest: str,
):
    return type(snapshot)(
        snapshot.era,
        snapshot.tick,
        snapshot.state,
        digest,
    )
