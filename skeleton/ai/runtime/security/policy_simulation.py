"""Non-authoritative contracts for deterministic policy simulation.

This module is deliberately evidence-only. It compares already-produced policy
decisions and has no capability to execute tools, mutate policy, grant
authority, or perform external side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Mapping


_DECISIONS = frozenset({"allow", "deny", "abstain"})


class PolicySimulationError(ValueError):
    """A policy-simulation contract or trace-integrity invariant failed."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PolicySimulationError(f"{name} must be non-empty normalized text")
    return value


def _decision(value: object) -> str:
    result = _token("decision", value)
    if result not in _DECISIONS:
        raise PolicySimulationError("decision must be allow, deny, or abstain")
    return result


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PolicySimulationError("policy simulation evidence must be canonical JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PolicyTrace:
    """One bounded policy decision over a governed subject/workload pair."""

    trace_id: str
    subject_id: str
    workload_id: str
    decision: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _token("trace_id", self.trace_id))
        object.__setattr__(self, "subject_id", _token("subject_id", self.subject_id))
        object.__setattr__(self, "workload_id", _token("workload_id", self.workload_id))
        object.__setattr__(self, "decision", _decision(self.decision))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "trace_id": self.trace_id,
                "subject_id": self.subject_id,
                "workload_id": self.workload_id,
                "decision": self.decision,
            }
        )


@dataclass(frozen=True, slots=True)
class PolicyDelta:
    """One decision change for an identity-stable trace."""

    trace_id: str
    subject_id: str
    workload_id: str
    baseline_decision: str
    candidate_decision: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _token("trace_id", self.trace_id))
        object.__setattr__(self, "subject_id", _token("subject_id", self.subject_id))
        object.__setattr__(self, "workload_id", _token("workload_id", self.workload_id))
        object.__setattr__(self, "baseline_decision", _decision(self.baseline_decision))
        object.__setattr__(self, "candidate_decision", _decision(self.candidate_decision))
        if self.baseline_decision == self.candidate_decision:
            raise PolicySimulationError("PolicyDelta requires a changed decision")

    @property
    def transition(self) -> str:
        return f"{self.baseline_decision}->{self.candidate_decision}"


@dataclass(frozen=True, slots=True)
class PolicySimulation:
    """Evidence-only comparison receipt for a candidate policy."""

    simulation_id: str
    baseline_policy_id: str
    candidate_policy_id: str
    baseline_trace_digest: str
    candidate_trace_digest: str
    total_traces: int
    deltas: tuple[PolicyDelta, ...]
    transition_counts: Mapping[str, int]
    affected_subjects: tuple[str, ...]
    affected_workloads: tuple[str, ...]
    production_authority: bool = False
    external_side_effects: bool = False

    def __post_init__(self) -> None:
        for name in ("simulation_id", "baseline_policy_id", "candidate_policy_id"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        if self.baseline_policy_id == self.candidate_policy_id:
            raise PolicySimulationError("candidate policy must differ from baseline policy")
        if isinstance(self.total_traces, bool) or not isinstance(self.total_traces, int) or self.total_traces < 0:
            raise PolicySimulationError("total_traces must be a non-negative integer")
        if self.production_authority is not False:
            raise PolicySimulationError("policy simulation cannot grant production authority")
        if self.external_side_effects is not False:
            raise PolicySimulationError("policy simulation cannot permit external side effects")
        if len(self.deltas) > self.total_traces:
            raise PolicySimulationError("delta count exceeds total traces")

        counts = dict(self.transition_counts)
        if any(
            transition not in {
                f"{left}->{right}"
                for left in _DECISIONS
                for right in _DECISIONS
                if left != right
            }
            for transition in counts
        ):
            raise PolicySimulationError("unknown policy transition")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts.values()):
            raise PolicySimulationError("transition counts must be non-negative integers")
        if sum(counts.values()) != len(self.deltas):
            raise PolicySimulationError("transition counts do not match deltas")
        object.__setattr__(self, "transition_counts", MappingProxyType(dict(sorted(counts.items()))))
        object.__setattr__(self, "affected_subjects", tuple(sorted(set(self.affected_subjects))))
        object.__setattr__(self, "affected_workloads", tuple(sorted(set(self.affected_workloads))))

    @property
    def changed_traces(self) -> int:
        return len(self.deltas)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "simulation_id": self.simulation_id,
                "baseline_policy_id": self.baseline_policy_id,
                "candidate_policy_id": self.candidate_policy_id,
                "baseline_trace_digest": self.baseline_trace_digest,
                "candidate_trace_digest": self.candidate_trace_digest,
                "total_traces": self.total_traces,
                "deltas": [
                    {
                        "trace_id": delta.trace_id,
                        "subject_id": delta.subject_id,
                        "workload_id": delta.workload_id,
                        "baseline_decision": delta.baseline_decision,
                        "candidate_decision": delta.candidate_decision,
                    }
                    for delta in self.deltas
                ],
                "transition_counts": dict(self.transition_counts),
                "affected_subjects": list(self.affected_subjects),
                "affected_workloads": list(self.affected_workloads),
                "production_authority": False,
                "external_side_effects": False,
            }
        )


__all__ = [
    "PolicyDelta",
    "PolicySimulation",
    "PolicySimulationError",
    "PolicyTrace",
]
