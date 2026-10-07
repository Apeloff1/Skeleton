from __future__ import annotations

import math
from dataclasses import replace

import pytest

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
    engine_era_profile,
)
from skeleton.jeeves.game_engine_legacy import (
    InputFrame,
)
from skeleton.jeeves.game_engine_runtime import (
    ExecutableGameEngineLab,
)
from skeleton.jeeves.game_engine_timing import (
    MAX_ADVANCE_NS,
    TIMING_POLICIES,
    ClockSnapshot,
    DeterministicGameClock,
    TimingMode,
    build_game_clock,
    timing_policy,
    timing_policy_document,
)


def _cadence_deltas(
    hz: int,
    frames: int,
) -> tuple[int, ...]:
    return tuple(
        (
            ((index + 1) * 1_000_000_000)
            // hz
            - (
                index * 1_000_000_000
            )
            // hz
        )
        for index in range(frames)
    )


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_every_era_has_timing_policy_matching_profile_tick_rate(
    era: EngineEra,
) -> None:
    policy = timing_policy(
        era
    )

    assert era in TIMING_POLICIES
    assert policy.era is era
    assert (
        policy.simulation_hz
        == engine_era_profile(
            era
        ).tick_hz
    )
    assert any(
        domain.name
        == "simulation"
        and domain.hz
        == policy.simulation_hz
        for domain
        in policy.domains
    )


def test_timing_modes_progress_from_frame_lock_to_multi_rate() -> None:
    assert (
        timing_policy(
            EngineEra.PONG
        ).mode
        is TimingMode.FRAME_LOCKED
    )
    assert (
        timing_policy(
            EngineEra.FIXED_3D
        ).mode
        is TimingMode.FIXED_INTERPOLATED
    )
    assert (
        timing_policy(
            EngineEra.MODERN
        ).mode
        is TimingMode.MULTI_RATE
    )
    assert (
        timing_policy(
            EngineEra.NEXT
        ).mode
        is TimingMode.MULTI_RATE
    )


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_routed_sandbox_attests_timing_policy(
    era: EngineEra,
) -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        era
    )

    document = __import__(
        "json"
    ).loads(
        sandbox.tree.read(
            "engine/timing_policy.json"
        )
    )

    assert (
        document
        == timing_policy_document(
            era
        )
    )
    assert lab.evaluate(
        sandbox
    ).passed


def test_timing_policy_tamper_is_contract_failure_and_repaired() -> None:
    import json

    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.NEXT
    )
    path = (
        "engine/timing_policy.json"
    )
    document = json.loads(
        sandbox.tree.read(
            path
        )
    )
    document[
        "simulation_hz"
    ] = 1
    broken = sandbox.apply(
        (
            SandboxPatch(
                path,
                json.dumps(
                    document
                ),
                sandbox.tree.file_digest(
                    path
                ),
            ),
        )
    )

    before = lab.evaluate(
        broken
    )
    assert not before.passed
    assert "contract" in before.failed
    assert (
        path
        in before.contract_mismatches
    )

    repaired = broken.apply(
        lab.canonical_repair(
            broken,
            before,
        )
    )

    assert lab.evaluate(
        repaired
    ).passed
    assert (
        json.loads(
            repaired.tree.read(
                path
            )
        )
        == timing_policy_document(
            EngineEra.NEXT
        )
    )


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_one_second_of_presentation_cadence_reaches_exact_simulation_rate(
    era: EngineEra,
) -> None:
    clock = DeterministicGameClock(
        era
    )
    policy = clock.policy
    deltas = _cadence_deltas(
        policy.presentation_hz,
        policy.presentation_hz,
    )

    frames = tuple(
        clock.advance(
            delta
        )
        for delta in deltas
    )

    assert sum(deltas) == 1_000_000_000
    assert (
        clock.simulation_tick
        == policy.simulation_hz
    )
    assert (
        sum(
            frame.simulation_steps
            for frame in frames
        )
        == policy.simulation_hz
    )
    assert (
        sum(
            frame.dropped_simulation_steps
            for frame in frames
        )
        == 0
    )


def test_fixed_3d_runs_30hz_simulation_under_60hz_presentation() -> None:
    clock = DeterministicGameClock(
        EngineEra.FIXED_3D
    )
    deltas = _cadence_deltas(
        60,
        60,
    )
    frames = [
        clock.advance(
            delta
        )
        for delta in deltas
    ]

    assert clock.policy.simulation_hz == 30
    assert clock.policy.presentation_hz == 60
    assert clock.simulation_tick == 30
    assert {
        frame.simulation_steps
        for frame in frames
    } <= {
        0,
        1,
    }
    assert any(
        0.45
        < frame.interpolation_alpha
        < 0.55
        for frame in frames
    )
    assert any(
        frame.interpolation_alpha
        == 0.0
        for frame in frames
    )


