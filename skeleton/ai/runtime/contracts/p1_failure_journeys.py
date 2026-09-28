"""P1 terminal failure-journey qualification.

P1-PROM-02 is a non-mutating terminal verifier.  It binds the accepted
P1-PROM-01 exact-head bundle to the mandatory failure journeys required by the
P1 execution map.  A missing, stale, non-independent, unrecovered, or
semantically incomplete journey rejects the qualification atomically.

This module never signs promotion and never mutates maturity state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.p1_terminal_evidence import (
    P1_TERMINAL_REQUIRED_TASKS,
    P1TerminalEvidenceDecision,
)


P1_FAILURE_JOURNEY_SCHEMA_VERSION = 1
P1_FAILURE_JOURNEY_TASK_ID = "P1-PROM-02"
P1_FAILURE_JOURNEY_ACCOUNTABILITY_ID = "ACC-P1-PROM-02"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FailureJourneyFamily(str, Enum):
    CLEAN_MACHINE = "clean_machine"
    ROLLBACK = "rollback"
    RESTORE = "restore"
    SATURATION = "saturation"
    PARTITION = "partition"
    ADVERSARIAL = "adversarial"
    PROVIDER_FAILOVER = "provider_failover"
    STALE_EVIDENCE = "stale_evidence"


P1_REQUIRED_FAILURE_JOURNEYS: tuple[FailureJourneyFamily, ...] = tuple(
    FailureJourneyFamily
)
P1_RECOVERY_REQUIRED_JOURNEYS: frozenset[FailureJourneyFamily] = frozenset(
    {
        FailureJourneyFamily.ROLLBACK,
        FailureJourneyFamily.RESTORE,
        FailureJourneyFamily.SATURATION,
        FailureJourneyFamily.PARTITION,
        FailureJourneyFamily.PROVIDER_FAILOVER,
    }
)
P1_FAILURE_JOURNEY_ASSERTIONS: Mapping[
    FailureJourneyFamily,
    tuple[str, ...],
] = {
    FailureJourneyFamily.CLEAN_MACHINE: (
        "clean_install_verified",
        "no_unowned_critical_state",
    ),
    FailureJourneyFamily.ROLLBACK: (
        "rollback_verified",
        "prechange_state_restored",
    ),
    FailureJourneyFamily.RESTORE: (
        "restore_verified",
        "authoritative_state_reconciled",
    ),
    FailureJourneyFamily.SATURATION: (
        "graceful_degradation_verified",
        "capacity_bounds_enforced",
    ),
    FailureJourneyFamily.PARTITION: (
        "partition_failover_verified",
        "split_brain_prevented",
    ),
    FailureJourneyFamily.ADVERSARIAL: (
        "adversarial_blocking_verified",
        "deception_or_policy_conflict_blocks",
    ),
    FailureJourneyFamily.PROVIDER_FAILOVER: (
        "provider_failover_verified",
        "governance_denial_not_routed",
    ),
    FailureJourneyFamily.STALE_EVIDENCE: (
        "stale_evidence_rejected",
        "exact_head_required",
    ),
}


class P1FailureJourneyError(ValueError):
    """Failure-journey evidence is malformed."""


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise P1FailureJourneyError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise P1FailureJourneyError(f"{field} must be normalized")
    return normalized


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise P1FailureJourneyError(f"{field} must be lowercase sha256")
    return text


def _git_sha(value: object, field: str) -> str:
    text = _text(value, field, maximum=40)
    if not _SHA_RE.fullmatch(text):
        raise P1FailureJourneyError(
            f"{field} must be lowercase 40-character git sha"
        )
    return text


def _assertions(
    values: Iterable[str],
    field: str,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise P1FailureJourneyError(
            f"{field} must be an iterable of strings"
        )
    normalized: set[str] = set()
    for value in values:
        item = _text(value, field, maximum=128)
        if not re.fullmatch(r"^[a-z0-9][a-z0-9_:-]{0,127}$", item):
            raise P1FailureJourneyError(
                f"{field} contains non-canonical assertion"
            )
        normalized.add(item)
    if not normalized:
        raise P1FailureJourneyError(f"{field} must be non-empty")
    return tuple(sorted(normalized))


def _evidence(
    values: Iterable[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise P1FailureJourneyError(
            "evidence must contain EvidenceRef"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise P1FailureJourneyError(
                "evidence must contain EvidenceRef"
            )
        _text(item.source, "evidence.source")
        _sha256(item.digest, "evidence.digest")
        _text(item.category, "evidence.category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key:
        raise P1FailureJourneyError("evidence must be non-empty")
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True)
class FailureJourneyReceipt:
    family: FailureJourneyFamily
    repository: str
    commit_sha: str
    verifier_id: str
    verifier_digest: str
    test_manifest_digest: str
    evidence: tuple[EvidenceRef, ...]
    assertions: tuple[str, ...]
    passed: bool = True
    independent: bool = True
    recovered: bool = False
    production_mutation_count: int = 0

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "family",
                FailureJourneyFamily(self.family),
            )
        except ValueError as exc:
            raise P1FailureJourneyError(
                "invalid failure journey family"
            ) from exc
        repository = _text(
            self.repository,
            "repository",
            maximum=200,
        )
        if repository.count("/") != 1:
            raise P1FailureJourneyError(
                "repository must be owner/name"
            )
        object.__setattr__(
            self,
            "commit_sha",
            _git_sha(self.commit_sha, "commit_sha"),
        )
        object.__setattr__(
            self,
            "verifier_id",
            _text(self.verifier_id, "verifier_id"),
        )
        object.__setattr__(
            self,
            "verifier_digest",
            _sha256(self.verifier_digest, "verifier_digest"),
        )
        object.__setattr__(
            self,
            "test_manifest_digest",
            _sha256(
                self.test_manifest_digest,
                "test_manifest_digest",
            ),
        )
        object.__setattr__(
            self,
            "evidence",
            _evidence(self.evidence),
        )
        object.__setattr__(
            self,
            "assertions",
            _assertions(self.assertions, "assertions"),
        )
        for field in ("passed", "independent", "recovered"):
            if not isinstance(getattr(self, field), bool):
                raise P1FailureJourneyError(
                    f"{field} must be boolean"
                )
        if (
            isinstance(self.production_mutation_count, bool)
            or not isinstance(self.production_mutation_count, int)
            or self.production_mutation_count < 0
        ):
            raise P1FailureJourneyError(
                "production_mutation_count must be non-negative integer"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "family": self.family.value,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "verifier_id": self.verifier_id,
            "verifier_digest": self.verifier_digest,
            "test_manifest_digest": self.test_manifest_digest,
            "evidence": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence
            ],
            "assertions": list(self.assertions),
            "passed": self.passed,
            "independent": self.independent,
            "recovered": self.recovered,
            "production_mutation_count": self.production_mutation_count,
        }

    @property
    def receipt_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class FailureJourneyEvidence:
    family: FailureJourneyFamily
    receipt_digest: str
    verifier_digest: str
    test_manifest_digest: str

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "family",
                FailureJourneyFamily(self.family),
            )
        except ValueError as exc:
            raise P1FailureJourneyError(
                "invalid journey evidence family"
            ) from exc
        for field in (
            "receipt_digest",
            "verifier_digest",
            "test_manifest_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )

    def payload(self) -> dict[str, str]:
        return {
            "family": self.family.value,
            "receipt_digest": self.receipt_digest,
            "verifier_digest": self.verifier_digest,
            "test_manifest_digest": self.test_manifest_digest,
        }


@dataclass(frozen=True, slots=True)
class P1FailureJourneyDecision:
    accepted: bool
    reasons: tuple[str, ...]
    repository: str
    commit_sha: str
    terminal_evidence_digest: str
    journey_evidence: tuple[FailureJourneyEvidence, ...]
    task_id: str = P1_FAILURE_JOURNEY_TASK_ID
    accountability_id: str = P1_FAILURE_JOURNEY_ACCOUNTABILITY_ID
    schema_version: int = P1_FAILURE_JOURNEY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise P1FailureJourneyError(
                "accepted must be boolean"
            )
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item
            for item in self.reasons
        ):
            raise P1FailureJourneyError(
                "reasons must contain non-empty strings"
            )
        repository = _text(
            self.repository,
            "repository",
            maximum=200,
        )
        if repository.count("/") != 1:
            raise P1FailureJourneyError(
                "repository must be owner/name"
            )
        object.__setattr__(
            self,
            "commit_sha",
            _git_sha(self.commit_sha, "commit_sha"),
        )
        object.__setattr__(
            self,
            "terminal_evidence_digest",
            _sha256(
                self.terminal_evidence_digest,
                "terminal_evidence_digest",
            ),
        )
        if not isinstance(self.journey_evidence, tuple) or any(
            not isinstance(item, FailureJourneyEvidence)
            for item in self.journey_evidence
        ):
            raise P1FailureJourneyError(
                "journey_evidence must contain FailureJourneyEvidence"
            )
        if self.task_id != P1_FAILURE_JOURNEY_TASK_ID:
            raise P1FailureJourneyError("task_id drift")
        if self.accountability_id != P1_FAILURE_JOURNEY_ACCOUNTABILITY_ID:
            raise P1FailureJourneyError(
                "accountability_id drift"
            )
        if self.schema_version != P1_FAILURE_JOURNEY_SCHEMA_VERSION:
            raise P1FailureJourneyError(
                "unsupported failure journey schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "terminal_evidence_digest": self.terminal_evidence_digest,
            "journey_evidence": [
                item.payload() for item in self.journey_evidence
            ],
            "promotion_authority": False,
            "signed_promotion": False,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:prom-02:failure-journey-qualification",
    ) -> EvidenceRef:
        if not self.accepted:
            raise P1FailureJourneyError(
                "rejected failure journeys cannot become evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="p1_failure_journey_qualification",
        )


def qualify_p1_failure_journeys(
    *,
    terminal_evidence: P1TerminalEvidenceDecision,
    receipts: Iterable[FailureJourneyReceipt],
    expected_repository: str,
    expected_head: str,
) -> P1FailureJourneyDecision:
    """Join all mandatory failure journeys to an exact-head PROM-01 bundle."""

    if not isinstance(
        terminal_evidence,
        P1TerminalEvidenceDecision,
    ):
        raise TypeError(
            "terminal_evidence must be P1TerminalEvidenceDecision"
        )

    repository = _text(
        expected_repository,
        "expected_repository",
        maximum=200,
    )
    if repository.count("/") != 1:
        raise P1FailureJourneyError(
            "expected_repository must be owner/name"
        )
    head = _git_sha(expected_head, "expected_head")
    reasons: list[str] = []

    if not terminal_evidence.accepted:
        reasons.append("terminal-evidence-rejected")
    if not terminal_evidence.promotion_ready:
        reasons.append("terminal-evidence-not-promotion-ready")
    if terminal_evidence.repository != repository:
        reasons.append("terminal-repository-mismatch")
    if terminal_evidence.commit_sha != head:
        reasons.append("terminal-exact-head-mismatch")
    if terminal_evidence.promotion_blockers:
        reasons.append("terminal-promotion-blockers-present")

    expected_terminal_tasks = dict(P1_TERMINAL_REQUIRED_TASKS)
    observed_terminal_tasks: dict[str, str] = {}
    for item in terminal_evidence.task_evidence:
        if item.task_id in observed_terminal_tasks:
            reasons.append(
                f"terminal-duplicate-task:{item.task_id}"
            )
            continue
        observed_terminal_tasks[item.task_id] = item.accountability_id
    for task_id, accountability_id in P1_TERMINAL_REQUIRED_TASKS:
        observed = observed_terminal_tasks.get(task_id)
        if observed is None:
            reasons.append(f"terminal-missing-task:{task_id}")
        elif observed != accountability_id:
            reasons.append(
                f"terminal-accountability-mismatch:{task_id}"
            )
    for task_id in sorted(
        set(observed_terminal_tasks) - set(expected_terminal_tasks)
    ):
        reasons.append(f"terminal-unknown-task:{task_id}")

    if isinstance(receipts, (str, bytes)):
        raise TypeError(
            "receipts must contain FailureJourneyReceipt"
        )
    by_family: dict[FailureJourneyFamily, FailureJourneyReceipt] = {}
    verifier_ids: set[str] = set()
    for receipt in receipts:
        if not isinstance(receipt, FailureJourneyReceipt):
            raise TypeError(
                "receipts must contain FailureJourneyReceipt"
            )
        if receipt.family in by_family:
            reasons.append(
                f"duplicate-journey:{receipt.family.value}"
            )
            continue
        by_family[receipt.family] = receipt
        if receipt.verifier_id in verifier_ids:
            reasons.append(
                f"duplicate-verifier:{receipt.verifier_id}"
            )
        verifier_ids.add(receipt.verifier_id)

    required = set(P1_REQUIRED_FAILURE_JOURNEYS)
    missing = sorted(
        required - set(by_family),
        key=lambda item: item.value,
    )
    unknown = sorted(
        set(by_family) - required,
        key=lambda item: item.value,
    )
    reasons.extend(
        f"missing-journey:{item.value}" for item in missing
    )
    reasons.extend(
        f"unknown-journey:{item.value}" for item in unknown
    )

    evidence: list[FailureJourneyEvidence] = []
    for family in P1_REQUIRED_FAILURE_JOURNEYS:
        receipt = by_family.get(family)
        if receipt is None:
            continue
        prefix = family.value
        if receipt.repository != repository:
            reasons.append(f"{prefix}:repository-mismatch")
        if receipt.commit_sha != head:
            reasons.append(f"{prefix}:exact-head-mismatch")
        if not receipt.passed:
            reasons.append(f"{prefix}:journey-failed")
        if not receipt.independent:
            reasons.append(f"{prefix}:not-independent")
        if receipt.production_mutation_count != 0:
            reasons.append(f"{prefix}:production-mutated")
        if (
            family in P1_RECOVERY_REQUIRED_JOURNEYS
            and not receipt.recovered
        ):
            reasons.append(f"{prefix}:recovery-not-verified")

        required_assertions = set(
            P1_FAILURE_JOURNEY_ASSERTIONS[family]
        )
        missing_assertions = sorted(
            required_assertions - set(receipt.assertions)
        )
        reasons.extend(
            f"{prefix}:missing-assertion:{item}"
            for item in missing_assertions
        )
        evidence.append(
            FailureJourneyEvidence(
                family=family,
                receipt_digest=receipt.receipt_digest,
                verifier_digest=receipt.verifier_digest,
                test_manifest_digest=receipt.test_manifest_digest,
            )
        )

    normalized = tuple(sorted(set(reasons)))
    return P1FailureJourneyDecision(
        accepted=not normalized,
        reasons=normalized,
        repository=repository,
        commit_sha=head,
        terminal_evidence_digest=terminal_evidence.decision_digest,
        journey_evidence=tuple(evidence),
    )


__all__ = [
    "P1_FAILURE_JOURNEY_ACCOUNTABILITY_ID",
    "P1_FAILURE_JOURNEY_ASSERTIONS",
    "P1_FAILURE_JOURNEY_SCHEMA_VERSION",
    "P1_FAILURE_JOURNEY_TASK_ID",
    "P1_RECOVERY_REQUIRED_JOURNEYS",
    "P1_REQUIRED_FAILURE_JOURNEYS",
    "FailureJourneyEvidence",
    "FailureJourneyFamily",
    "FailureJourneyReceipt",
    "P1FailureJourneyDecision",
    "P1FailureJourneyError",
    "qualify_p1_failure_journeys",
]
