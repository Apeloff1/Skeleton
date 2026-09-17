from __future__ import annotations

import json

import pytest

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_runtime import (
    ERA_FAMILY,
    AdversarialEngineEvolution,
    EngineFamily,
    ExecutableGameEngineLab,
    RoutedEngineSandbox,
    build_executable_game_engine,
    engine_family,
)


def test_every_engine_era_has_exactly_one_runtime_family() -> None:
    assert set(ERA_FAMILY) == set(EngineEra)
    assert len(ERA_FAMILY) == len(EngineEra)


def test_runtime_family_partition_is_complete_and_disjoint() -> None:
    groups = {
        family: {
            era
            for era, mapped
            in ERA_FAMILY.items()
            if mapped is family
        }
        for family in EngineFamily
    }

    assert groups[EngineFamily.LEGACY] == {
        EngineEra.PONG,
        EngineEra.ARCADE,
        EngineEra.EIGHT_BIT,
        EngineEra.SIXTEEN_BIT,
    }
    assert groups[EngineFamily.TRANSITION_3D] == {
        EngineEra.EARLY_3D,
        EngineEra.FIXED_3D,
        EngineEra.SHADER,
    }
    assert groups[EngineFamily.MODERN] == {
        EngineEra.HD,
        EngineEra.OPEN_WORLD,
        EngineEra.MODERN,
        EngineEra.NEXT,
    }
    assert not (
        groups[EngineFamily.LEGACY]
        & groups[EngineFamily.TRANSITION_3D]
    )
    assert not (
        groups[EngineFamily.LEGACY]
        & groups[EngineFamily.MODERN]
    )
    assert not (
        groups[EngineFamily.TRANSITION_3D]
        & groups[EngineFamily.MODERN]
    )


@pytest.mark.parametrize("era", list(EngineEra))
def test_unified_lab_builds_and_passes_every_era(
    era: EngineEra,
) -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        era,
        "action_adventure",
    )

    assert sandbox.era is era
    assert sandbox.family is engine_family(era)
    assert sandbox.gameplay_dialect == "action_adventure"
    assert sandbox.tree.files

    report = lab.evaluate(sandbox)

    assert report.passed
    assert report.score == 1.0


@pytest.mark.parametrize("era", list(EngineEra))
def test_unified_machine_has_snapshot_restore_and_step(
    era: EngineEra,
) -> None:
    sandbox = build_executable_game_engine(era)
    machine = sandbox.machine()
    before = machine.snapshot()

    machine.step()
    assert machine.tick == 1

    machine.restore(before)

    assert machine.tick == 0
    assert machine.snapshot().digest == before.digest


def test_build_all_returns_chronological_complete_ladder() -> None:
    lab = ExecutableGameEngineLab()
    sandboxes = lab.build_all(
        "platformer",
    )

    assert tuple(
        sandbox.era
        for sandbox in sandboxes
    ) == tuple(EngineEra)
    assert all(
        sandbox.gameplay_dialect
        == "platformer"
        for sandbox in sandboxes
    )


def test_family_mismatch_fails_closed() -> None:
    lab = ExecutableGameEngineLab()
    valid = lab.create(
        EngineEra.PONG
    )
    forged = RoutedEngineSandbox(
        valid.era,
        EngineFamily.MODERN,
        valid.native,
    )

    with pytest.raises(
        GameEngineLabError,
        match="family",
    ):
        lab.evaluate(forged)


def test_unknown_era_fails_closed() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="unknown",
    ):
        engine_family("not_an_engine")


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.PONG,
        EngineEra.EARLY_3D,
        EngineEra.MODERN,
    ],
)
def test_unified_adversarial_repair_promotes_corrupt_tuning(
    era: EngineEra,
) -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(era)

    if era is EngineEra.PONG:
        path = "engine/legacy_tuning.json"
        payload = json.loads(
            sandbox.tree.read(path)
        )
        payload["paddle_speed"] = 999
    elif era is EngineEra.EARLY_3D:
        path = "engine/3d_tuning.json"
        payload = json.loads(
            sandbox.tree.read(path)
        )
        payload["near_plane"] = 999
    else:
        path = "engine/modern_tuning.json"
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

    before = lab.evaluate(
        broken
    )
    assert not before.passed

    result = lab.adversarial_improve(
        broken,
        target=1.0,
    )

    assert result.promoted
    assert result.report.passed
    assert result.rounds
    assert result.rounds[-1].accepted


def test_build_executable_game_engine_is_single_call_surface() -> None:
    sandbox = build_executable_game_engine(
        EngineEra.NEXT,
        "immersive_sim",
    )

    assert (
        sandbox.family
        is EngineFamily.MODERN
    )
    assert (
        sandbox.gameplay_dialect
        == "immersive_sim"
    )
    assert (
        "engine/adaptive_policy.json"
        in sandbox.tree.files
    )



