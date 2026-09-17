from __future__ import annotations

import pytest

from skeleton.jeeves.game_engine_3d import ThreeDMachine
from skeleton.jeeves.game_engine_lab import EngineEra, GameEngineLabError, SandboxPatch
from skeleton.jeeves.game_engine_legacy import LegacyMachine
from skeleton.jeeves.game_engine_modern import ModernMachine
from skeleton.jeeves.game_engine_registry import (
    ERA_FAMILY,
    EngineFamily,
    JeevesGameEngineRegistry,
    build_executable_engine_tree,
    engine_family,
)


def test_registry_covers_every_era_exactly_once() -> None:
    assert set(ERA_FAMILY) == set(EngineEra)
    assert len(ERA_FAMILY) == len(EngineEra)
    assert all(isinstance(family, EngineFamily) for family in ERA_FAMILY.values())


@pytest.mark.parametrize("era", list(EngineEra))
def test_registry_builds_passing_snapshotted_sandbox_for_every_era(
    era: EngineEra,
) -> None:
    registry = JeevesGameEngineRegistry()
    sandbox = registry.create(era, "soulslike")
    report = registry.evaluate(sandbox)

    assert sandbox.era is era
    assert sandbox.family is engine_family(era)
    assert len(sandbox.snapshots) == 1
    assert sandbox.snapshots[0].tree_digest == sandbox.tree.digest
    assert report.passed
    assert report.score == 1.0
    assert report.tree_digest == sandbox.tree.digest


@pytest.mark.parametrize("era", list(EngineEra))
def test_registry_machine_dispatch_matches_era_family(era: EngineEra) -> None:
    machine = JeevesGameEngineRegistry().create(era).machine()
    family = engine_family(era)

    if family is EngineFamily.LEGACY_2D:
        assert isinstance(machine, LegacyMachine)
    elif family is EngineFamily.TRANSITION_3D:
        assert isinstance(machine, ThreeDMachine)
    else:
        assert isinstance(machine, ModernMachine)


@pytest.mark.parametrize("era", list(EngineEra))
def test_tuning_attack_is_detected_repaired_and_snapshotted(
    era: EngineEra,
) -> None:
    registry = JeevesGameEngineRegistry()
    baseline = registry.create(era, "arcade_golden_age")
    attacked = registry.tuning_attack(baseline)
    attacked_report = registry.evaluate(attacked)

    assert not attacked_report.passed

    result = registry.adversarial_improve(attacked)

    assert result.promoted
    assert result.report.passed
    assert result.report.score == 1.0
    assert len(result.rounds) == 1
    assert result.rounds[0].accepted
    assert len(result.sandbox.snapshots) == len(baseline.snapshots) + 1


@pytest.mark.parametrize("era", list(EngineEra))
def test_contract_delete_attack_is_detected_and_recovered(
    era: EngineEra,
) -> None:
    registry = JeevesGameEngineRegistry()
    baseline = registry.create(era)
    attacked = registry.contract_delete_attack(baseline)

    assert not registry.evaluate(attacked).passed

    result = registry.adversarial_improve(attacked)

    assert result.promoted
    assert result.report.passed


def test_quality_matrix_is_deterministic_and_complete() -> None:
    registry = JeevesGameEngineRegistry()
    first = registry.quality_matrix("metroidvania")
    second = registry.quality_matrix("metroidvania")

    assert first == second
    assert first.all_passed
    assert first.minimum_score == 1.0
    assert len(first.entries) == len(EngineEra)
    assert [entry.era for entry in first.entries] == list(EngineEra)
    assert len(first.digest) == 64


@pytest.mark.parametrize("era", list(EngineEra))
def test_full_adversarial_tournament_recovers_each_era(era: EngineEra) -> None:
    report = JeevesGameEngineRegistry().adversarial_tournament(
        era,
        "roguelike",
    )

    assert report.passed
    assert len(report.attacks) == 2
    assert all(attack.detected for attack in report.attacks)
    assert all(attack.recovered for attack in report.attacks)
    assert all(
        attack.attacked_score < attack.before_score
        for attack in report.attacks
    )
    assert all(attack.final_score == 1.0 for attack in report.attacks)
    assert len(report.digest) == 64


def test_managed_snapshot_restores_pre_mutation_tree() -> None:
    registry = JeevesGameEngineRegistry()
    sandbox = registry.create(EngineEra.EIGHT_BIT)
    original = sandbox.tree.digest
    path = "game/main.scene.json"
    mutated = sandbox.apply(
        (
            SandboxPatch(
                path,
                sandbox.tree.read(path) + "\n",
                sandbox.tree.file_digest(path),
            ),
        )
    ).snapshot()

    assert mutated.tree.digest != original
    assert mutated.restore(0).tree.digest == original


def test_managed_family_tamper_fails_closed() -> None:
    registry = JeevesGameEngineRegistry()
    sandbox = registry.create(EngineEra.PONG)
    forged = type(sandbox)(
        sandbox.era,
        EngineFamily.MODERN,
        sandbox.tree,
        sandbox.gameplay_dialect,
        sandbox.sequence,
        sandbox.snapshots,
    )

    with pytest.raises(
        GameEngineLabError,
        match="family mismatch",
    ):
        registry.evaluate(forged)


def test_regressing_registry_candidate_is_not_promoted() -> None:
    registry = JeevesGameEngineRegistry()
    baseline = registry.create(EngineEra.MODERN)
    broken = registry.tuning_attack(baseline)

    def worse(current, report):
        del report
        return (
            SandboxPatch(
                "engine/modern_runtime.py",
                None,
                current.tree.file_digest("engine/modern_runtime.py"),
            ),
        )

    result = registry.adversarial_improve(
        broken,
        improver=worse,
    )

    assert not result.promoted
    assert len(result.rounds) == 1
    assert not result.rounds[0].accepted
    assert result.sandbox.tree.digest == broken.tree.digest


@pytest.mark.parametrize("era", list(EngineEra))
def test_direct_tree_builder_matches_registry_tree(era: EngineEra) -> None:
    tree = build_executable_engine_tree(era, "jrpg")
    sandbox = JeevesGameEngineRegistry().create(era, "jrpg")

    assert tree.digest == sandbox.tree.digest