def test_frame_locked_eras_report_zero_interpolation() -> None:
    for era in (
        EngineEra.PONG,
        EngineEra.ARCADE,
        EngineEra.EIGHT_BIT,
        EngineEra.SIXTEEN_BIT,
        EngineEra.EARLY_3D,
    ):
        clock = DeterministicGameClock(
            era
        )
        for delta in _cadence_deltas(
            clock.policy.presentation_hz,
            5,
        ):
            assert (
                clock.advance(
                    delta
                ).interpolation_alpha
                == 0.0
            )


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.PONG,
        EngineEra.EARLY_3D,
        EngineEra.FIXED_3D,
        EngineEra.HD,
        EngineEra.MODERN,
        EngineEra.NEXT,
    ],
)
def test_stall_catchup_is_bounded_and_excess_work_is_dropped(
    era: EngineEra,
) -> None:
    clock = DeterministicGameClock(
        era
    )
    frame = clock.advance(
        1_000_000_000
    )

    assert (
        frame.simulation_steps
        == clock.policy.max_catchup_steps
    )
    assert (
        frame.dropped_simulation_steps
        == (
            clock.policy.simulation_hz
            - clock.policy.max_catchup_steps
        )
    )
    assert (
        clock.simulation_tick
        == clock.policy.max_catchup_steps
    )


def test_next_auxiliary_domains_do_not_advance_through_dropped_stall_time() -> None:
    clock = DeterministicGameClock(
        EngineEra.NEXT
    )

    frame = clock.advance(
        1_000_000_000
    )
    domains = {
        row.name: row
        for row in frame.domains
    }

    assert frame.simulation_steps == 16
    assert frame.dropped_simulation_steps == 224
    # 16 accepted 240-Hz simulation steps represent 1/15 second.
    assert domains[
        "gameplay"
    ].steps == 8
    assert domains[
        "animation"
    ].steps == 8
    assert domains[
        "ai"
    ].steps == 4


def test_pause_freezes_all_authoritative_domains() -> None:
    clock = DeterministicGameClock(
        EngineEra.NEXT
    )
    clock.set_paused(
        True
    )

    first = clock.advance(
        500_000_000
    )
    second = clock.advance(
        500_000_000
    )

    assert first.simulation_steps == 0
    assert second.simulation_steps == 0
    assert clock.simulation_tick == 0
    assert all(
        row.total_steps == 0
        for row in second.domains
    )
    assert second.paused
    assert (
        second.presentation_index
        == 1
    )


def test_pause_resume_preserves_fractional_accumulator() -> None:
    clock = DeterministicGameClock(
        EngineEra.FIXED_3D
    )
    half = 16_666_667

    first = clock.advance(
        half
    )
    assert first.simulation_steps == 0
    assert first.interpolation_alpha > 0.49

    clock.set_paused(
        True
    )
    paused = clock.advance(
        2_000_000_000
    )
    assert paused.simulation_steps == 0
    assert (
        paused.interpolation_alpha
        == first.interpolation_alpha
    )

    clock.set_paused(
        False
    )
    resumed = clock.advance(
        half
    )
    assert resumed.simulation_steps == 1


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.PONG,
        EngineEra.ARCADE,
        EngineEra.EIGHT_BIT,
        EngineEra.SIXTEEN_BIT,
        EngineEra.EARLY_3D,
        EngineEra.FIXED_3D,
    ],
)
def test_older_eras_reject_variable_time_scale(
    era: EngineEra,
) -> None:
    clock = DeterministicGameClock(
        era
    )

    with pytest.raises(
        GameEngineLabError,
        match="variable time scale unavailable",
    ):
        clock.set_time_scale(
            2,
            1,
        )


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.SHADER,
        EngineEra.HD,
        EngineEra.OPEN_WORLD,
        EngineEra.MODERN,
        EngineEra.NEXT,
    ],
)
def test_later_eras_support_exact_rational_time_scale(
    era: EngineEra,
) -> None:
    clock = DeterministicGameClock(
        era
    )
    clock.set_time_scale(
        1,
        2,
    )

    deltas = _cadence_deltas(
        clock.policy.presentation_hz,
        clock.policy.presentation_hz,
    )
    for delta in deltas:
        clock.advance(
            delta
        )

    assert (
        clock.time_scale.numerator
        == 1
    )
    assert (
        clock.time_scale.denominator
        == 2
    )
    assert (
        clock.simulation_tick
        == clock.policy.simulation_hz
        // 2
    )


@pytest.mark.parametrize(
    ("numerator", "denominator"),
    [
        (0, 1),
        (-1, 1),
        (17, 1),
        (1, 0),
        (1, 17),
        (True, 1),
    ],
)
def test_time_scale_ratio_is_strictly_bounded(
    numerator,
    denominator,
) -> None:
    clock = DeterministicGameClock(
        EngineEra.NEXT
    )

    with pytest.raises(
        GameEngineLabError,
        match="time scale ratio",
    ):
        clock.set_time_scale(
            numerator,
            denominator,
        )


@pytest.mark.parametrize(
    "delta",
    [
        -1,
        MAX_ADVANCE_NS + 1,
        True,
    ],
)
def test_advance_delta_is_strictly_bounded(
    delta,
) -> None:
    clock = DeterministicGameClock(
        EngineEra.MODERN
    )

    with pytest.raises(
        GameEngineLabError,
        match="timing delta",
    ):
        clock.advance(
            delta
        )


