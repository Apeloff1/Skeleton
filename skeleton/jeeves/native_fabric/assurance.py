"""Evidence-based gate synthesis for large stacked Jeeves PRs.

The source-only job checks Python and structure, not physical hardware or
every GitHub security workflow. CI verdicts are strictly bound to exact SHA:
a green run on an earlier head, skipped stage, pending job or cancelled
workflow cannot be converted into a final-head production readiness pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping, Sequence

from .contracts import ContractHold, digest, exact_integer, identifier, fingerprint


REQUIRED_EXACT_HEAD = (
    "Merge Readiness",
    "Backend Quality",
    "App Foundation E2E",
    "Workflow Input Security",
    "Sealed Context Guard",
    "Artifact Policy",
    "Malware Gate",
    "Repository Hygiene Gate",
    "Secret scanning",
    "Dependency Review",
)


@dataclass(frozen=True, slots=True)
class Gate:
    gate_id: str
    head_sha: str
    state: str
    conclusion: str | None
    attempt: int
    source_only: bool = False

    def __post_init__(self):
        identifier(self.gate_id, "gate")
        digest(self.head_sha)
        if self.state not in ("queued", "waiting", "in_progress", "completed"):
            raise ContractHold("unexpected gate state")
        if self.conclusion is not None and self.conclusion not in (
            "success", "failure", "cancelled", "skipped",
            "timed_out", "action_required", "neutral", "stale",
        ):
            raise ContractHold("unexpected gate conclusion")
        exact_integer(self.attempt, minimum=1, maximum=10000)
        if type(self.source_only) is not bool:
            raise ContractHold("typed gate scope required")


@dataclass(frozen=True, slots=True)
class GateReport:
    head_sha: str
    required_count: int
    passed: tuple[str, ...]
    failed: tuple[str, ...]
    pending: tuple[str, ...]
    missing: tuple[str, ...]
    stale: tuple[str, ...]
    source_only_passed: tuple[str, ...]

    @property
    def fully_qualified(self) -> bool:
        return (not self.failed and not self.pending and
                not self.missing and not self.stale and
                len(self.passed) == self.required_count)

    def to_record(self):
        return {
            "schema": "jeeves.fabric.exact_head_gate_report.v1",
            "head_sha": self.head_sha, "required": self.required_count,
            "passed": list(self.passed), "failed": list(self.failed),
            "pending": list(self.pending), "missing": list(self.missing),
            "stale": list(self.stale),
            "source_only_passed": list(self.source_only_passed),
            "all_required_exact_head_gates_passed": self.fully_qualified,
            "device_qualified": False,
            "release_certified": False,
        }


def summarize_exact_head(
    head_sha: str, gates: Sequence[Gate],
    *, required: Sequence[str] = REQUIRED_EXACT_HEAD,
) -> GateReport:
    digest(head_sha)
    if type(gates) not in (tuple, list) or len(gates) > 10000:
        raise ContractHold("unbounded gate inventory")
    if type(required) not in (tuple, list) or not 1 <= len(required) <= 256:
        raise ContractHold("explicit finite security gate list required")
    normalized = tuple(identifier(x, "required gate") if " " not in x
                       else x for x in required)
    if len(set(normalized)) != len(normalized):
        raise ContractHold("duplicate required gate")
    known = {}
    stale = set()
    source_only = set()
    for gate in gates:
        if not isinstance(gate, Gate):
            raise ContractHold("typed workflow check required")
        if gate.head_sha != head_sha:
            if gate.gate_id in normalized:
                stale.add(gate.gate_id)
            continue
        if gate.source_only and gate.state == "completed" and gate.conclusion == "success":
            source_only.add(gate.gate_id)
        prior = known.get(gate.gate_id)
        if prior is None or gate.attempt > prior.attempt:
            known[gate.gate_id] = gate
        elif prior.attempt == gate.attempt:
            raise ContractHold("duplicate exact-head gate attempt")
    passed, failed, pending, missing = [], [], [], []
    for gate_name in normalized:
        item = known.get(gate_name)
        if item is None:
            missing.append(gate_name)
        elif item.source_only:
            failed.append(gate_name)
        elif item.state != "completed":
            pending.append(gate_name)
        elif item.conclusion == "success":
            passed.append(gate_name)
        else:
            failed.append(gate_name)
    return GateReport(
        head_sha, len(normalized), tuple(sorted(passed)),
        tuple(sorted(failed)), tuple(sorted(pending)),
        tuple(sorted(missing)), tuple(sorted(stale)),
        tuple(sorted(source_only)),
    )


__all__ = ["REQUIRED_EXACT_HEAD", "Gate", "GateReport",
           "summarize_exact_head"]
