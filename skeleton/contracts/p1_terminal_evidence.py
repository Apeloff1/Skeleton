"""Terminal P1 exact-head evidence aggregation.

P1-PROM-01 is evidence-only. It joins exact-head PromotionEvidenceReceipt
objects from the terminal dependencies and a non-mutating maturity
reconciliation report. The aggregate can be structurally valid while still
reporting explicit maturity blockers. It never signs or applies promotion.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.promotion_evidence import PromotionEvidenceReceipt


P1_TERMINAL_EVIDENCE_SCHEMA_VERSION = 1
P1_TERMINAL_EVIDENCE_TASK_ID = "P1-PROM-01"
P1_TERMINAL_EVIDENCE_ACCOUNTABILITY_ID = "ACC-P1-PROM-01"
P1_TERMINAL_REQUIRED_TASKS: tuple[tuple[str, str], ...] = (
    ("P1-EVID-06", "ACC-P1-EVID-06"),
    ("P1-PROD-04", "ACC-P1-PROD-04"),
    ("P1-PROD-05", "ACC-P1-PROD-05"),
    ("P1-LEARN-04", "ACC-P1-LEARN-04"),
    ("P1-LEARN-06", "ACC-P1-LEARN-06"),
    ("P1-REL-05", "ACC-P1-REL-05"),
    ("P1-REL-06", "ACC-P1-REL-06"),
    ("P1-DIST-06", "ACC-P1-DIST-06"),
    ("P1-INTEL-06", "ACC-P1-INTEL-06"),
    ("P1-AUTO-06", "ACC-P1-AUTO-06"),
)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class P1TerminalEvidenceError(ValueError):
    """Terminal evidence input is malformed."""


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
        raise P1TerminalEvidenceError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise P1TerminalEvidenceError(f"{field} must be normalized")
    return normalized


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise P1TerminalEvidenceError(f"{field} must be lowercase sha256")
    return text


def _git_sha(value: object, field: str) -> str:
    text = _text(value, field, maximum=40)
    if not _SHA_RE.fullmatch(text):
        raise P1TerminalEvidenceError(
            f"{field} must be lowercase 40-character git sha"
        )
    return text


@dataclass(frozen=True, slots=True)
class TerminalTaskEvidence:
    task_id: str
    accountability_id: str
    subject_digest: str
    receipt_digest: str
    evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _text(self.task_id, "task_id"))
        object.__setattr__(
            self,
            "accountability_id",
            _text(self.accountability_id, "accountability_id"),
        )
        for field in ("subject_digest", "receipt_digest", "evidence_digest"):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )

    def payload(self) -> dict[str, str]:
        return {
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "subject_digest": self.subject_digest,
            "receipt_digest": self.receipt_digest,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True, slots=True)
class MaturityCoverageRecord:
    volume_key: str
    lane_id: str
    target_floor: str
    target_floor_eligible: bool
    current_claim_valid: bool
    current_claim_blockers: tuple[str, ...]
    promotion_candidate: str | None

    def __post_init__(self) -> None:
        for field in ("volume_key", "lane_id", "target_floor"):
            object.__setattr__(
                self,
                field,
                _text(getattr(self, field), field),
            )
        for field in ("target_floor_eligible", "current_claim_valid"):
            if not isinstance(getattr(self, field), bool):
                raise P1TerminalEvidenceError(f"{field} must be boolean")
        if not isinstance(self.current_claim_blockers, tuple) or any(
            not isinstance(item, str) or not item
            for item in self.current_claim_blockers
        ):
            raise P1TerminalEvidenceError(
                "current_claim_blockers must contain non-empty strings"
            )
        if self.promotion_candidate is not None:
            object.__setattr__(
                self,
                "promotion_candidate",
                _text(self.promotion_candidate, "promotion_candidate"),
            )

    def payload(self) -> dict[str, Any]:
        return {
            "volume_key": self.volume_key,
            "lane_id": self.lane_id,
            "target_floor": self.target_floor,
            "target_floor_eligible": self.target_floor_eligible,
            "current_claim_valid": self.current_claim_valid,
            "current_claim_blockers": list(self.current_claim_blockers),
            "promotion_candidate": self.promotion_candidate,
        }


@dataclass(frozen=True, slots=True)
class P1TerminalEvidenceDecision:
    accepted: bool
    promotion_ready: bool
    reasons: tuple[str, ...]
    promotion_blockers: tuple[str, ...]
    repository: str
    commit_sha: str
    task_evidence: tuple[TerminalTaskEvidence, ...]
    maturity_report_digest: str
    maturity_coverage_digest: str
    primary_volume_count: int
    blocking_volume_keys: tuple[str, ...]
    task_id: str = P1_TERMINAL_EVIDENCE_TASK_ID
    accountability_id: str = P1_TERMINAL_EVIDENCE_ACCOUNTABILITY_ID
    schema_version: int = P1_TERMINAL_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise P1TerminalEvidenceError("accepted must be boolean")
        if not isinstance(self.promotion_ready, bool):
            raise P1TerminalEvidenceError("promotion_ready must be boolean")
        for field in ("reasons", "promotion_blockers", "blocking_volume_keys"):
            value = getattr(self, field)
            if not isinstance(value, tuple) or any(
                not isinstance(item, str) or not item for item in value
            ):
                raise P1TerminalEvidenceError(
                    f"{field} must contain non-empty strings"
                )
        repository = _text(self.repository, "repository", maximum=200)
        if repository.count("/") != 1:
            raise P1TerminalEvidenceError("repository must be owner/name")
        object.__setattr__(
            self,
            "commit_sha",
            _git_sha(self.commit_sha, "commit_sha"),
        )
        if not isinstance(self.task_evidence, tuple) or any(
            not isinstance(item, TerminalTaskEvidence)
            for item in self.task_evidence
        ):
            raise P1TerminalEvidenceError(
                "task_evidence must contain TerminalTaskEvidence"
            )
        object.__setattr__(
            self,
            "maturity_report_digest",
            _sha256(
                self.maturity_report_digest,
                "maturity_report_digest",
            ),
        )
        object.__setattr__(
            self,
            "maturity_coverage_digest",
            _sha256(
                self.maturity_coverage_digest,
                "maturity_coverage_digest",
            ),
        )
        if (
            isinstance(self.primary_volume_count, bool)
            or not isinstance(self.primary_volume_count, int)
            or self.primary_volume_count < 1
        ):
            raise P1TerminalEvidenceError(
                "primary_volume_count must be positive integer"
            )
        if self.task_id != P1_TERMINAL_EVIDENCE_TASK_ID:
            raise P1TerminalEvidenceError("task_id drift")
        if self.accountability_id != P1_TERMINAL_EVIDENCE_ACCOUNTABILITY_ID:
            raise P1TerminalEvidenceError("accountability_id drift")
        if self.schema_version != P1_TERMINAL_EVIDENCE_SCHEMA_VERSION:
            raise P1TerminalEvidenceError(
                "unsupported terminal evidence schema"
            )
        if self.promotion_ready and (
            not self.accepted or self.promotion_blockers
        ):
            raise P1TerminalEvidenceError(
                "promotion_ready cannot coexist with rejection/blockers"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "promotion_ready": self.promotion_ready,
            "reasons": list(self.reasons),
            "promotion_blockers": list(self.promotion_blockers),
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "task_evidence": [
                item.payload() for item in self.task_evidence
            ],
            "maturity_report_digest": self.maturity_report_digest,
            "maturity_coverage_digest": self.maturity_coverage_digest,
            "primary_volume_count": self.primary_volume_count,
            "blocking_volume_keys": list(self.blocking_volume_keys),
            "promotion_authority": False,
            "signed_promotion": False,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:prom-01:terminal-evidence-bundle",
    ) -> EvidenceRef:
        if not self.accepted:
            raise P1TerminalEvidenceError(
                "rejected terminal bundle cannot become evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="p1_terminal_evidence_bundle",
        )


def _validate_maturity_report_digest(
    report: Mapping[str, Any],
) -> str:
    claimed = report.get("report_digest")
    if not isinstance(claimed, str) or not _SHA256_RE.fullmatch(claimed):
        raise P1TerminalEvidenceError(
            "maturity report_digest must be lowercase sha256"
        )
    payload = dict(report)
    payload.pop("report_digest", None)
    expected = _canonical_digest(payload)
    if expected != claimed:
        raise P1TerminalEvidenceError(
            "maturity report digest mismatch"
        )
    return claimed


def aggregate_p1_terminal_evidence(
    *,
    receipts: Iterable[PromotionEvidenceReceipt],
    maturity_report: Mapping[str, Any],
    expected_repository: str,
    expected_head: str,
    expected_primary_volumes: Iterable[str],
) -> P1TerminalEvidenceDecision:
    """Join exact-head terminal lane receipts and maturity coverage fail closed."""

    repository = _text(
        expected_repository,
        "expected_repository",
        maximum=200,
    )
    if repository.count("/") != 1:
        raise P1TerminalEvidenceError(
            "expected_repository must be owner/name"
        )
    head = _git_sha(expected_head, "expected_head")
    if not isinstance(maturity_report, Mapping):
        raise TypeError("maturity_report must be a mapping")

    expected_tasks = dict(P1_TERMINAL_REQUIRED_TASKS)
    by_task: dict[str, PromotionEvidenceReceipt] = {}
    reasons: list[str] = []

    if isinstance(receipts, (str, bytes)):
        raise TypeError(
            "receipts must contain PromotionEvidenceReceipt"
        )
    for receipt in receipts:
        if not isinstance(receipt, PromotionEvidenceReceipt):
            raise TypeError(
                "receipts must contain PromotionEvidenceReceipt"
            )
        if receipt.task_id in by_task:
            reasons.append(f"duplicate-task-receipt:{receipt.task_id}")
            continue
        by_task[receipt.task_id] = receipt

    missing = sorted(set(expected_tasks) - set(by_task))
    unknown = sorted(set(by_task) - set(expected_tasks))
    reasons.extend(f"missing-task-receipt:{item}" for item in missing)
    reasons.extend(f"unknown-task-receipt:{item}" for item in unknown)

    task_evidence: list[TerminalTaskEvidence] = []
    for task_id, accountability_id in P1_TERMINAL_REQUIRED_TASKS:
        receipt = by_task.get(task_id)
        if receipt is None:
            continue
        if receipt.accountability_id != accountability_id:
            reasons.append(f"accountability-mismatch:{task_id}")
        if receipt.repository != repository:
            reasons.append(f"repository-mismatch:{task_id}")
        if receipt.commit_sha != head:
            reasons.append(f"exact-head-mismatch:{task_id}")
        task_evidence.append(
            TerminalTaskEvidence(
                task_id=task_id,
                accountability_id=receipt.accountability_id,
                subject_digest=receipt.subject_digest,
                receipt_digest=receipt.receipt_digest,
                evidence_digest=receipt.evidence_digest,
            )
        )

    expected_volumes = tuple(
        sorted(
            {
                _text(value, "expected_primary_volumes", maximum=64)
                for value in expected_primary_volumes
            }
        )
    )
    if not expected_volumes:
        raise P1TerminalEvidenceError(
            "expected_primary_volumes must be non-empty"
        )

    maturity_report_digest = _validate_maturity_report_digest(
        maturity_report
    )
    if maturity_report.get("source_mutation_detected") is not False:
        reasons.append("maturity-source-mutation-detected")
    records = maturity_report.get("records")
    if not isinstance(records, list):
        raise P1TerminalEvidenceError(
            "maturity records must be a list"
        )

    coverage_by_key: dict[str, MaturityCoverageRecord] = {}
    for raw in records:
        if not isinstance(raw, Mapping):
            raise P1TerminalEvidenceError(
                "maturity records must be objects"
            )
        key = _text(raw.get("volume_key"), "volume_key", maximum=64)
        if key in coverage_by_key:
            reasons.append(f"duplicate-maturity-volume:{key}")
            continue
        blockers_raw = raw.get("current_claim_blockers")
        if not isinstance(blockers_raw, list) or any(
            not isinstance(item, str) or not item
            for item in blockers_raw
        ):
            raise P1TerminalEvidenceError(
                f"{key}: current_claim_blockers must be string list"
            )
        coverage_by_key[key] = MaturityCoverageRecord(
            volume_key=key,
            lane_id=_text(raw.get("lane_id"), "lane_id", maximum=64),
            target_floor=_text(
                raw.get("target_floor"),
                "target_floor",
                maximum=64,
            ),
            target_floor_eligible=raw.get("target_floor_eligible"),
            current_claim_valid=raw.get("current_claim_valid"),
            current_claim_blockers=tuple(blockers_raw),
            promotion_candidate=raw.get("promotion_candidate"),
        )

    missing_volumes = sorted(
        set(expected_volumes) - set(coverage_by_key)
    )
    unknown_volumes = sorted(
        set(coverage_by_key) - set(expected_volumes)
    )
    reasons.extend(
        f"missing-maturity-volume:{item}" for item in missing_volumes
    )
    reasons.extend(
        f"unknown-maturity-volume:{item}" for item in unknown_volumes
    )

    coverage = tuple(
        coverage_by_key[key]
        for key in sorted(coverage_by_key)
        if key in set(expected_volumes)
    )
    coverage_digest = _canonical_digest(
        [item.payload() for item in coverage]
    )

    promotion_blockers: list[str] = []
    blocking_keys: set[str] = set()
    for item in coverage:
        if not item.target_floor_eligible:
            promotion_blockers.append(
                f"target-floor-not-eligible:{item.volume_key}"
            )
            blocking_keys.add(item.volume_key)
        if not item.current_claim_valid:
            promotion_blockers.append(
                f"current-claim-invalid:{item.volume_key}"
            )
            blocking_keys.add(item.volume_key)
        for blocker in item.current_claim_blockers:
            promotion_blockers.append(
                f"maturity:{item.volume_key}:{blocker}"
            )
            blocking_keys.add(item.volume_key)

    normalized_reasons = tuple(sorted(set(reasons)))
    normalized_blockers = tuple(sorted(set(promotion_blockers)))
    accepted = not normalized_reasons
    promotion_ready = accepted and not normalized_blockers
    return P1TerminalEvidenceDecision(
        accepted=accepted,
        promotion_ready=promotion_ready,
        reasons=normalized_reasons,
        promotion_blockers=normalized_blockers,
        repository=repository,
        commit_sha=head,
        task_evidence=tuple(task_evidence),
        maturity_report_digest=maturity_report_digest,
        maturity_coverage_digest=coverage_digest,
        primary_volume_count=len(expected_volumes),
        blocking_volume_keys=tuple(sorted(blocking_keys)),
    )


__all__ = [
    "P1_TERMINAL_EVIDENCE_ACCOUNTABILITY_ID",
    "P1_TERMINAL_EVIDENCE_SCHEMA_VERSION",
    "P1_TERMINAL_EVIDENCE_TASK_ID",
    "P1_TERMINAL_REQUIRED_TASKS",
    "MaturityCoverageRecord",
    "P1TerminalEvidenceDecision",
    "P1TerminalEvidenceError",
    "TerminalTaskEvidence",
    "aggregate_p1_terminal_evidence",
]
