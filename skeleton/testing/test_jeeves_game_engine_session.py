from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace

import pytest

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_input import (
    InputDevice,
    RawInputSample,
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
from skeleton.jeeves.game_engine_runtime import (
    ExecutableGameEngineLab,
)
from skeleton.jeeves.game_engine_session import (
    MAX_REPLAY_TAPE_BYTES,
    DeterministicGameLoop,
    build_game_loop,
    build_replay_tape,
    parse_replay_tape,
    serialize_replay_tape,
    verify_replay_tape,
)




def _repack_replay_payload(
    payload: dict[str, object],
) -> bytes:
    identity = dict(
        payload
    )
    identity.pop(
        "digest",
        None,
    )
    payload = dict(
        payload
    )
    payload["digest"] = (
        hashlib.sha256(
            json.dumps(
                identity,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode(
                "utf-8"
            )
        ).hexdigest()
    )
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode(
        "utf-8"
    )



def _combined_snapshot_digest(
    snapshot,
) -> str:
    payload = {
        "schema_version":
            snapshot.schema_version,
        "engine_era":
            snapshot.era.value,
        "tree_digest":
            snapshot.tree_digest,
        "machine_digest":
            snapshot.machine_snapshot.digest,
        "clock_digest":
            snapshot.clock_snapshot.digest,
        "history_size":
            snapshot.history_size,
        "chain_digest":
            snapshot.chain_digest,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode(
            "utf-8"
        )
    ).hexdigest()

def _one_step_delta(
    loop: DeterministicGameLoop,
) -> int:
    return math.ceil(
        float(
            loop.clock.simulation_period_ns
        )
    )


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_game_loop_keeps_clock_and_machine_tick_aligned(
    era: EngineEra,
) -> None:
    sandbox = (
        ExecutableGameEngineLab()
        .create(
            era
        )
    )
    loop = DeterministicGameLoop(
        sandbox
    )

    result = loop.advance(
        _one_step_delta(
            loop
        )
    )

    assert result.timing.simulation_steps == 1
    assert loop.machine.tick == 1
    assert loop.clock.simulation_tick == 1
    assert len(result.simulation) == 1
    assert result.simulation[0].tick == 0
    assert (
        result.machine_digest
        == loop.machine.fingerprint()
    )
    assert (
        result.clock_digest
        == loop.clock.fingerprint()
    )


def test_pong_two_player_inputs_are_combined_on_same_simulation_tick() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.PONG
        )
    )
    left_before = loop.machine.left_y
    right_before = loop.machine.right_y

    result = loop.advance(
        _one_step_delta(
            loop
        ),
        (
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.PADDLE,
                move_y=-1.0,
            ),
            RawInputSample(
                tick=0,
                player=1,
                device=InputDevice.PADDLE,
                move_y=1.0,
            ),
        ),
    )

    evidence = result.simulation[0]
    assert evidence.players == (
        0,
        1,
    )
    buttons = InputButton(
        evidence.compatibility_buttons
    )
    assert buttons & InputButton.UP
    assert buttons & InputButton.B
    assert loop.machine.left_y < left_before
    assert loop.machine.right_y > right_before


def test_input_outside_consumed_tick_window_is_rejected_without_clock_mutation() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.FIXED_3D
        )
    )
    before = loop.clock.snapshot()

    with pytest.raises(
        GameEngineLabError,
        match="not consumed",
    ):
        loop.advance(
            1,
            (
                RawInputSample(
                    tick=0,
                    player=0,
                    device=InputDevice.ANALOG_PAD,
                ),
            ),
        )

    assert loop.clock.snapshot() == before
    assert loop.machine.tick == 0
    assert loop.history == ()


def test_stale_input_is_rejected_transactionally() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )
    loop.advance(
        _one_step_delta(
            loop
        )
    )
    before_clock = loop.clock.snapshot()
    before_machine = (
        loop.machine.fingerprint()
    )
    before_chain = (
        loop.chain_digest
    )

    with pytest.raises(
        GameEngineLabError,
        match="not consumed",
    ):
        loop.advance(
            _one_step_delta(
                loop
            ),
            (
                RawInputSample(
                    tick=0,
                    player=0,
                    device=InputDevice.DUAL_ANALOG_PAD,
                ),
            ),
        )

    assert loop.clock.snapshot() == before_clock
    assert (
        loop.machine.fingerprint()
        == before_machine
    )
    assert loop.chain_digest == before_chain
    assert len(loop.history) == 1