@pytest.mark.parametrize(
    "era",
    [
        EngineEra.PONG,
        EngineEra.EARLY_3D,
        EngineEra.NEXT,
    ],
)
def test_evolution_session_snapshots_promotions_and_restores_origin(
    era: EngineEra,
) -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        era,
        "action_adventure",
    )
    if era is EngineEra.PONG:
        path = "engine/legacy_tuning.json"
        payload = json.loads(
            sandbox.tree.read(path)
        )
        payload["paddle_speed"] = 999
    elif era is EngineEra.EARLY_3D:
        path = "engine/3d_tuning.json"
        payload = json.loads(
            sandbox.tree.read(path)
        )
        payload["near_plane"] = 999
    else:
        path = "engine/adaptive_policy.json"
        payload = json.loads(
            sandbox.tree.read(path)
        )
        payload["coefficients"] = [
            10,
            0,
            0,
            0,
        ]
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
    evolution = AdversarialEngineEvolution(
        lab
    )
    session = evolution.start(
        broken
    )
    origin_digest = (
        session.sandbox.tree.digest
    )
    before = lab.evaluate(
        broken
    )
    repair = lab.canonical_repair(
        broken,
        before,
    )

    promoted, report, round_result = (
        evolution.tournament_round(
            session,
            (
                (
                    SandboxPatch(
                        "game/noise.txt",
                        "no quality change",
                    ),
                ),
                repair,
            ),
        )
    )

    assert round_result.accepted
    assert report.passed
    assert len(
        promoted.checkpoints
    ) == 2
    assert (
        promoted.checkpoints[1]
        .parent_digest
        == promoted.checkpoints[0]
        .tree_digest
    )
    assert (
        promoted.checkpoints[1]
        .tree_digest
        == promoted.sandbox.tree.digest
    )

    restored = promoted.restore(0)

    assert (
        restored.sandbox.tree.digest
        == origin_digest
    )
    assert not lab.evaluate(
        restored.sandbox
    ).passed


def test_evolution_tournament_rejects_equal_quality_churn() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.SIXTEEN_BIT
    )
    evolution = AdversarialEngineEvolution(
        lab
    )
    session = evolution.start(
        sandbox
    )

    next_session, report, round_result = (
        evolution.tournament_round(
            session,
            (
                (
                    SandboxPatch(
                        "notes/candidate.txt",
                        "cosmetic mutation",
                    ),
                ),
            ),
        )
    )

    assert report.passed
    assert not round_result.accepted
    assert (
        next_session.sandbox.tree.digest
        == sandbox.tree.digest
    )
    assert len(
        next_session.checkpoints
    ) == 1


def test_evolution_tournament_discards_invalid_candidate_and_promotes_repair() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.MODERN
    )
    path = "engine/modern_tuning.json"
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
    evolution = AdversarialEngineEvolution(
        lab
    )
    session = evolution.start(
        broken
    )
    report = lab.evaluate(
        broken
    )
    repair = lab.canonical_repair(
        broken,
        report,
    )

    promoted, selected, round_result = (
        evolution.tournament_round(
            session,
            (
                (
                    SandboxPatch(
                        path,
                        "stale candidate",
                        "0" * 64,
                    ),
                ),
                repair,
            ),
        )
    )

    assert round_result.candidate_count == 2
    assert round_result.accepted
    assert selected.passed
    assert len(
        promoted.checkpoints
    ) == 2


def test_evolution_loop_reaches_target_with_canonical_proposer() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.SHADER
    )
    path = "engine/3d_tuning.json"
    payload = json.loads(
        sandbox.tree.read(path)
    )
    payload["fov_deg"] = 999
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
    evolution = AdversarialEngineEvolution(
        lab
    )
    session = evolution.start(
        broken
    )

    result = evolution.evolve(
        session,
        evolution.canonical_candidates,
        target=1.0,
        max_rounds=4,
    )

    assert result.target_met
    assert result.report.passed
    assert len(result.rounds) == 1
    assert result.rounds[0].accepted
    assert len(
        result.session.checkpoints
    ) == 2



def test_jeeves_owns_engine_lab_lazily() -> None:
    jeeves = Jeeves()

    assert jeeves._game_engines is None

    sandbox = jeeves.build_game_engine(
        EngineEra.PONG,
        gameplay_dialect="arcade_golden_age",
    )

    assert jeeves._game_engines is not None
    assert sandbox.era is EngineEra.PONG
    assert (
        sandbox.gameplay_dialect
        == "arcade_golden_age"
    )
    assert (
        jeeves.evaluate_game_engine(
            sandbox
        ).passed
    )


def test_jeeves_evolves_broken_engine_through_checkpoint_loop() -> None:
    jeeves = Jeeves()
    sandbox = jeeves.build_game_engine(
        EngineEra.EIGHT_BIT,
        gameplay_dialect="platformer",
    )
    path = "engine/legacy_tuning.json"
    payload = json.loads(
        sandbox.tree.read(path)
    )
    payload["jump_impulse"] = 999
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

    assert not (
        jeeves.evaluate_game_engine(
            broken
        ).passed
    )

    result = jeeves.evolve_game_engine(
        broken,
        target=1.0,
        max_rounds=4,
    )

    assert result.target_met
    assert result.report.passed
    assert len(result.rounds) == 1
    assert len(
        result.session.checkpoints
    ) == 2



def test_evolution_lineage_verifies_parent_chain_and_detects_forgery() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.PONG
    )
    path = "engine/legacy_tuning.json"
    payload = json.loads(
        sandbox.tree.read(path)
    )
    payload["paddle_speed"] = 999
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
    evolution = AdversarialEngineEvolution(
        lab
    )
    session = evolution.start(
        broken
    )
    report = lab.evaluate(
        broken
    )
    repair = lab.canonical_repair(
        broken,
        report,
    )
    promoted, _, _ = (
        evolution.tournament_round(
            session,
            (repair,),
        )
    )

    assert promoted.verify_lineage()
    assert len(
        promoted.lineage_digest
    ) == 64

    first, second = (
        promoted.checkpoints
    )
    forged_second = type(second)(
        second.schema_version,
        second.era,
        second.sequence,
        "0" * 64,
        second.tree_digest,
        second.files,
    )
    forged = type(promoted)(
        promoted.sandbox,
        (
            first,
            forged_second,
        ),
        promoted.sequence,
    )

    with pytest.raises(
        GameEngineLabError,
        match="parent mismatch",
    ):
        forged.verify_lineage()
