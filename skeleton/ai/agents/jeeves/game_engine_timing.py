"""Deterministic historical simulation timing for Jeeves game engines.

This module is not a wall-clock scheduler. Callers provide elapsed nanoseconds;
the clock converts them into bounded simulation work using exact rational
arithmetic. EngineEraProfile.tick_hz remains the authoritative simulation rate.

The timing model evolves from frame-locked early engines through decoupled
simulation/presentation, catch-up clamping, interpolation, and Next multi-rate
domains. No time.time(), monotonic clock, sleep, thread, or platform vsync API
participates in authoritative state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Mapping

from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    engine_era_profile,
)

TIMING_SCHEMA_VERSION = 1
NANOSECONDS_PER_SECOND = 1_000_000_000
MAX_ADVANCE_NS = 10 * NANOSECONDS_PER_SECOND
MAX_TIME_SCALE_NUMERATOR = 16
MAX_TIME_SCALE_DENOMINATOR = 16


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


class TimingMode(str, Enum):
    FRAME_LOCKED = "frame_locked"
    FIXED_INTERPOLATED = "fixed_interpolated"
    MULTI_RATE = "multi_rate"


@dataclass(frozen=True, slots=True)
class TimingDomain:
    name: str
    hz: int

    def __post_init__(self) -> None:
        if (
            not self.name
            or len(self.name) > 32
            or not all(
                char.isalnum()
                or char in "_.-"
                for char in self.name
            )
        ):
            raise GameEngineLabError(
                "timing domain name must be a bounded token"
            )
        if (
            type(self.hz) is not int
            or not 1 <= self.hz <= 2000
        ):
            raise GameEngineLabError(
                "timing domain rate outside [1, 2000]"
            )


@dataclass(frozen=True, slots=True)
class EraTimingPolicy:
    era: EngineEra
    mode: TimingMode
    simulation_hz: int
    presentation_hz: int
    max_catchup_steps: int
    interpolation: bool
    variable_time_scale: bool
    pause_supported: bool
    domains: tuple[TimingDomain, ...]

    def __post_init__(self) -> None:
        profile = engine_era_profile(self.era)
        if self.simulation_hz != profile.tick_hz:
            raise GameEngineLabError(
                "timing policy must preserve era profile tick rate"
            )
        if (
            type(self.presentation_hz) is not int
            or not 1 <= self.presentation_hz <= 1000
            or type(self.max_catchup_steps) is not int
            or not 1 <= self.max_catchup_steps <= 64
        ):
            raise GameEngineLabError(
                "timing policy rate/catchup bounds invalid"
            )
        names = tuple(
            domain.name
            for domain in self.domains
        )
        if len(names) != len(set(names)):
            raise GameEngineLabError(
                "timing domain names must be unique"
            )
        if not any(
            domain.name == "simulation"
            and domain.hz == self.simulation_hz
            for domain in self.domains
        ):
            raise GameEngineLabError(
                "timing policy requires authoritative simulation domain"
            )


def _domains(
    simulation_hz: int,
    *,
    gameplay_hz: int | None = None,
    ai_hz: int | None = None,
    animation_hz: int | None = None,
) -> tuple[TimingDomain, ...]:
    values = [
        TimingDomain(
            "simulation",
            simulation_hz,
        )
    ]
    if (
        gameplay_hz is not None
        and gameplay_hz != simulation_hz
    ):
        values.append(
            TimingDomain(
                "gameplay",
                gameplay_hz,
            )
        )
    if ai_hz is not None:
        values.append(
            TimingDomain(
                "ai",
                ai_hz,
            )
        )
    if animation_hz is not None:
        values.append(
            TimingDomain(
                "animation",
                animation_hz,
            )
        )
    return tuple(values)


def _policy(
    era: EngineEra,
    mode: TimingMode,
    presentation_hz: int,
    catchup: int,
    *,
    interpolation: bool,
    variable_scale: bool,
    pause: bool = True,
    gameplay_hz: int | None = None,
    ai_hz: int | None = None,
    animation_hz: int | None = None,
) -> EraTimingPolicy:
    simulation_hz = engine_era_profile(
        era
    ).tick_hz
    return EraTimingPolicy(
        era,
        mode,
        simulation_hz,
        presentation_hz,
        catchup,
        interpolation,
        variable_scale,
        pause,
        _domains(
            simulation_hz,
            gameplay_hz=gameplay_hz,
            ai_hz=ai_hz,
            animation_hz=animation_hz,
        ),
    )


TIMING_POLICIES: Mapping[
    EngineEra,
    EraTimingPolicy,
] = {
    EngineEra.PONG: _policy(
        EngineEra.PONG,
        TimingMode.FRAME_LOCKED,
        60,
        2,
        interpolation=False,
        variable_scale=False,
    ),
    EngineEra.ARCADE: _policy(
        EngineEra.ARCADE,
        TimingMode.FRAME_LOCKED,
        60,
        2,
        interpolation=False,
        variable_scale=False,
    ),
    EngineEra.EIGHT_BIT: _policy(
        EngineEra.EIGHT_BIT,
        TimingMode.FRAME_LOCKED,
        60,
        2,
        interpolation=False,
        variable_scale=False,
    ),
    EngineEra.SIXTEEN_BIT: _policy(
        EngineEra.SIXTEEN_BIT,
        TimingMode.FRAME_LOCKED,
        60,
        2,
        interpolation=False,
        variable_scale=False,
    ),
    EngineEra.EARLY_3D: _policy(
        EngineEra.EARLY_3D,
        TimingMode.FRAME_LOCKED,
        35,
        2,
        interpolation=False,
        variable_scale=False,
    ),
    EngineEra.FIXED_3D: _policy(
        EngineEra.FIXED_3D,
        TimingMode.FIXED_INTERPOLATED,
        60,
        2,
        interpolation=True,
        variable_scale=False,
    ),
    EngineEra.SHADER: _policy(
        EngineEra.SHADER,
        TimingMode.FIXED_INTERPOLATED,
        60,
        3,
        interpolation=True,
        variable_scale=True,
        animation_hz=30,
    ),
    EngineEra.HD: _policy(
        EngineEra.HD,
        TimingMode.FIXED_INTERPOLATED,
        60,
        4,
        interpolation=True,
        variable_scale=True,
        ai_hz=30,
        animation_hz=60,
    ),
    EngineEra.OPEN_WORLD: _policy(
        EngineEra.OPEN_WORLD,
        TimingMode.FIXED_INTERPOLATED,
        60,
        6,
        interpolation=True,
        variable_scale=True,
        ai_hz=30,
        animation_hz=60,
    ),
    EngineEra.MODERN: _policy(
        EngineEra.MODERN,
        TimingMode.MULTI_RATE,
        120,
        8,
        interpolation=True,
        variable_scale=True,
        gameplay_hz=120,
        ai_hz=60,
        animation_hz=120,
    ),
    EngineEra.NEXT: _policy(
        EngineEra.NEXT,
        TimingMode.MULTI_RATE,
        240,
        16,
        interpolation=True,
        variable_scale=True,
        gameplay_hz=120,
        ai_hz=60,
        animation_hz=120,
    ),
}


def timing_policy(
    era: EngineEra | str,
) -> EraTimingPolicy:
    try:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
    except ValueError as exc:
        raise GameEngineLabError(
            f"unknown engine era: {era!r}"
        ) from exc
    return TIMING_POLICIES[key]


def timing_policy_document(
    era: EngineEra | str,
) -> dict[str, object]:
    policy = timing_policy(era)
    return {
        "schema_version":
            TIMING_SCHEMA_VERSION,
        "engine_era":
            policy.era.value,
        "mode":
            policy.mode.value,
        "simulation_hz":
            policy.simulation_hz,
        "presentation_hz":
            policy.presentation_hz,
        "max_catchup_steps":
            policy.max_catchup_steps,
        "interpolation":
            policy.interpolation,
        "variable_time_scale":
            policy.variable_time_scale,
        "pause_supported":
            policy.pause_supported,
        "domains": [
            {
                "name": domain.name,
                "hz": domain.hz,
            }
            for domain in policy.domains
        ],
        "authoritative_wall_clock":
            False,
    }


@dataclass(
    frozen=True,
    slots=True,
)
class DomainSteps:
    name: str
    steps: int
    total_steps: int


@dataclass(
    frozen=True,
    slots=True,
)
class TimingFrame:
    era: EngineEra
    presentation_index: int
    supplied_delta_ns: int
    scaled_delta_numerator: int
    scaled_delta_denominator: int
    simulation_steps: int
    dropped_simulation_steps: int
    simulation_tick: int
    interpolation_alpha: float
    domains: tuple[DomainSteps, ...]
    paused: bool
    time_scale_numerator: int
    time_scale_denominator: int
    digest: str


@dataclass(
    frozen=True,
    slots=True,
)
class ClockSnapshot:
    era: EngineEra
    presentation_index: int
    simulation_tick: int
    accumulator_numerator: int
    accumulator_denominator: int
    paused: bool
    time_scale_numerator: int
    time_scale_denominator: int
    domain_totals: tuple[
        tuple[str, int],
        ...,
    ]
    domain_phases: tuple[
        tuple[
            str,
            int,
            int,
        ],
        ...,
    ]
    digest: str


class DeterministicGameClock:
    """Caller-driven exact-rational simulation clock."""

    def __init__(
        self,
        era: EngineEra | str,
    ) -> None:
        self.policy = timing_policy(era)
        self.presentation_index = 0
        self.simulation_tick = 0
        self._accumulator_ns = Fraction(0, 1)
        self._domain_accumulators = {
            domain.name: Fraction(0, 1)
            for domain
            in self.policy.domains
            if domain.name != "simulation"
        }
        self._domain_totals = {
            domain.name: 0
            for domain
            in self.policy.domains
        }
        self.paused = False
        self._time_scale = Fraction(1, 1)

    @property
    def era(self) -> EngineEra:
        return self.policy.era

    @property
    def simulation_period_ns(
        self,
    ) -> Fraction:
        return Fraction(
            NANOSECONDS_PER_SECOND,
            self.policy.simulation_hz,
        )

    @property
    def presentation_period_ns(
        self,
    ) -> Fraction:
        return Fraction(
            NANOSECONDS_PER_SECOND,
            self.policy.presentation_hz,
        )

    @property
    def time_scale(
        self,
    ) -> Fraction:
        return self._time_scale

    def set_paused(
        self,
        paused: bool,
    ) -> None:
        if type(paused) is not bool:
            raise GameEngineLabError(
                "paused must be boolean"
            )
        if (
            paused
            and not self.policy.pause_supported
        ):
            raise GameEngineLabError(
                "pause unsupported in engine era"
            )
        self.paused = paused

    def set_time_scale(
        self,
        numerator: int,
        denominator: int = 1,
    ) -> None:
        if (
            type(numerator) is not int
            or type(denominator) is not int
            or denominator <= 0
            or numerator <= 0
            or numerator
            > MAX_TIME_SCALE_NUMERATOR
            or denominator
            > MAX_TIME_SCALE_DENOMINATOR
        ):
            raise GameEngineLabError(
                "time scale ratio outside bounded range"
            )
        value = Fraction(
            numerator,
            denominator,
        )
        if (
            value != 1
            and not self.policy.variable_time_scale
        ):
            raise GameEngineLabError(
                "variable time scale unavailable in engine era"
            )
        self._time_scale = value

    def _domain_step_counts(
        self,
        scaled_delta_ns: Fraction,
    ) -> tuple[
        DomainSteps,
        ...,
    ]:
        rows: list[
            DomainSteps
        ] = []
        self._domain_totals[
            "simulation"
        ] = self.simulation_tick
        rows.append(
            DomainSteps(
                "simulation",
                0,
                self.simulation_tick,
            )
        )
        for domain in self.policy.domains:
            if domain.name == "simulation":
                continue
            accumulator = (
                self._domain_accumulators[
                    domain.name
                ]
                + scaled_delta_ns
            )
            period = Fraction(
                NANOSECONDS_PER_SECOND,
                domain.hz,
            )
            steps = int(
                accumulator
                // period
            )
            accumulator -= (
                steps * period
            )
            self._domain_accumulators[
                domain.name
            ] = accumulator
            self._domain_totals[
                domain.name
            ] += steps
            rows.append(
                DomainSteps(
                    domain.name,
                    steps,
                    self._domain_totals[
                        domain.name
                    ],
                )
            )
        return tuple(rows)

    def advance(
        self,
        delta_ns: int,
    ) -> TimingFrame:
        if (
            type(delta_ns) is not int
            or not 0
            <= delta_ns
            <= MAX_ADVANCE_NS
        ):
            raise GameEngineLabError(
                "timing delta outside bounded nanosecond range"
            )
        supplied = delta_ns
        scaled = (
            Fraction(0, 1)
            if self.paused
            else Fraction(
                delta_ns,
                1,
            )
            * self._time_scale
        )
        previous_accumulator = (
            self._accumulator_ns
        )
        self._accumulator_ns += scaled
        period = (
            self.simulation_period_ns
        )
        available = int(
            self._accumulator_ns
            // period
        )
        steps = min(
            available,
            self.policy.max_catchup_steps,
        )
        dropped = max(
            0,
            available - steps,
        )
        # Consume all whole periods, but only advance auxiliary domains through
        # accepted simulation time. Dropped catch-up work is discarded from
        # every domain so no hidden scheduler can outrun authoritative state.
        self._accumulator_ns -= (
            available * period
        )
        accepted_delta = (
            steps * period
            + (
                self._accumulator_ns
                - previous_accumulator
            )
        )
        if accepted_delta < 0:
            raise GameEngineLabError(
                "timing accepted delta became negative"
            )
        self.simulation_tick += steps
        domain_rows = list(
            self._domain_step_counts(
                accepted_delta
            )
        )
        domain_rows[0] = (
            DomainSteps(
                "simulation",
                steps,
                self.simulation_tick,
            )
        )

        if (
            self.policy.interpolation
            and period > 0
        ):
            alpha = float(
                self._accumulator_ns
                / period
            )
        else:
            alpha = 0.0

        payload = {
            "engine_era":
                self.era.value,
            "presentation_index":
                self.presentation_index,
            "supplied_delta_ns":
                supplied,
            "scaled_delta": (
                scaled.numerator,
                scaled.denominator,
            ),
            "simulation_steps":
                steps,
            "dropped_simulation_steps":
                dropped,
            "simulation_tick":
                self.simulation_tick,
            "interpolation_alpha":
                round(
                    alpha,
                    15,
                ),
            "domains": [
                (
                    row.name,
                    row.steps,
                    row.total_steps,
                )
                for row in domain_rows
            ],
            "paused":
                self.paused,
            "time_scale": (
                self._time_scale.numerator,
                self._time_scale.denominator,
            ),
        }
        frame = TimingFrame(
            self.era,
            self.presentation_index,
            supplied,
            scaled.numerator,
            scaled.denominator,
            steps,
            dropped,
            self.simulation_tick,
            round(
                alpha,
                15,
            ),
            tuple(domain_rows),
            self.paused,
            self._time_scale.numerator,
            self._time_scale.denominator,
            _digest(payload),
        )
        self.presentation_index += 1
        return frame

    def snapshot(self) -> ClockSnapshot:
        payload = {
            "engine_era":
                self.era.value,
            "presentation_index":
                self.presentation_index,
            "simulation_tick":
                self.simulation_tick,
            "accumulator": (
                self._accumulator_ns.numerator,
                self._accumulator_ns.denominator,
            ),
            "paused":
                self.paused,
            "time_scale": (
                self._time_scale.numerator,
                self._time_scale.denominator,
            ),
            "domain_totals":
                tuple(
                    sorted(
                        self._domain_totals.items()
                    )
                ),
            "domain_accumulators": {
                name: (
                    value.numerator,
                    value.denominator,
                )
                for name, value
                in sorted(
                    self._domain_accumulators.items()
                )
            },
        }
        # Domain accumulator state participates indirectly in digest while the
        # public snapshot stores enough information to reconstruct it below.
        state_digest = _digest(payload)
        return ClockSnapshot(
            self.era,
            self.presentation_index,
            self.simulation_tick,
            self._accumulator_ns.numerator,
            self._accumulator_ns.denominator,
            self.paused,
            self._time_scale.numerator,
            self._time_scale.denominator,
            tuple(
                sorted(
                    self._domain_totals.items()
                )
            ),
            tuple(
                (
                    name,
                    value.numerator,
                    value.denominator,
                )
                for name, value
                in sorted(
                    self._domain_accumulators.items()
                )
            ),
            state_digest,
        )

    def restore(
        self,
        snapshot: ClockSnapshot,
    ) -> None:
        if snapshot.era is not self.era:
            raise GameEngineLabError(
                "timing snapshot era mismatch"
            )
        if (
            type(snapshot.presentation_index)
            is not int
            or type(snapshot.simulation_tick)
            is not int
            or snapshot.presentation_index < 0
            or snapshot.simulation_tick < 0
            or type(snapshot.accumulator_numerator)
            is not int
            or type(snapshot.accumulator_denominator)
            is not int
            or snapshot.accumulator_denominator <= 0
            or type(snapshot.paused) is not bool
            or type(snapshot.time_scale_numerator)
            is not int
            or type(snapshot.time_scale_denominator)
            is not int
            or snapshot.time_scale_denominator <= 0
        ):
            raise GameEngineLabError(
                "timing snapshot fields invalid"
            )
        accumulator = Fraction(
            snapshot.accumulator_numerator,
            snapshot.accumulator_denominator,
        )
        if (
            accumulator < 0
            or accumulator
            >= self.simulation_period_ns
        ):
            raise GameEngineLabError(
                "timing snapshot accumulator outside simulation period"
            )
        scale = Fraction(
            snapshot.time_scale_numerator,
            snapshot.time_scale_denominator,
        )
        if (
            scale <= 0
            or snapshot.time_scale_numerator
            > MAX_TIME_SCALE_NUMERATOR
            or snapshot.time_scale_denominator
            > MAX_TIME_SCALE_DENOMINATOR
            or (
                scale != 1
                and not self.policy.variable_time_scale
            )
        ):
            raise GameEngineLabError(
                "timing snapshot time scale violates era policy"
            )
        if (
            snapshot.paused
            and not self.policy.pause_supported
        ):
            raise GameEngineLabError(
                "timing snapshot pause violates era policy"
            )

        totals: dict[str, int] = {}
        for row in snapshot.domain_totals:
            if (
                not isinstance(row, tuple)
                or len(row) != 2
                or not isinstance(row[0], str)
                or type(row[1]) is not int
                or row[1] < 0
                or row[0] in totals
            ):
                raise GameEngineLabError(
                    "timing snapshot domain totals malformed"
                )
            totals[row[0]] = row[1]
        expected_domains = {
            domain.name
            for domain
            in self.policy.domains
        }
        if (
            set(totals)
            != expected_domains
            or totals[
                "simulation"
            ]
            != snapshot.simulation_tick
        ):
            raise GameEngineLabError(
                "timing snapshot domain inventory mismatch"
            )

        expected_phases = (
            expected_domains
            - {"simulation"}
        )
        phases: dict[
            str,
            Fraction,
        ] = {}
        for row in snapshot.domain_phases:
            if (
                not isinstance(row, tuple)
                or len(row) != 3
                or not isinstance(row[0], str)
                or row[0] in phases
                or type(row[1]) is not int
                or type(row[2]) is not int
                or row[2] <= 0
            ):
                raise GameEngineLabError(
                    "timing snapshot domain phase malformed"
                )
            name, numerator, denominator = row
            if name not in expected_phases:
                raise GameEngineLabError(
                    "timing snapshot domain phase inventory mismatch"
                )
            value = Fraction(
                numerator,
                denominator,
            )
            domain = next(
                item
                for item in self.policy.domains
                if item.name == name
            )
            period = Fraction(
                NANOSECONDS_PER_SECOND,
                domain.hz,
            )
            if not 0 <= value < period:
                raise GameEngineLabError(
                    "timing snapshot domain phase outside period"
                )
            phases[name] = value
        if set(phases) != expected_phases:
            raise GameEngineLabError(
                "timing snapshot domain phase inventory mismatch"
            )

        candidate = DeterministicGameClock(
            self.era
        )
        candidate.presentation_index = (
            snapshot.presentation_index
        )
        candidate.simulation_tick = (
            snapshot.simulation_tick
        )
        candidate._accumulator_ns = (
            accumulator
        )
        candidate.paused = (
            snapshot.paused
        )
        candidate._time_scale = scale
        candidate._domain_totals = dict(
            totals
        )
        candidate._domain_accumulators = dict(
            phases
        )
        if (
            candidate.snapshot().digest
            != snapshot.digest
        ):
            raise GameEngineLabError(
                "timing snapshot digest mismatch"
            )

        self.presentation_index = (
            candidate.presentation_index
        )
        self.simulation_tick = (
            candidate.simulation_tick
        )
        self._accumulator_ns = (
            candidate._accumulator_ns
        )
        self.paused = (
            candidate.paused
        )
        self._time_scale = (
            candidate._time_scale
        )
        self._domain_totals = dict(
            candidate._domain_totals
        )
        self._domain_accumulators = dict(
            candidate._domain_accumulators
        )

    def fingerprint(self) -> str:
        return self.snapshot().digest


def build_game_clock(
    era: EngineEra | str,
) -> DeterministicGameClock:
    return DeterministicGameClock(
        era
    )