def test_duplicate_tick_player_input_is_rejected_without_advancing_clock() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )
    sample = RawInputSample(
        tick=0,
        player=0,
        device=InputDevice.DUAL_ANALOG_PAD,
    )
    before = loop.clock.snapshot()

    with pytest.raises(
        GameEngineLabError,
        match="duplicate input sample",
    ):
        loop.advance(
            _one_step_delta(
                loop
            ),
            (
                sample,
                sample,
            ),
        )

    assert loop.clock.snapshot() == before
    assert loop.machine.tick == 0


def test_manual_machine_advance_is_detected_as_authority_drift() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.EIGHT_BIT
        )
    )
    loop.machine.step(
        InputFrame(
            0
        )
    )

    with pytest.raises(
        GameEngineLabError,
        match="authority drift",
    ):
        loop.advance(
            _one_step_delta(
                loop
            )
        )


def test_one_second_next_stall_keeps_bounded_machine_and_clock_steps_aligned() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.NEXT
        )
    )

    result = loop.advance(
        1_000_000_000
    )

    assert result.timing.simulation_steps == 16
    assert (
        result.timing.dropped_simulation_steps
        == 224
    )
    assert len(result.simulation) == 16
    assert loop.machine.tick == 16
    assert loop.clock.simulation_tick == 16


def test_modern_analog_metadata_participates_in_session_evidence() -> None:
    sandbox = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )
    first = build_game_loop(
        sandbox
    )
    second = build_game_loop(
        sandbox
    )
    delta = _one_step_delta(
        first
    )

    first_result = first.advance(
        delta,
        (
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.DUAL_ANALOG_PAD,
                aim_x=0.5,
            ),
        ),
    )
    second_result = second.advance(
        delta,
        (
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.DUAL_ANALOG_PAD,
                aim_x=0.8,
            ),
        ),
    )

    assert (
        first_result.simulation[
            0
        ].compatibility_buttons
        == second_result.simulation[
            0
        ].compatibility_buttons
        == 0
    )
    assert (
        first.machine.fingerprint()
        == second.machine.fingerprint()
    )
    assert (
        first.chain_digest
        != second.chain_digest
    )
    assert (
        first_result.simulation[
            0
        ].input_digests
        != second_result.simulation[
            0
        ].input_digests
    )


def test_replay_from_fresh_machine_matches_every_advance() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )
    delta = _one_step_delta(
        loop
    )

    for tick in range(20):
        loop.advance(
            delta,
            (
                RawInputSample(
                    tick=tick,
                    player=0,
                    device=InputDevice.DUAL_ANALOG_PAD,
                    move_x=(
                        0.8
                        if tick % 2 == 0
                        else -0.8
                    ),
                    aim_x=(
                        0.4
                        if tick % 3 == 0
                        else 0.0
                    ),
                ),
            ),
        )

    verification = (
        loop.verify_replay()
    )

    assert verification.passed
    assert verification.failure_index is None
    assert verification.advances == 20
    assert (
        verification.chain_digest
        == loop.chain_digest
    )
    assert (
        verification.machine_digest
        == loop.machine.fingerprint()
    )
    assert (
        verification.clock_digest
        == loop.clock.fingerprint()
    )


def test_zero_step_presentation_frames_are_part_of_replay_identity() -> None:
    sandbox = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.FIXED_3D
        )
    )
    first = build_game_loop(
        sandbox
    )
    second = build_game_loop(
        sandbox
    )

    first.advance(
        1
    )
    first.advance(
        _one_step_delta(
            first
        )
    )
    second.advance(
        _one_step_delta(
            second
        )
    )

    assert (
        first.machine.fingerprint()
        == second.machine.fingerprint()
    )
    assert (
        first.clock.simulation_tick
        == second.clock.simulation_tick
        == 1
    )
    assert (
        first.chain_digest
        != second.chain_digest
    )


def test_combined_snapshot_restore_truncates_descendant_replay_lineage() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )
    delta = _one_step_delta(
        loop
    )
    for tick in range(3):
        loop.advance(
            delta,
            (
                RawInputSample(
                    tick=tick,
                    player=0,
                    device=InputDevice.DUAL_ANALOG_PAD,
                    move_y=0.7,
                ),
            ),
        )

    snapshot = loop.snapshot()
    expected_machine = (
        loop.machine.fingerprint()
    )
    expected_clock = (
        loop.clock.fingerprint()
    )
    expected_chain = (
        loop.chain_digest
    )

    for tick in range(
        3,
        6,
    ):
        loop.advance(
            delta,
            (
                RawInputSample(
                    tick=tick,
                    player=0,
                    device=InputDevice.DUAL_ANALOG_PAD,
                    move_x=-0.7,
                ),
            ),
        )

    assert len(loop.history) == 6
    loop.restore(
        snapshot
    )

    assert len(loop.history) == 3
    assert loop.machine.tick == 3
    assert loop.clock.simulation_tick == 3
    assert (
        loop.machine.fingerprint()
        == expected_machine
    )
    assert (
        loop.clock.fingerprint()
        == expected_clock
    )
    assert (
        loop.chain_digest
        == expected_chain
    )
    assert (
        loop.machine.rollback_depth
        == 0
    )
    assert loop.verify_replay().passed