def test_next_multi_rate_domains_have_expected_one_second_totals() -> None:
    clock = DeterministicGameClock(
        EngineEra.NEXT
    )

    for delta in _cadence_deltas(
        240,
        240,
    ):
        last = clock.advance(
            delta
        )

    totals = {
        row.name:
            row.total_steps
        for row in last.domains
    }
    assert totals == {
        "simulation": 240,
        "gameplay": 120,
        "ai": 60,
        "animation": 120,
    }


def test_modern_multi_rate_replay_is_bit_stable() -> None:
    deltas = (
        4_000_000,
        5_000_000,
        10_000_000,
        1_000_000,
        12_000_000,
    ) * 20
    first = DeterministicGameClock(
        EngineEra.MODERN
    )
    second = DeterministicGameClock(
        EngineEra.MODERN
    )

    first_frames = tuple(
        first.advance(
            delta
        )
        for delta in deltas
    )
    second_frames = tuple(
        second.advance(
            delta
        )
        for delta in deltas
    )

    assert first_frames == second_frames
    assert (
        first.fingerprint()
        == second.fingerprint()
    )


def test_clock_snapshot_restores_fractional_multi_rate_phase_exactly() -> None:
    clock = DeterministicGameClock(
        EngineEra.NEXT
    )
    clock.set_time_scale(
        3,
        2,
    )
    for delta in (
        1_000_000,
        2_000_000,
        3_000_000,
        4_000_000,
        5_000_000,
    ):
        clock.advance(
            delta
        )

    snapshot = clock.snapshot()
    expected = clock.fingerprint()
    for _ in range(10):
        clock.advance(
            7_000_000
        )

    clock.restore(
        snapshot
    )

    assert clock.fingerprint() == expected
    assert (
        clock.snapshot()
        == snapshot
    )


def test_clock_snapshot_tamper_fails_without_mutating_live_clock() -> None:
    clock = DeterministicGameClock(
        EngineEra.MODERN
    )
    for delta in (
        4_000_000,
        8_000_000,
        3_000_000,
    ):
        clock.advance(
            delta
        )
    before = clock.snapshot()
    before_fingerprint = (
        clock.fingerprint()
    )
    forged = replace(
        before,
        digest="0" * 64,
    )

    with pytest.raises(
        GameEngineLabError,
        match="digest mismatch",
    ):
        clock.restore(
            forged
        )

    assert (
        clock.fingerprint()
        == before_fingerprint
    )
    assert clock.snapshot() == before


def test_clock_snapshot_rejects_duplicate_domain_phase_identity() -> None:
    clock = DeterministicGameClock(
        EngineEra.NEXT
    )
    clock.advance(
        5_000_000
    )
    snapshot = clock.snapshot()
    row = snapshot.domain_phases[0]
    forged = replace(
        snapshot,
        domain_phases=(
            row,
            row,
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="domain phase",
    ):
        clock.restore(
            forged
        )


def test_timing_clock_can_drive_actual_modern_machine_tick_for_tick() -> None:
    lab = ExecutableGameEngineLab()
    machine = lab.create(
        EngineEra.MODERN
    ).machine()
    clock = DeterministicGameClock(
        EngineEra.MODERN
    )
    frames = []

    for delta in _cadence_deltas(
        120,
        24,
    ):
        timing = clock.advance(
            delta
        )
        for _ in range(
            timing.simulation_steps
        ):
            frames.append(
                machine.step(
                    InputFrame(
                        machine.tick
                    )
                )
            )

    assert clock.simulation_tick == 24
    assert machine.tick == 24
    assert len(frames) == 24


def test_fixed_3d_presentation_can_render_between_simulation_ticks() -> None:
    lab = ExecutableGameEngineLab()
    machine = lab.create(
        EngineEra.FIXED_3D
    ).machine()
    clock = DeterministicGameClock(
        EngineEra.FIXED_3D
    )

    render_frames = 0
    sim_frames = 0
    for delta in _cadence_deltas(
        60,
        12,
    ):
        timing = clock.advance(
            delta
        )
        render_frames += 1
        for _ in range(
            timing.simulation_steps
        ):
            machine.step(
                InputFrame(
                    machine.tick
                )
            )
            sim_frames += 1

    assert render_frames == 12
    assert sim_frames == 6
    assert machine.tick == 6
    assert clock.simulation_tick == 6


def test_builder_returns_clock_for_requested_era() -> None:
    clock = build_game_clock(
        EngineEra.EARLY_3D
    )

    assert isinstance(
        clock,
        DeterministicGameClock,
    )
    assert (
        clock.era
        is EngineEra.EARLY_3D
    )
    assert clock.policy.simulation_hz == 35


def test_jeeves_owns_game_clock_and_advance_boundary() -> None:
    jeeves = Jeeves()
    clock = jeeves.game_clock(
        EngineEra.MODERN
    )

    frame = (
        jeeves.advance_game_clock(
            clock,
            math.ceil(
                float(
                    clock.simulation_period_ns
                )
            ),
        )
    )

    assert frame.simulation_steps == 1
    assert frame.simulation_tick == 1
    assert len(frame.digest) == 64
