"""Deterministic game-loop sessions for Jeeves historical engines.

Input normalization, simulation timing and machine runtimes are independently
deterministic. This module binds those authorities so they cannot silently
drift:

* clock.simulation_tick must equal machine.tick before and after every advance;
* only input samples consumed by simulation ticks in the current presentation
  advance are accepted;
* multiple players are normalized independently then lowered into the existing
  compatibility InputFrame by deterministic button union;
* presentation timing, normalized input digests and machine frame evidence are
  hash-chained;
* snapshots bind machine + clock + replay lineage and truncate descendants on
  restore;
* replay runs from a fresh machine/clock over the same sandbox and must produce
  identical per-advance evidence and final fingerprints.

No wall clock, host input polling, randomness, threads or background execution
participates in authoritative state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from .game_engine_input import (
    InputNormalizer,
    NormalizedInput,
    RawInputSample,
)
from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
)
from .game_engine_legacy import (
    InputButton,
    InputFrame,
)
from .game_engine_runtime import (
    RoutedEngineSandbox,
)
from .game_engine_timing import (
    ClockSnapshot,
    DeterministicGameClock,
    TimingFrame,
)

SESSION_SCHEMA_VERSION = 1
MAX_SESSION_INPUTS_PER_ADVANCE = 256
MAX_SESSION_HISTORY = 100_000


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _sample_document(
    sample: RawInputSample,
) -> dict[str, object]:
    return {
        "tick": sample.tick,
        "player": sample.player,
        "device": sample.device.value,
        "buttons": int(sample.buttons),
        "move": (
            sample.move_x,
            sample.move_y,
        ),
        "aim": (
            sample.aim_x,
            sample.aim_y,
        ),
        "triggers": (
            sample.left_trigger,
            sample.right_trigger,
        ),
        "pointer": (
            sample.pointer_x,
            sample.pointer_y,
        ),
        "motion": (
            sample.motion_x,
            sample.motion_y,
            sample.motion_z,
        ),
        "touch_active":
            sample.touch_active,
    }


@dataclass(frozen=True, slots=True)
class SimulationTickEvidence:
    tick: int
    input_digests: tuple[str, ...]
    players: tuple[int, ...]
    compatibility_buttons: int
    machine_before_digest: str
    machine_after_digest: str
    machine_frame_digest: str
    digest: str


@dataclass(frozen=True, slots=True)
class LoopAdvanceResult:
    era: EngineEra
    presentation_index: int
    timing: TimingFrame
    simulation: tuple[
        SimulationTickEvidence,
        ...,
    ]
    machine_digest: str
    clock_digest: str
    chain_digest: str
    digest: str


@dataclass(frozen=True, slots=True)
class ReplayAdvance:
    delta_ns: int
    samples: tuple[
        RawInputSample,
        ...,
    ]
    result_digest: str
    chain_digest: str


@dataclass(frozen=True, slots=True)
class GameLoopSnapshot:
    schema_version: int
    era: EngineEra
    tree_digest: str
    machine_snapshot: object
    clock_snapshot: ClockSnapshot
    history_size: int
    chain_digest: str
    digest: str


@dataclass(frozen=True, slots=True)
class ReplayVerification:
    passed: bool
    advances: int
    chain_digest: str
    machine_digest: str
    clock_digest: str
    failure_index: int | None
    detail: str


class DeterministicGameLoop:
    """Bind one routed sandbox to input, timing and machine execution."""

    def __init__(
        self,
        sandbox: RoutedEngineSandbox,
    ) -> None:
        self.sandbox = sandbox
        self.era = sandbox.era
        self.machine = sandbox.machine()
        self.clock = (
            DeterministicGameClock(
                self.era
            )
        )
        self.input = InputNormalizer(
            self.era
        )
        self._genesis_digest = _digest(
            {
                "schema_version":
                    SESSION_SCHEMA_VERSION,
                "engine_era":
                    self.era.value,
                "tree_digest":
                    sandbox.tree.digest,
                "machine_digest":
                    self.machine.fingerprint(),
                "clock_digest":
                    self.clock.fingerprint(),
            }
        )
        self._chain_digest = (
            self._genesis_digest
        )
        self._history: list[
            ReplayAdvance
        ] = []
        self._assert_alignment()

    @property
    def chain_digest(self) -> str:
        return self._chain_digest

    @property
    def history(
        self,
    ) -> tuple[
        ReplayAdvance,
        ...,
    ]:
        return tuple(
            self._history
        )

    def _assert_alignment(
        self,
    ) -> None:
        machine_tick = getattr(
            self.machine,
            "tick",
            None,
        )
        if (
            type(machine_tick) is not int
            or machine_tick
            != self.clock.simulation_tick
        ):
            raise GameEngineLabError(
                (
                    "game-loop authority drift: "
                    f"machine_tick={machine_tick!r}, "
                    f"clock_tick={self.clock.simulation_tick}"
                )
            )

    def _normalized_by_tick(
        self,
        samples: tuple[
            RawInputSample,
            ...,
        ],
        *,
        start_tick: int,
        step_count: int,
    ) -> dict[
        int,
        tuple[
            NormalizedInput,
            ...,
        ],
    ]:
        if (
            len(samples)
            > MAX_SESSION_INPUTS_PER_ADVANCE
        ):
            raise GameEngineLabError(
                "game-loop input batch exceeds bounded size"
            )
        normalized = (
            self.input.normalize_many(
                samples
            )
        )
        stop_tick = (
            start_tick
            + step_count
        )
        for item in normalized:
            if (
                item.tick
                < start_tick
                or item.tick
                >= stop_tick
            ):
                raise GameEngineLabError(
                    (
                        "input tick not consumed by current "
                        "simulation advance"
                    )
                )
        grouped: dict[
            int,
            list[
                NormalizedInput
            ],
        ] = {}
        for item in normalized:
            grouped.setdefault(
                item.tick,
                [],
            ).append(
                item
            )
        return {
            tick: tuple(
                sorted(
                    values,
                    key=lambda item:
                        item.player,
                )
            )
            for tick, values
            in grouped.items()
        }

    @staticmethod
    def _compatibility_frame(
        tick: int,
        inputs: tuple[
            NormalizedInput,
            ...,
        ],
    ) -> InputFrame:
        buttons = (
            InputButton.NONE
        )
        for item in inputs:
            if (
                item.tick
                != tick
                or item.compatibility.tick
                != tick
            ):
                raise GameEngineLabError(
                    "normalized input tick identity mismatch"
                )
            buttons |= (
                item.compatibility.buttons
            )
        return InputFrame(
            tick,
            buttons,
        )

    @staticmethod
    def _machine_frame_digest(
        frame: object,
    ) -> str:
        state_digest = getattr(
            frame,
            "state_digest",
            None,
        )
        if (
            isinstance(
                state_digest,
                str,
            )
            and len(
                state_digest
            )
            == 64
        ):
            return state_digest
        return _digest(
            repr(
                frame
            )
        )

    def advance(
        self,
        delta_ns: int,
        samples: Iterable[
            RawInputSample
        ] = (),
    ) -> LoopAdvanceResult:
        if (
            len(self._history)
            >= MAX_SESSION_HISTORY
        ):
            raise GameEngineLabError(
                "game-loop replay history budget exceeded"
            )
        self._assert_alignment()
        raw_samples = tuple(
            samples
        )
        before_clock = (
            self.clock.snapshot()
        )
        before_machine = (
            self.machine.snapshot()
        )
        start_tick = (
            self.machine.tick
        )

        try:
            timing = self.clock.advance(
                delta_ns
            )
            grouped = (
                self._normalized_by_tick(
                    raw_samples,
                    start_tick=
                        start_tick,
                    step_count=
                        timing.simulation_steps,
                )
            )
        except Exception:
            self.clock.restore(
                before_clock
            )
            raise

        expected_clock_tick = (
            start_tick
            + timing.simulation_steps
        )
        if (
            self.clock.simulation_tick
            != expected_clock_tick
        ):
            self.clock.restore(
                before_clock
            )
            raise GameEngineLabError(
                "clock advance violated contiguous simulation tick contract"
            )

        evidence: list[
            SimulationTickEvidence
        ] = []
        executed_steps = 0
        try:
            for tick in range(
                start_tick,
                expected_clock_tick,
            ):
                tick_inputs = (
                    grouped.get(
                        tick,
                        (),
                    )
                )
                compatibility = (
                    self._compatibility_frame(
                        tick,
                        tick_inputs,
                    )
                )
                machine_before_digest = (
                    self.machine.fingerprint()
                )
                frame = self.machine.step(
                    compatibility
                )
                executed_steps += 1
                after_machine = (
                    self.machine.fingerprint()
                )
                frame_digest = (
                    self._machine_frame_digest(
                        frame
                    )
                )
                tick_identity = {
                    "engine_era":
                        self.era.value,
                    "tick":
                        tick,
                    "input_digests":
                        tuple(
                            item.digest
                            for item
                            in tick_inputs
                        ),
                    "players":
                        tuple(
                            item.player
                            for item
                            in tick_inputs
                        ),
                    "compatibility_buttons":
                        int(
                            compatibility.buttons
                        ),
                    "machine_before":
                        machine_before_digest,
                    "machine_after":
                        after_machine,
                    "machine_frame":
                        frame_digest,
                }
                tick_digest = (
                    _digest(
                        tick_identity
                    )
                )
                evidence.append(
                    SimulationTickEvidence(
                        tick,
                        tuple(
                            item.digest
                            for item
                            in tick_inputs
                        ),
                        tuple(
                            item.player
                            for item
                            in tick_inputs
                        ),
                        int(
                            compatibility.buttons
                        ),
                        machine_before_digest,
                        after_machine,
                        frame_digest,
                        tick_digest,
                    )
                )
            self._assert_alignment()
        except Exception:
            restored = False
            rollback = getattr(
                self.machine,
                "rollback",
                None,
            )
            rollback_depth = getattr(
                self.machine,
                "rollback_depth",
                None,
            )
            if (
                executed_steps > 0
                and callable(
                    rollback
                )
                and type(
                    rollback_depth
                )
                is int
                and rollback_depth
                >= executed_steps
            ):
                try:
                    rollback(
                        executed_steps
                    )
                    restored = (
                        self.machine.fingerprint()
                        == before_machine.digest
                    )
                except Exception:
                    restored = False
            if not restored:
                self.machine.restore(
                    before_machine
                )
                clear_history = getattr(
                    self.machine,
                    "clear_rollback_history",
                    None,
                )
                if callable(
                    clear_history
                ):
                    clear_history()
            self.clock.restore(
                before_clock
            )
            self._assert_alignment()
            raise
        machine_digest = (
            self.machine.fingerprint()
        )
        clock_digest = (
            self.clock.fingerprint()
        )
        advance_identity = {
            "schema_version":
                SESSION_SCHEMA_VERSION,
            "engine_era":
                self.era.value,
            "tree_digest":
                self.sandbox.tree.digest,
            "presentation_index":
                timing.presentation_index,
            "timing_digest":
                timing.digest,
            "raw_samples": [
                _sample_document(
                    sample
                )
                for sample
                in raw_samples
            ],
            "simulation_digests":
                tuple(
                    item.digest
                    for item
                    in evidence
                ),
            "machine_digest":
                machine_digest,
            "clock_digest":
                clock_digest,
            "previous_chain":
                self._chain_digest,
        }
        result_digest = (
            _digest(
                advance_identity
            )
        )
        next_chain = _digest(
            {
                "previous":
                    self._chain_digest,
                "advance":
                    result_digest,
            }
        )
        self._chain_digest = (
            next_chain
        )
        self._history.append(
            ReplayAdvance(
                delta_ns,
                raw_samples,
                result_digest,
                next_chain,
            )
        )
        return LoopAdvanceResult(
            self.era,
            timing.presentation_index,
            timing,
            tuple(
                evidence
            ),
            machine_digest,
            clock_digest,
            next_chain,
            result_digest,
        )

    def snapshot(
        self,
    ) -> GameLoopSnapshot:
        self._assert_alignment()
        machine_snapshot = (
            self.machine.snapshot()
        )
        clock_snapshot = (
            self.clock.snapshot()
        )
        payload = {
            "schema_version":
                SESSION_SCHEMA_VERSION,
            "engine_era":
                self.era.value,
            "tree_digest":
                self.sandbox.tree.digest,
            "machine_digest":
                machine_snapshot.digest,
            "clock_digest":
                clock_snapshot.digest,
            "history_size":
                len(
                    self._history
                ),
            "chain_digest":
                self._chain_digest,
        }
        return GameLoopSnapshot(
            SESSION_SCHEMA_VERSION,
            self.era,
            self.sandbox.tree.digest,
            machine_snapshot,
            clock_snapshot,
            len(
                self._history
            ),
            self._chain_digest,
            _digest(
                payload
            ),
        )

    def restore(
        self,
        snapshot: GameLoopSnapshot,
    ) -> None:
        if (
            snapshot.schema_version
            != SESSION_SCHEMA_VERSION
            or snapshot.era
            is not self.era
            or snapshot.tree_digest
            != self.sandbox.tree.digest
            or type(
                snapshot.history_size
            )
            is not int
            or not 0
            <= snapshot.history_size
            <= len(
                self._history
            )
            or not isinstance(
                snapshot.chain_digest,
                str,
            )
            or len(
                snapshot.chain_digest
            )
            != 64
        ):
            raise GameEngineLabError(
                "game-loop snapshot contract mismatch"
            )

        expected_chain = (
            self._genesis_digest
            if snapshot.history_size
            == 0
            else self._history[
                snapshot.history_size
                - 1
            ].chain_digest
        )
        if (
            snapshot.chain_digest
            != expected_chain
        ):
            raise GameEngineLabError(
                "game-loop snapshot lineage mismatch"
            )

        machine_digest = getattr(
            snapshot.machine_snapshot,
            "digest",
            None,
        )
        if (
            not isinstance(
                machine_digest,
                str,
            )
            or len(
                machine_digest
            )
            != 64
        ):
            raise GameEngineLabError(
                "game-loop machine snapshot malformed"
            )
        payload = {
            "schema_version":
                snapshot.schema_version,
            "engine_era":
                snapshot.era.value,
            "tree_digest":
                snapshot.tree_digest,
            "machine_digest":
                machine_digest,
            "clock_digest":
                snapshot.clock_snapshot.digest,
            "history_size":
                snapshot.history_size,
            "chain_digest":
                snapshot.chain_digest,
        }
        if (
            _digest(
                payload
            )
            != snapshot.digest
        ):
            raise GameEngineLabError(
                "game-loop snapshot digest mismatch"
            )

        # Validate both authorities against fresh instances before mutating the
        # live session. This makes malformed snapshots fail closed.
        candidate_machine = (
            self.sandbox.machine()
        )
        candidate_machine.restore(
            snapshot.machine_snapshot
        )
        candidate_clock = (
            DeterministicGameClock(
                self.era
            )
        )
        candidate_clock.restore(
            snapshot.clock_snapshot
        )
        if (
            candidate_machine.tick
            != candidate_clock.simulation_tick
        ):
            raise GameEngineLabError(
                "game-loop snapshot authorities are tick-misaligned"
            )

        self.machine.restore(
            snapshot.machine_snapshot
        )
        clear_history = getattr(
            self.machine,
            "clear_rollback_history",
            None,
        )
        if callable(
            clear_history
        ):
            clear_history()
        self.clock.restore(
            snapshot.clock_snapshot
        )
        self._history = self._history[
            : snapshot.history_size
        ]
        self._chain_digest = (
            snapshot.chain_digest
        )
        self._assert_alignment()

    def verify_replay(
        self,
    ) -> ReplayVerification:
        replay = DeterministicGameLoop(
            self.sandbox
        )
        for index, expected in enumerate(
            self._history
        ):
            try:
                actual = replay.advance(
                    expected.delta_ns,
                    expected.samples,
                )
            except Exception as exc:
                return ReplayVerification(
                    False,
                    index,
                    replay.chain_digest,
                    replay.machine.fingerprint(),
                    replay.clock.fingerprint(),
                    index,
                    (
                        "replay raised "
                        + type(
                            exc
                        ).__name__
                        + ": "
                        + str(
                            exc
                        )
                    ),
                )
            if (
                actual.digest
                != expected.result_digest
                or actual.chain_digest
                != expected.chain_digest
            ):
                return ReplayVerification(
                    False,
                    index + 1,
                    replay.chain_digest,
                    replay.machine.fingerprint(),
                    replay.clock.fingerprint(),
                    index,
                    "replay evidence diverged",
                )

        machine_digest = (
            self.machine.fingerprint()
        )
        clock_digest = (
            self.clock.fingerprint()
        )
        passed = (
            replay.chain_digest
            == self._chain_digest
            and replay.machine.fingerprint()
            == machine_digest
            and replay.clock.fingerprint()
            == clock_digest
        )
        return ReplayVerification(
            passed,
            len(
                self._history
            ),
            replay.chain_digest,
            replay.machine.fingerprint(),
            replay.clock.fingerprint(),
            (
                None
                if passed
                else len(
                    self._history
                )
            ),
            (
                "replay matched"
                if passed
                else "replay final authority diverged"
            ),
        )


def build_game_loop(
    sandbox: RoutedEngineSandbox,
) -> DeterministicGameLoop:
    return DeterministicGameLoop(
        sandbox
    )