def test_tampered_session_snapshot_fails_without_mutating_live_authority() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.NEXT
        )
    )
    loop.advance(
        _one_step_delta(
            loop
        )
    )
    before = loop.snapshot()
    before_machine = (
        loop.machine.fingerprint()
    )
    before_clock = (
        loop.clock.fingerprint()
    )
    forged = replace(
        before,
        digest="0" * 64,
    )

    with pytest.raises(
        GameEngineLabError,
        match="snapshot digest mismatch",
    ):
        loop.restore(
            forged
        )

    assert (
        loop.machine.fingerprint()
        == before_machine
    )
    assert (
        loop.clock.fingerprint()
        == before_clock
    )
    assert loop.snapshot() == before


def test_snapshot_rejects_forged_clock_machine_tick_misalignment() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )
    loop.advance(
        _one_step_delta(
            loop
        )
    )
    snapshot = loop.snapshot()
    forged_clock = replace(
        snapshot.clock_snapshot,
        simulation_tick=0,
        domain_totals=tuple(
            (
                name,
                (
                    0
                    if name
                    == "simulation"
                    else total
                ),
            )
            for name, total
            in snapshot.clock_snapshot.domain_totals
        ),
    )
    forged = replace(
        snapshot,
        clock_snapshot=
            forged_clock,
    )
    # Preserve the outer digest mismatch as the first fail-closed boundary.
    with pytest.raises(
        GameEngineLabError,
    ):
        loop.restore(
            forged
        )


def test_builder_returns_deterministic_loop_for_exact_sandbox() -> None:
    sandbox = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.SHADER
        )
    )

    loop = build_game_loop(
        sandbox
    )

    assert isinstance(
        loop,
        DeterministicGameLoop,
    )
    assert loop.sandbox is sandbox
    assert (
        loop.era
        is EngineEra.SHADER
    )
    assert (
        loop.chain_digest
        == loop.snapshot().chain_digest
    )


def test_jeeves_owns_game_loop_advance_and_replay_boundary() -> None:
    jeeves = Jeeves()
    sandbox = jeeves.build_game_engine(
        EngineEra.MODERN,
        gameplay_dialect=
            "action_adventure",
    )
    loop = jeeves.game_loop(
        sandbox
    )
    delta = _one_step_delta(
        loop
    )

    result = jeeves.advance_game_loop(
        loop,
        delta,
        (
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.DUAL_ANALOG_PAD,
                move_x=0.9,
            ),
        ),
    )
    verification = (
        jeeves.verify_game_loop_replay(
            loop
        )
    )

    assert result.timing.simulation_steps == 1
    assert verification.passed
    assert loop.machine.tick == 1



def test_modern_step_failure_restores_clock_machine_and_prior_rollback_history() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )
    delta = _one_step_delta(
        loop
    )
    for _ in range(3):
        loop.advance(
            delta
        )

    before_machine = (
        loop.machine.fingerprint()
    )
    before_clock = (
        loop.clock.snapshot()
    )
    before_chain = (
        loop.chain_digest
    )
    before_history = (
        loop.history
    )
    before_rollback = (
        loop.machine.rollback_depth
    )
    original_step = (
        loop.machine.step
    )

    def fail_on_second(
        frame: InputFrame,
    ):
        if frame.tick == 4:
            raise GameEngineLabError(
                "injected step failure"
            )
        return original_step(
            frame
        )

    loop.machine.step = fail_on_second

    with pytest.raises(
        GameEngineLabError,
        match="injected step failure",
    ):
        loop.advance(
            delta * 2
        )

    loop.machine.step = original_step
    assert (
        loop.machine.fingerprint()
        == before_machine
    )
    assert loop.clock.snapshot() == before_clock
    assert loop.chain_digest == before_chain
    assert loop.history == before_history
    assert (
        loop.machine.rollback_depth
        == before_rollback
    )


