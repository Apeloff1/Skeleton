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
from typing import Iterable, Mapping


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


def _sha256(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PolicySimulationError(f"{name} must be a lowercase sha256 digest")
    return value


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
        object.__setattr__(
            self,
            "baseline_trace_digest",
            _sha256("baseline_trace_digest", self.baseline_trace_digest),
        )
        object.__setattr__(
            self,
            "candidate_trace_digest",
            _sha256("candidate_trace_digest", self.candidate_trace_digest),
        )
        if (
            isinstance(self.total_traces, bool)
            or not isinstance(self.total_traces, int)
            or self.total_traces < 0
        ):
            raise PolicySimulationError("total_traces must be a non-negative integer")
        if self.production_authority is not False:
            raise PolicySimulationError("policy simulation cannot grant production authority")
        if self.external_side_effects is not False:
            raise PolicySimulationError("policy simulation cannot permit external side effects")
        if len(self.deltas) > self.total_traces:
            raise PolicySimulationError("delta count exceeds total traces")

        if any(not isinstance(delta, PolicyDelta) for delta in self.deltas):
            raise PolicySimulationError("deltas must contain PolicyDelta values")
        trace_ids = [delta.trace_id for delta in self.deltas]
        if len(trace_ids) != len(set(trace_ids)):
            raise PolicySimulationError("delta trace IDs must be unique")

        counts = dict(self.transition_counts)
        expected_counts: dict[str, int] = {}
        for delta in self.deltas:
            expected_counts[delta.transition] = (
                expected_counts.get(delta.transition, 0) + 1
            )
        if counts != expected_counts:
            raise PolicySimulationError("transition counts do not match deltas")
        object.__setattr__(
            self,
            "transition_counts",
            MappingProxyType(dict(sorted(counts.items()))),
        )

        expected_subjects = tuple(
            sorted({delta.subject_id for delta in self.deltas})
        )
        expected_workloads = tuple(
            sorted({delta.workload_id for delta in self.deltas})
        )
        supplied_subjects = tuple(
            sorted({_token("affected_subject", value) for value in self.affected_subjects})
        )
        supplied_workloads = tuple(
            sorted({_token("affected_workload", value) for value in self.affected_workloads})
        )
        if supplied_subjects != expected_subjects:
            raise PolicySimulationError("affected subjects do not match deltas")
        if supplied_workloads != expected_workloads:
            raise PolicySimulationError("affected workloads do not match deltas")
        object.__setattr__(self, "affected_subjects", supplied_subjects)
        object.__setattr__(self, "affected_workloads", supplied_workloads)

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


def _index_traces(
    name: str,
    traces: Iterable[PolicyTrace],
) -> dict[str, PolicyTrace]:
    rows: dict[str, PolicyTrace] = {}
    try:
        iterator = iter(traces)
    except TypeError as exc:
        raise PolicySimulationError(f"{name} traces must be iterable") from exc
    for trace in iterator:
        if not isinstance(trace, PolicyTrace):
            raise PolicySimulationError(f"{name} traces must contain PolicyTrace values")
        if trace.trace_id in rows:
            raise PolicySimulationError(f"{name} trace IDs must be unique")
        rows[trace.trace_id] = trace
    return rows


def _trace_set_digest(rows: Mapping[str, PolicyTrace]) -> str:
    return _digest(
        [
            {
                "trace_id": trace.trace_id,
                "subject_id": trace.subject_id,
                "workload_id": trace.workload_id,
                "decision": trace.decision,
            }
            for _, trace in sorted(rows.items())
        ]
    )


def simulate_policy_change(
    *,
    simulation_id: str,
    baseline_policy_id: str,
    candidate_policy_id: str,
    baseline_traces: Iterable[PolicyTrace],
    candidate_traces: Iterable[PolicyTrace],
) -> PolicySimulation:
    """Compare two decision traces without executing either policy.

    The two trace sets must describe the exact same governed subjects and
    workloads. This prevents a candidate from appearing safer by omitting
    difficult cases or relabeling identities. Only decision values may differ.
    """

    baseline = _index_traces("baseline", baseline_traces)
    candidate = _index_traces("candidate", candidate_traces)
    if set(baseline) != set(candidate):
        raise PolicySimulationError(
            "baseline and candidate must cover the exact same trace IDs"
        )

    deltas: list[PolicyDelta] = []
    transition_counts: dict[str, int] = {}
    for trace_id in sorted(baseline):
        before = baseline[trace_id]
        after = candidate[trace_id]
        if (
            before.subject_id != after.subject_id
            or before.workload_id != after.workload_id
        ):
            raise PolicySimulationError(
                f"trace identity drifted for {trace_id}"
            )
        if before.decision == after.decision:
            continue
        delta = PolicyDelta(
            trace_id=trace_id,
            subject_id=before.subject_id,
            workload_id=before.workload_id,
            baseline_decision=before.decision,
            candidate_decision=after.decision,
        )
        deltas.append(delta)
        transition_counts[delta.transition] = (
            transition_counts.get(delta.transition, 0) + 1
        )

    return PolicySimulation(
        simulation_id=simulation_id,
        baseline_policy_id=baseline_policy_id,
        candidate_policy_id=candidate_policy_id,
        baseline_trace_digest=_trace_set_digest(baseline),
        candidate_trace_digest=_trace_set_digest(candidate),
        total_traces=len(baseline),
        deltas=tuple(deltas),
        transition_counts=transition_counts,
        affected_subjects=tuple(delta.subject_id for delta in deltas),
        affected_workloads=tuple(delta.workload_id for delta in deltas),
    )


__all__ = [
    "PolicyDelta",
    "PolicySimulation",
    "PolicySimulationError",
    "PolicyTrace",
    "simulate_policy_change",
]
