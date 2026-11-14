"""B021 mechanics session: record / replay / compare / prove-deterministic.

:class:`MechanicsSession` is a thin, fail-closed façade over the existing
:class:`~skeleton.simulation.game.replay.MechanicsReplay` contract. It does not
re-implement combat, progression, economy or AI transitions; it binds a
:class:`SessionPlan` (seed, start tick, systems, steps) to a canonical plan
digest and proves that recording the same plan yields byte-identical traces,
survives a canonical-JSON round trip, and replays without divergence.

:func:`seeded_skirmish_steps` shows how the lane-addressed
:class:`~skeleton.simulation.game.deterministic.SeededDraws` feed scripted
steps into the replay contract without touching ``random``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from skeleton.simulation.game.deterministic import (
    DeterministicError,
    SeededDraws,
    assert_identical_runs,
)
from skeleton.simulation.game.mechanics import (
    AIBehaviorSpec,
    CombatSystemSpec,
    EconomySystemSpec,
    ProgressionSystemSpec,
)
from skeleton.simulation.game.replay import (
    MAX_SEED,
    MAX_STEPS,
    MAX_TICK,
    GameReplayError,
    MechanicsReplay,
    ReplayComparison,
    ReplayStep,
    ReplayTrace,
    canonical_digest,
    parse_trace,
)

SESSION_SCHEMA: Final = "game.mechanics.session"
SESSION_SCHEMA_VERSION: Final = 1
MAX_PROOF_RUNS: Final = 8
_SYSTEM_KEYS: Final = ("combat", "progression", "economy", "ai_behavior")


class MechanicsSessionError(DeterministicError):
    """Fail-closed session contract error."""

    code = "GAME.SESSION"
    http_status = 422


@dataclass(frozen=True, slots=True)
class SessionPlan:
    """Everything that determines a mechanics run, and nothing else."""

    seed: int
    steps: tuple[ReplayStep, ...]
    tick: int = 0
    combat: CombatSystemSpec | Mapping[str, Any] | None = None
    progression: ProgressionSystemSpec | Mapping[str, Any] | None = None
    economy: EconomySystemSpec | Mapping[str, Any] | None = None
    ai_behavior: AIBehaviorSpec | Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if type(self.seed) is not int or not 0 <= self.seed <= MAX_SEED:
            raise MechanicsSessionError("seed out of range", context={"reason": "out_of_range"})
        if type(self.tick) is not int or not 0 <= self.tick <= MAX_TICK:
            raise MechanicsSessionError("tick out of range", context={"reason": "out_of_range"})
        if not isinstance(self.steps, tuple) or not 0 < len(self.steps) <= MAX_STEPS:
            raise MechanicsSessionError(
                "plan needs 1..MAX_STEPS steps as a tuple",
                context={"reason": "invalid_steps", "max_steps": MAX_STEPS},
            )
        if all(getattr(self, key) is None for key in _SYSTEM_KEYS):
            raise MechanicsSessionError(
                "plan must bind at least one mechanics system",
                context={"reason": "missing_system"},
            )

    def record_kwargs(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "tick": self.tick,
            "steps": self.steps,
            **{key: getattr(self, key) for key in _SYSTEM_KEYS},
        }


@dataclass(frozen=True, slots=True)
class DeterminismProof:
    """Evidence that one plan is reproducible under the replay contract."""

    plan_digest: str
    result_digest: str
    runs: int
    step_count: int
    roundtrip_identical: bool
    replay_identical: bool

    def to_canonical(self) -> dict[str, Any]:
        return {
            "schema": SESSION_SCHEMA,
            "schema_version": SESSION_SCHEMA_VERSION,
            "plan_digest": self.plan_digest,
            "result_digest": self.result_digest,
            "runs": self.runs,
            "step_count": self.step_count,
            "roundtrip_identical": self.roundtrip_identical,
            "replay_identical": self.replay_identical,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_canonical())


@dataclass
class MechanicsSession:
    """Session façade over :class:`MechanicsReplay` (composition, not a fork)."""

    replay_engine: MechanicsReplay = field(default_factory=MechanicsReplay)

    def record(self, plan: SessionPlan) -> ReplayTrace:
        if not isinstance(plan, SessionPlan):
            raise MechanicsSessionError("session plan required", context={"reason": "invalid_plan"})
        return self.replay_engine.record(**plan.record_kwargs())

    def replay(self, trace: ReplayTrace | Mapping[str, Any] | str | bytes) -> ReplayTrace:
        return self.replay_engine.replay(trace)

    def compare(
        self,
        expected: ReplayTrace | Mapping[str, Any] | str | bytes,
        actual: ReplayTrace | Mapping[str, Any] | str | bytes,
    ) -> ReplayComparison:
        return self.replay_engine.compare(expected, actual)

    def plan_digest(self, plan: SessionPlan) -> str:
        """Digest of the normalized plan, as bound by the replay contract.

        Two plans that normalize to the same inputs and steps share a digest
        even if one used spec objects and the other mappings.
        """

        trace = self.record(plan)
        return canonical_digest(
            {
                "schema": SESSION_SCHEMA,
                "schema_version": SESSION_SCHEMA_VERSION,
                "seed": trace.seed,
                "tick": trace.tick,
                "inputs": dict(trace.inputs),
                "steps": [step.to_canonical() for step in trace.steps],
            }
        )

    def prove_deterministic(self, plan: SessionPlan, *, runs: int = 3) -> DeterminismProof:
        """Record ``runs`` times, round-trip, replay; fail closed on any drift."""

        if type(runs) is not int or not 2 <= runs <= MAX_PROOF_RUNS:
            raise MechanicsSessionError(
                "runs must be in [2, MAX_PROOF_RUNS]",
                context={"reason": "out_of_range", "max_runs": MAX_PROOF_RUNS},
            )
        result_digest = assert_identical_runs(lambda: self.record(plan), runs=runs)
        trace = self.record(plan)
        wire = self.replay_engine.dumps(trace)
        restored = self.replay_engine.loads(wire)
        comparison = self.compare(trace, restored)
        if not comparison.identical or self.replay_engine.dumps(restored) != wire:
            raise MechanicsSessionError(
                "trace did not survive canonical round trip",
                context={"reason": "roundtrip_divergence"},
            )
        try:
            replayed = self.replay(wire)
        except GameReplayError as exc:
            raise MechanicsSessionError(
                "recorded trace failed to replay",
                context={"reason": "replay_divergence", "detail": exc.message},
            ) from exc
        if replayed.result_digest != result_digest:
            raise MechanicsSessionError(
                "replay produced a different result digest",
                context={"reason": "replay_divergence"},
            )
        return DeterminismProof(
            plan_digest=self.plan_digest(plan),
            result_digest=result_digest,
            runs=runs,
            step_count=len(trace.steps),
            roundtrip_identical=True,
            replay_identical=True,
        )

    def envelope(self, trace: ReplayTrace | Mapping[str, Any] | str | bytes) -> dict[str, Any]:
        """Canonical session envelope for storage or transport."""

        parsed = parse_trace(trace)
        body = parsed.to_canonical()
        return {
            "schema": SESSION_SCHEMA,
            "schema_version": SESSION_SCHEMA_VERSION,
            "result_digest": parsed.result_digest,
            "envelope_digest": canonical_digest(
                {"schema": SESSION_SCHEMA, "schema_version": SESSION_SCHEMA_VERSION, "trace": body}
            ),
            "trace": body,
        }

    def open_envelope(self, envelope: Mapping[str, Any]) -> ReplayTrace:
        """Verify an envelope and replay it; any tampering fails closed."""

        if not isinstance(envelope, Mapping) or set(envelope) != {
            "schema",
            "schema_version",
            "result_digest",
            "envelope_digest",
            "trace",
        }:
            raise MechanicsSessionError("malformed session envelope", context={"reason": "malformed"})
        if (
            envelope["schema"] != SESSION_SCHEMA
            or envelope["schema_version"] != SESSION_SCHEMA_VERSION
        ):
            raise MechanicsSessionError(
                "incompatible session envelope", context={"reason": "version_mismatch"}
            )
        expected = canonical_digest(
            {
                "schema": SESSION_SCHEMA,
                "schema_version": SESSION_SCHEMA_VERSION,
                "trace": envelope["trace"],
            }
        )
        if expected != envelope["envelope_digest"]:
            raise MechanicsSessionError("session envelope digest mismatch", context={"reason": "tampered"})
        replayed = self.replay(envelope["trace"])
        if replayed.result_digest != envelope["result_digest"]:
            raise MechanicsSessionError("session result digest mismatch", context={"reason": "tampered"})
        return replayed


def seeded_skirmish_steps(
    seed: int,
    *,
    rounds: int,
    actor: str = "hero",
    target: str = "slime",
    currency: str = "gold",
    start_tick: int = 0,
) -> tuple[ReplayStep, ...]:
    """Script combat strikes plus loot payouts from lane-addressed draws.

    Strike damage uses the ``combat.damage`` lane and loot uses ``loot.gold``,
    so changing the loot table never reshuffles combat outcomes.
    """

    if type(rounds) is not int or not 1 <= rounds <= MAX_STEPS // 2:
        raise MechanicsSessionError(
            "rounds out of range", context={"reason": "out_of_range", "max_rounds": MAX_STEPS // 2}
        )
    draws = SeededDraws(seed)
    steps: list[ReplayStep] = []
    for round_index in range(rounds):
        tick = start_tick + round_index + 1
        steps.append(
            ReplayStep(
                kind="combat",
                action="strike",
                at_tick=tick,
                payload={
                    "actor": actor,
                    "target": target,
                    "base_damage": 5 + draws.draw("combat.damage", 16, tick=tick),
                },
            )
        )
        steps.append(
            ReplayStep(
                kind="economy",
                action="transact",
                at_tick=tick,
                payload={"currency": currency, "delta": 1 + draws.draw("loot.gold", 10, tick=tick)},
            )
        )
    return tuple(steps)


__all__ = [
    "SESSION_SCHEMA",
    "SESSION_SCHEMA_VERSION",
    "DeterminismProof",
    "MechanicsSession",
    "MechanicsSessionError",
    "SessionPlan",
    "seeded_skirmish_steps",
]
