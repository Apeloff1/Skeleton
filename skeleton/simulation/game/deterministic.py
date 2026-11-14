"""B021 deterministic loop primitives over the canonical mechanics replay.

This module adds the pieces that sit *between* a host and
:class:`skeleton.simulation.game.replay.MechanicsReplay`:

* :func:`bounded_draw` -- lane-addressed SHA-256 draws keyed by
  ``(seed, tick, lane, index, modulus)``. No ``random`` module, no wall clock.
* :class:`SeededDraws` -- per-lane draw counters with ``draw``/``chance``,
  a checkpointable ``snapshot``/``restore`` and a canonical ``digest``.
* :class:`DeterministicLoop` -- runs a pure step function over explicit ticks
  (reusing :class:`~skeleton.simulation.game.mechanics_depth.TickClock`) and
  chains a canonical-JSON SHA-256 digest per frame.
* :func:`assert_identical_runs` -- executes a run factory N times and fails
  closed on the first divergent digest.

Canonical JSON and digests are the replay contract's own
(:func:`~skeleton.simulation.game.replay.canonical_dumps`), so a loop trace and
a mechanics trace are hashed under one rule. Every invalid input raises
:class:`DeterministicError`; nothing is silently clamped.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from skeleton.kernel.errors import KernelError
from skeleton.simulation.game.mechanics_depth import TickClock
from skeleton.simulation.game.replay import (
    MAX_SEED,
    MAX_TICK,
    GameReplayError,
    ReplayTrace,
    canonical_digest,
    canonical_dumps,
)

DETERMINISTIC_SCHEMA: Final = "game.deterministic.loop"
DETERMINISTIC_SCHEMA_VERSION: Final = 1
DRAW_SCHEMA: Final = "game.deterministic.draw"

MAX_MODULUS: Final = 2**32
MAX_LANES: Final = 64
MAX_DRAWS_PER_LANE: Final = 1_000_000
MAX_LOOP_TICKS: Final = 10_000
MAX_IDENTICAL_RUNS: Final = 16
GENESIS_DIGEST: Final = "0" * 64

_LANE_RE: Final = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")


class DeterministicError(KernelError):
    """Fail-closed determinism contract error."""

    code = "GAME.DETERMINISM"
    http_status = 422


def _int(name: str, value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise DeterministicError(
            f"{name} must be an integer in [{minimum}, {maximum}]",
            context={"reason": "out_of_range", "field": name},
        )
    return value


def _lane(value: object) -> str:
    if not isinstance(value, str) or not _LANE_RE.match(value):
        raise DeterministicError(
            "draw lane must be a lowercase token",
            context={"reason": "invalid_lane"},
        )
    return value


def _canonical(value: Any, *, what: str) -> str:
    try:
        return canonical_dumps(value)
    except GameReplayError as exc:
        raise DeterministicError(
            f"{what} is not canonical JSON",
            context={"reason": "non_canonical_json", "what": what},
        ) from exc


def _digest(value: Any, *, what: str) -> str:
    _canonical(value, what=what)
    return canonical_digest(value)


def bounded_draw(seed: int, tick: int, lane: str, index: int, modulus: int) -> int:
    """Return a value in ``[0, modulus)`` derived only from the arguments."""

    seed = _int("seed", seed, 0, MAX_SEED)
    tick = _int("tick", tick, 0, MAX_TICK)
    lane = _lane(lane)
    index = _int("index", index, 0, MAX_DRAWS_PER_LANE)
    modulus = _int("modulus", modulus, 1, MAX_MODULUS)
    material = canonical_dumps(
        {
            "schema": DRAW_SCHEMA,
            "schema_version": DETERMINISTIC_SCHEMA_VERSION,
            "seed": seed,
            "tick": tick,
            "lane": lane,
            "index": index,
            "modulus": modulus,
        }
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big") % modulus


class SeededDraws:
    """Lane-addressed seeded entropy with checkpointable counters.

    Each lane has its own monotonically increasing index, so adding draws in
    one lane (for example ``"loot"``) never shifts another lane's sequence
    (for example ``"combat"``). That is what keeps replays stable when content
    is extended.
    """

    __slots__ = ("_seed", "_counters", "_drawn")

    def __init__(self, seed: int, counters: Mapping[str, int] | None = None) -> None:
        self._seed = _int("seed", seed, 0, MAX_SEED)
        self._counters: dict[str, int] = {}
        self._drawn = 0
        for lane, value in sorted((counters or {}).items()):
            self._counters[_lane(lane)] = _int("counter", value, 0, MAX_DRAWS_PER_LANE)
        if len(self._counters) > MAX_LANES:
            raise DeterministicError("too many draw lanes", context={"reason": "lane_budget"})

    @property
    def seed(self) -> int:
        return self._seed

    def draw(self, lane: str, modulus: int, *, tick: int = 0) -> int:
        lane = _lane(lane)
        index = self._counters.get(lane, 0)
        if lane not in self._counters and len(self._counters) >= MAX_LANES:
            raise DeterministicError("too many draw lanes", context={"reason": "lane_budget"})
        if index >= MAX_DRAWS_PER_LANE:
            raise DeterministicError(
                "draw lane exhausted", context={"reason": "draw_budget", "lane": lane}
            )
        value = bounded_draw(self._seed, tick, lane, index, modulus)
        self._counters[lane] = index + 1
        self._drawn += 1
        return value

    def chance(self, lane: str, numerator: int, denominator: int, *, tick: int = 0) -> bool:
        """Integer-only Bernoulli draw: ``True`` with probability n/d."""

        denominator = _int("denominator", denominator, 1, MAX_MODULUS)
        numerator = _int("numerator", numerator, 0, denominator)
        return self.draw(lane, denominator, tick=tick) < numerator

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": DRAW_SCHEMA,
            "schema_version": DETERMINISTIC_SCHEMA_VERSION,
            "seed": self._seed,
            "counters": dict(sorted(self._counters.items())),
        }

    @classmethod
    def restore(cls, snapshot: Mapping[str, Any]) -> "SeededDraws":
        if not isinstance(snapshot, Mapping) or set(snapshot) != {
            "schema",
            "schema_version",
            "seed",
            "counters",
        }:
            raise DeterministicError("malformed entropy snapshot", context={"reason": "malformed"})
        if (
            snapshot["schema"] != DRAW_SCHEMA
            or snapshot["schema_version"] != DETERMINISTIC_SCHEMA_VERSION
        ):
            raise DeterministicError(
                "incompatible entropy snapshot", context={"reason": "version_mismatch"}
            )
        counters = snapshot["counters"]
        if not isinstance(counters, Mapping):
            raise DeterministicError("malformed entropy snapshot", context={"reason": "malformed"})
        return cls(snapshot["seed"], counters)

    def digest(self) -> str:
        return canonical_digest(self.snapshot())


@dataclass(frozen=True, slots=True)
class LoopFrame:
    tick: int
    state_digest: str
    chain_digest: str

    def to_canonical(self) -> dict[str, Any]:
        return {"tick": self.tick, "state_digest": self.state_digest, "chain": self.chain_digest}


@dataclass(frozen=True, slots=True)
class LoopRun:
    seed: int
    start_tick: int
    genesis_digest: str
    frames: tuple[LoopFrame, ...]
    final_state: Mapping[str, Any]
    entropy_digest: str
    trace_digest: str

    def to_canonical(self) -> dict[str, Any]:
        return {
            "schema": DETERMINISTIC_SCHEMA,
            "schema_version": DETERMINISTIC_SCHEMA_VERSION,
            "seed": self.seed,
            "start_tick": self.start_tick,
            "genesis": self.genesis_digest,
            "frames": [frame.to_canonical() for frame in self.frames],
            "final_state": json.loads(canonical_dumps(dict(self.final_state))),
            "entropy_digest": self.entropy_digest,
            "trace_digest": self.trace_digest,
        }


StepFn = Callable[[Mapping[str, Any], int, SeededDraws], Mapping[str, Any]]


class DeterministicLoop:
    """Run a pure step function over fixed ticks with a chained digest trace.

    The step function receives a *copy* of the state (decoded from canonical
    JSON), the current tick and the session's :class:`SeededDraws`. It must
    return the next state as a JSON object. Any non-canonical value (floats
    that are NaN/inf, sets, objects) fails closed instead of being coerced.
    """

    def __init__(self, step: StepFn, *, max_ticks: int = MAX_LOOP_TICKS) -> None:
        if not callable(step):
            raise DeterministicError("step must be callable", context={"reason": "invalid_step"})
        self._step = step
        self._max_ticks = _int("max_ticks", max_ticks, 1, MAX_LOOP_TICKS)

    def run(
        self,
        *,
        seed: int,
        ticks: int,
        initial_state: Mapping[str, Any],
        start_tick: int = 0,
    ) -> LoopRun:
        seed = _int("seed", seed, 0, MAX_SEED)
        ticks = _int("ticks", ticks, 0, self._max_ticks)
        start_tick = _int("start_tick", start_tick, 0, MAX_TICK)
        if start_tick + ticks > MAX_TICK:
            raise DeterministicError("tick budget exceeded", context={"reason": "tick_budget"})
        if not isinstance(initial_state, Mapping):
            raise DeterministicError("state must be a mapping", context={"reason": "invalid_state"})
        state_json = _canonical(dict(initial_state), what="initial state")
        draws = SeededDraws(seed)
        clock = TickClock(tick=start_tick, max_tick=MAX_TICK)
        chain = canonical_digest(
            {
                "schema": DETERMINISTIC_SCHEMA,
                "schema_version": DETERMINISTIC_SCHEMA_VERSION,
                "seed": seed,
                "start_tick": start_tick,
                "genesis": GENESIS_DIGEST,
                "state": json.loads(state_json),
            }
        )
        genesis = chain
        frames: list[LoopFrame] = []
        for _ in range(ticks):
            tick = clock.advance()
            produced = self._step(json.loads(state_json), tick, draws)
            if not isinstance(produced, Mapping):
                raise DeterministicError(
                    "step returned a non-mapping state",
                    context={"reason": "invalid_state", "tick": tick},
                )
            state_json = _canonical(dict(produced), what=f"state at tick {tick}")
            state_digest = canonical_digest(json.loads(state_json))
            chain = canonical_digest({"prev": chain, "tick": tick, "state": state_digest})
            frames.append(LoopFrame(tick=tick, state_digest=state_digest, chain_digest=chain))
        final_state = json.loads(state_json)
        entropy_digest = draws.digest()
        trace_digest = canonical_digest(
            {
                "schema": DETERMINISTIC_SCHEMA,
                "schema_version": DETERMINISTIC_SCHEMA_VERSION,
                "seed": seed,
                "start_tick": start_tick,
                "ticks": ticks,
                "head": chain,
                "entropy": entropy_digest,
            }
        )
        return LoopRun(
            seed=seed,
            start_tick=start_tick,
            genesis_digest=genesis,
            frames=tuple(frames),
            final_state=final_state,
            entropy_digest=entropy_digest,
            trace_digest=trace_digest,
        )

    @staticmethod
    def trace_digest(run: LoopRun) -> str:
        """Recompute and verify a run's trace digest (rejects tampered frames)."""

        if not isinstance(run, LoopRun):
            raise DeterministicError("loop run required", context={"reason": "invalid_run"})
        chain = run.genesis_digest
        expected_tick = run.start_tick
        for index, frame in enumerate(run.frames):
            expected_tick += 1
            recomputed = canonical_digest(
                {"prev": chain, "tick": frame.tick, "state": frame.state_digest}
            )
            if frame.tick != expected_tick or recomputed != frame.chain_digest:
                raise DeterministicError(
                    "loop frame chain broken",
                    context={"reason": "tampered", "frame": index},
                )
            chain = recomputed
        expected = canonical_digest(
            {
                "schema": DETERMINISTIC_SCHEMA,
                "schema_version": DETERMINISTIC_SCHEMA_VERSION,
                "seed": run.seed,
                "start_tick": run.start_tick,
                "ticks": len(run.frames),
                "head": chain,
                "entropy": run.entropy_digest,
            }
        )
        if expected != run.trace_digest:
            raise DeterministicError(
                "loop trace digest mismatch",
                context={"reason": "tampered", "expected": expected, "actual": run.trace_digest},
            )
        return expected


