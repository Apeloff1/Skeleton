from __future__ import annotations

import json

import pytest

from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_runtime import (
    ERA_FAMILY,
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