def test_legacy_post_step_failure_restores_pre_advance_snapshot() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.EIGHT_BIT
        )
    )
    before_machine = (
        loop.machine.fingerprint()
    )
    before_clock = (
        loop.clock.snapshot()
    )
    original_step = (
        loop.machine.step
    )

    def mutate_then_fail(
        frame: InputFrame,
    ):
        original_step(
            frame
        )
        raise GameEngineLabError(
            "post-step failure"
        )

    loop.machine.step = mutate_then_fail

    with pytest.raises(
        GameEngineLabError,
        match="post-step failure",
    ):
        loop.advance(
            _one_step_delta(
                loop
            )
        )

    loop.machine.step = original_step
    assert (
        loop.machine.fingerprint()
        == before_machine
    )
    assert loop.clock.snapshot() == before_clock
    assert loop.machine.tick == 0
    assert loop.clock.simulation_tick == 0
    assert loop.history == ()


def test_malformed_clock_object_in_combined_snapshot_fails_closed() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )
    snapshot = loop.snapshot()
    forged = replace(
        snapshot,
        clock_snapshot=object(),
    )

    with pytest.raises(
        GameEngineLabError,
        match="snapshot contract mismatch",
    ):
        loop.restore(
            forged
        )



def test_portable_replay_tape_is_byte_for_byte_deterministic() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )
    delta = _one_step_delta(
        loop
    )
    for tick in range(8):
        loop.advance(
            delta,
            (
                RawInputSample(
                    tick=tick,
                    player=0,
                    device=InputDevice.DUAL_ANALOG_PAD,
                    move_x=0.6,
                    aim_y=(
                        0.5
                        if tick % 2
                        else -0.5
                    ),
                ),
            ),
        )

    first_tape = build_replay_tape(
        loop
    )
    second_tape = build_replay_tape(
        loop
    )
    first_bytes = serialize_replay_tape(
        first_tape
    )
    second_bytes = serialize_replay_tape(
        second_tape
    )
    parsed = parse_replay_tape(
        first_bytes
    )

    assert first_tape == second_tape
    assert first_bytes == second_bytes
    assert parsed == first_tape
    assert len(first_tape.digest) == 64
    assert (
        verify_replay_tape(
            loop.sandbox,
            parsed,
        ).passed
    )


def test_empty_genesis_replay_tape_verifies() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.PONG
        )
    )
    tape = build_replay_tape(
        loop
    )

    assert tape.advances == ()
    verification = verify_replay_tape(
        loop.sandbox,
        tape,
    )
    assert verification.passed
    assert verification.advances == 0


def test_replay_tape_is_bound_to_exact_sandbox_tree() -> None:
    sandbox = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )
    loop = build_game_loop(
        sandbox
    )
    loop.advance(
        _one_step_delta(
            loop
        )
    )
    tape = build_replay_tape(
        loop
    )
    different = sandbox.apply(
        (
            SandboxPatch(
                "notes/replay-mismatch.txt",
                "different authority",
            ),
        )
    )

    with pytest.raises(
        GameEngineLabError,
        match="does not match sandbox authority",
    ):
        verify_replay_tape(
            different,
            tape,
        )


def test_replay_tape_top_level_digest_tamper_is_rejected() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.EIGHT_BIT
        )
    )
    loop.advance(
        _one_step_delta(
            loop
        )
    )
    data = serialize_replay_tape(
        build_replay_tape(
            loop
        )
    )
    payload = json.loads(
        data
    )
    payload["digest"] = "0" * 64
    forged = (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode(
        "utf-8"
    )

    with pytest.raises(
        GameEngineLabError,
        match="tape digest mismatch",
    ):
        parse_replay_tape(
            forged
        )


def test_rehashed_tape_with_forged_advance_evidence_fails_fresh_replay() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )
    loop.advance(
        _one_step_delta(
            loop
        ),
        (
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.DUAL_ANALOG_PAD,
                move_x=0.8,
            ),
        ),
    )
    payload = json.loads(
        serialize_replay_tape(
            build_replay_tape(
                loop
            )
        )
    )
    payload[
        "advances"
    ][0][
        "result_digest"
    ] = "0" * 64
    forged_data = (
        _repack_replay_payload(
            payload
        )
    )
    tape = parse_replay_tape(
        forged_data
    )

    verification = verify_replay_tape(
        loop.sandbox,
        tape,
    )

    assert not verification.passed
    assert verification.failure_index == 0
    assert (
        verification.detail
        == "tape replay evidence diverged"
    )