def _run_identity(result: object) -> tuple[str, tuple[str, ...]]:
    if isinstance(result, LoopRun):
        return result.trace_digest, tuple(frame.chain_digest for frame in result.frames)
    if isinstance(result, ReplayTrace):
        return result.result_digest, tuple(result.step_digests)
    if isinstance(result, str) and re.fullmatch(r"[0-9a-f]{64}", result):
        return result, ()
    raise DeterministicError(
        "run factory must return a LoopRun, ReplayTrace, or hex digest",
        context={"reason": "invalid_run", "type": type(result).__name__},
    )


def assert_identical_runs(factory: Callable[[], object], *, runs: int = 2) -> str:
    """Execute ``factory`` ``runs`` times; return the shared digest or fail closed."""

    if not callable(factory):
        raise DeterministicError("factory must be callable", context={"reason": "invalid_run"})
    runs = _int("runs", runs, 2, MAX_IDENTICAL_RUNS)
    baseline, baseline_frames = _run_identity(factory())
    for attempt in range(1, runs):
        digest, frames = _run_identity(factory())
        if digest == baseline and frames == baseline_frames:
            continue
        divergent = next(
            (i for i, (a, b) in enumerate(zip(baseline_frames, frames)) if a != b),
            min(len(baseline_frames), len(frames)),
        )
        raise DeterministicError(
            "non-deterministic execution",
            context={
                "reason": "divergence",
                "attempt": attempt,
                "expected": baseline,
                "actual": digest,
                "first_divergent_frame": divergent,
            },
        )
    return baseline


__all__ = [
    "DETERMINISTIC_SCHEMA",
    "DETERMINISTIC_SCHEMA_VERSION",
    "DeterministicError",
    "DeterministicLoop",
    "LoopFrame",
    "LoopRun",
    "SeededDraws",
    "assert_identical_runs",
    "bounded_draw",
]
