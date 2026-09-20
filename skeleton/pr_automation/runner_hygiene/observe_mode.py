"""Observe-only policy for scheduled sweeps and non-mutating triggers.

Scheduled automation must never gain mutation authority through Pack E.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .types import (
    Finding,
    HygieneMode,
    HygienePolicy,
    HygieneVerdict,
    SweepTrigger,
)


@dataclass(frozen=True, slots=True)
class ObservePolicy:
    trigger: SweepTrigger
    requested_mode: HygieneMode
    effective_mode: HygieneMode
    forced_observe: bool
    reasons: tuple[str, ...]

    @property
    def allows_mutation_signal(self) -> bool:
        """Pack E never mutates; this flag only gates candidacy signaling."""
        return (
            not self.forced_observe
            and self.effective_mode is not HygieneMode.OBSERVE
            and self.trigger is not SweepTrigger.SCHEDULE
        )


def parse_trigger(value: str | None) -> SweepTrigger:
    if not value:
        return SweepTrigger.MANUAL
    normalized = value.strip().casefold().replace("-", "_")
    mapping = {
        "schedule": SweepTrigger.SCHEDULE,
        "scheduled": SweepTrigger.SCHEDULE,
        "workflow_dispatch": SweepTrigger.WORKFLOW_DISPATCH,
        "workflow_run": SweepTrigger.WORKFLOW_RUN,
        "push": SweepTrigger.PUSH,
        "manual": SweepTrigger.MANUAL,
    }
    if normalized not in mapping:
        # Unknown triggers fail closed to observe.
        return SweepTrigger.SCHEDULE
    return mapping[normalized]


def parse_mode(value: str | None) -> HygieneMode:
    if not value:
        return HygieneMode.OBSERVE
    normalized = value.strip().casefold().replace("-", "_")
    for mode in HygieneMode:
        if mode.value == normalized:
            return mode
    return HygieneMode.OBSERVE


def force_observe_for_schedule(
    trigger: SweepTrigger | str,
    requested_mode: HygieneMode | str,
    *,
    policy: HygienePolicy | None = None,
) -> ObservePolicy:
    trig = parse_trigger(trigger.value if isinstance(trigger, SweepTrigger) else trigger)
    req = parse_mode(requested_mode.value if isinstance(requested_mode, HygieneMode) else requested_mode)
    observe_only = True if policy is None else policy.observe_only_on_schedule
    reasons: list[str] = []
    forced = False
    effective = req
    if trig is SweepTrigger.SCHEDULE and observe_only:
        if req is not HygieneMode.OBSERVE:
            forced = True
            reasons.append("schedule_forces_observe")
        effective = HygieneMode.OBSERVE
        reasons.append("schedule_observe_only")
    elif req is HygieneMode.OBSERVE:
        reasons.append("requested_observe")
    else:
        reasons.append("mode_honored")
    return ObservePolicy(
        trigger=trig,
        requested_mode=req,
        effective_mode=effective,
        forced_observe=forced,
        reasons=tuple(reasons),
    )


def observe_policy_from_env(env: Mapping[str, str]) -> ObservePolicy:
    trigger = env.get("GITHUB_EVENT_NAME") or env.get("HYGIENE_TRIGGER") or "manual"
    mode = env.get("HYGIENE_MODE") or env.get("PR_RUNNER_HYGIENE_MODE") or "observe"
    return force_observe_for_schedule(trigger, mode)


def assess_observe_gate(observe: ObservePolicy) -> tuple[HygieneVerdict, tuple[Finding, ...]]:
    if observe.effective_mode is HygieneMode.OBSERVE:
        findings = ()
        if observe.forced_observe:
            findings = (
                Finding(
                    code="observe.forced_schedule",
                    severity="info",
                    message="scheduled sweep forced into observe-only mode",
                ),
            )
        return HygieneVerdict.OBSERVE, findings
    return HygieneVerdict.ALLOW, ()


def assert_no_mutation_authority(observe: ObservePolicy) -> None:
    """Hard guard used by CLI/report paths — Pack E has no merge calls."""
    if observe.allows_mutation_signal and observe.trigger is SweepTrigger.SCHEDULE:
        raise RuntimeError("invariant violated: schedule must not allow mutation signal")


__all__ = [
    "ObservePolicy",
    "assess_observe_gate",
    "assert_no_mutation_authority",
    "force_observe_for_schedule",
    "observe_policy_from_env",
    "parse_mode",
    "parse_trigger",
]