def test_rehashed_tape_with_forged_final_fingerprint_fails_final_authority() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.SHADER
        )
    )
    loop.advance(
        _one_step_delta(
            loop
        )
    )
    payload = json.loads(
        serialize_replay_tape(
            build_replay_tape(
                loop
            )
        )
    )
    payload[
        "final_machine_digest"
    ] = "0" * 64
    tape = parse_replay_tape(
        _repack_replay_payload(
            payload
        )
    )

    verification = verify_replay_tape(
        loop.sandbox,
        tape,
    )

    assert not verification.passed
    assert (
        verification.failure_index
        == len(tape.advances)
    )
    assert (
        verification.detail
        == "replay tape final authority diverged"
    )


def test_replay_parser_rejects_boolean_button_encoding() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )
    loop.advance(
        _one_step_delta(
            loop
        ),
        (
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.DUAL_ANALOG_PAD,
            ),
        ),
    )
    payload = json.loads(
        serialize_replay_tape(
            build_replay_tape(
                loop
            )
        )
    )
    payload[
        "advances"
    ][0][
        "samples"
    ][0][
        "buttons"
    ] = True

    with pytest.raises(
        GameEngineLabError,
        match="enum encoding",
    ):
        parse_replay_tape(
            _repack_replay_payload(
                payload
            )
        )


def test_replay_parser_rejects_oversized_bytes() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="bytes outside bounds",
    ):
        parse_replay_tape(
            b"x"
            * (
                MAX_REPLAY_TAPE_BYTES
                + 1
            )
        )


def test_jeeves_exports_and_verifies_portable_game_loop_replay() -> None:
    jeeves = Jeeves()
    sandbox = jeeves.build_game_engine(
        EngineEra.MODERN
    )
    loop = jeeves.game_loop(
        sandbox
    )
    loop.advance(
        _one_step_delta(
            loop
        )
    )

    data = jeeves.export_game_loop_replay(
        loop
    )
    verification = (
        jeeves.verify_game_loop_replay_tape(
            sandbox,
            data,
        )
    )

    assert verification.passed
    assert verification.advances == 1



def test_input_batch_order_is_not_part_of_authoritative_replay_identity() -> None:
    sandbox = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.PONG
        )
    )
    first = build_game_loop(
        sandbox
    )
    second = build_game_loop(
        sandbox
    )
    delta = _one_step_delta(
        first
    )
    left = RawInputSample(
        tick=0,
        player=0,
        device=InputDevice.PADDLE,
        move_y=-1.0,
    )
    right = RawInputSample(
        tick=0,
        player=1,
        device=InputDevice.PADDLE,
        move_y=1.0,
    )

    first_result = first.advance(
        delta,
        (
            left,
            right,
        ),
    )
    second_result = second.advance(
        delta,
        (
            right,
            left,
        ),
    )

    assert first_result == second_result
    assert first.chain_digest == second.chain_digest
    assert first.history == second.history
    assert (
        serialize_replay_tape(
            build_replay_tape(
                first
            )
        )
        == serialize_replay_tape(
            build_replay_tape(
                second
            )
        )
    )


def test_game_loop_rejects_non_raw_input_sample_values() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )

    with pytest.raises(
        GameEngineLabError,
        match="RawInputSample",
    ):
        loop.advance(
            _one_step_delta(
                loop
            ),
            (
                object(),
            ),
        )

    assert loop.machine.tick == 0
    assert loop.clock.simulation_tick == 0
    assert loop.history == ()



def test_rehashed_combined_snapshot_cannot_claim_later_state_on_earlier_lineage() -> None:
    loop = build_game_loop(
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
    )
    delta = _one_step_delta(
        loop
    )
    loop.advance(
        delta,
        (
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.DUAL_ANALOG_PAD,
                move_x=0.7,
            ),
        ),
    )
    earlier = loop.snapshot()

    loop.advance(
        delta,
        (
            RawInputSample(
                tick=1,
                player=0,
                device=InputDevice.DUAL_ANALOG_PAD,
                move_y=0.7,
            ),
        ),
    )
    later = loop.snapshot()
    before_machine = (
        loop.machine.fingerprint()
    )
    before_clock = (
        loop.clock.fingerprint()
    )
    forged = replace(
        earlier,
        machine_snapshot=
            later.machine_snapshot,
        clock_snapshot=
            later.clock_snapshot,
    )
    forged = replace(
        forged,
        digest=
            _combined_snapshot_digest(
                forged
            ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="state does not match replay lineage",
    ):
        loop.restore(
            forged
        )

    assert (
        loop.machine.fingerprint()
        == before_machine
    )
    assert (
        loop.clock.fingerprint()
        == before_clock
    )
    assert len(loop.history) == 2
