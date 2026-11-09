"""Fail-closed evidence receipts for P3-T2 implementation candidates.

The continuation frontier is planning authority only.  These receipts bind
implementation evidence to one exact Git revision, one execution subject and
an independent verifier.  They intentionally carry no promotion authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Iterable, Mapping, Sequence


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_VOLUME = re.compile(r"^VOL-[0-9]{3}$")


class P3T2EvidenceError(ValueError):
    """Raised when continuation evidence is incomplete, stitched or ambiguous."""


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _nonempty(value: str, *, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise P3T2EvidenceError(f"{field} must be non-empty")
    return text


def _require_digest(value: str, *, field: str) -> str:
    text = str(value).strip().lower()
    if _SHA256.fullmatch(text) is None:
        raise P3T2EvidenceError(f"{field} must be a lowercase sha256 digest")
    return text


def _require_revision(value: str) -> str:
    text = str(value).strip().lower()
    if _GIT_SHA.fullmatch(text) is None:
        raise P3T2EvidenceError("source_revision must be a 40-character lowercase Git SHA")
    return text


def _unique_nonempty(values: Iterable[str], *, field: str) -> tuple[str, ...]:
    items = tuple(_nonempty(value, field=field) for value in values)
    if len(items) != len(set(items)):
        raise P3T2EvidenceError(f"{field} must be unique")
    return items


@dataclass(frozen=True, slots=True)
class P3T2LaneProof:
    """One independently witnessed volume proof."""

    task_id: str
    lane_id: str
    volume_ref: str
    execution_subject: str
    source_revision: str
    producer_id: str
    verifier_id: str
    evidence_refs: tuple[str, ...]
    observation_digest: str
    passed: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _nonempty(self.task_id, field="task_id"))
        object.__setattr__(self, "lane_id", _nonempty(self.lane_id, field="lane_id"))
        volume = _nonempty(self.volume_ref, field="volume_ref")
        if _VOLUME.fullmatch(volume) is None:
            raise P3T2EvidenceError("volume_ref must use VOL-NNN identity")
        object.__setattr__(self, "volume_ref", volume)
        object.__setattr__(
            self,
            "execution_subject",
            _nonempty(self.execution_subject, field="execution_subject"),
        )
        object.__setattr__(self, "source_revision", _require_revision(self.source_revision))
        object.__setattr__(
            self,
            "producer_id",
            _nonempty(self.producer_id, field="producer_id"),
        )
        object.__setattr__(
            self,
            "verifier_id",
            _nonempty(self.verifier_id, field="verifier_id"),
        )
        if self.producer_id == self.verifier_id:
            raise P3T2EvidenceError("producer and verifier must be independent")
        refs = _unique_nonempty(self.evidence_refs, field="evidence_refs")
        if not refs:
            raise P3T2EvidenceError("evidence_refs must not be empty")
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(
            self,
            "observation_digest",
            _require_digest(self.observation_digest, field="observation_digest"),
        )
        if self.passed is not True:
            raise P3T2EvidenceError("failed proof cannot satisfy candidate evidence")

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "lane_id": self.lane_id,
            "volume_ref": self.volume_ref,
            "execution_subject": self.execution_subject,
            "source_revision": self.source_revision,
            "producer_id": self.producer_id,
            "verifier_id": self.verifier_id,
            "evidence_refs": list(self.evidence_refs),
            "observation_digest": self.observation_digest,
            "passed": self.passed,
            "promotion_authority": False,
        }


@dataclass(frozen=True, slots=True)
class P3T2LaneReceipt:
    """Exact-volume receipt for one P3-T2 task owner."""

    task_id: str
    lane_id: str
    expected_volume_refs: tuple[str, ...]
    proofs: tuple[P3T2LaneProof, ...]
    dependency_receipt_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        task = _nonempty(self.task_id, field="task_id")
        lane = _nonempty(self.lane_id, field="lane_id")
        object.__setattr__(self, "task_id", task)
        object.__setattr__(self, "lane_id", lane)
        expected = _unique_nonempty(
            self.expected_volume_refs,
            field="expected_volume_refs",
        )
        if not expected:
            raise P3T2EvidenceError("expected_volume_refs must not be empty")
        if any(_VOLUME.fullmatch(value) is None for value in expected):
            raise P3T2EvidenceError("expected_volume_refs must use VOL-NNN identity")
        object.__setattr__(self, "expected_volume_refs", expected)

        proofs = tuple(self.proofs)
        if not proofs:
            raise P3T2EvidenceError("lane receipt requires proofs")
        object.__setattr__(self, "proofs", proofs)

        proof_refs = tuple(proof.volume_ref for proof in proofs)
        if len(proof_refs) != len(set(proof_refs)):
            raise P3T2EvidenceError("duplicate volume proof")
        if set(proof_refs) != set(expected):
            missing = sorted(set(expected) - set(proof_refs))
            extra = sorted(set(proof_refs) - set(expected))
            raise P3T2EvidenceError(
                f"proof coverage mismatch missing={missing} extra={extra}"
            )
        if any(proof.task_id != task or proof.lane_id != lane for proof in proofs):
            raise P3T2EvidenceError("proof task/lane identity mismatch")

        revisions = {proof.source_revision for proof in proofs}
        if len(revisions) != 1:
            raise P3T2EvidenceError("lane proofs must bind one exact source revision")
        subjects = {proof.execution_subject for proof in proofs}
        if len(subjects) != 1:
            raise P3T2EvidenceError("lane proofs must bind one execution subject")

        dependencies = tuple(
            _require_digest(value, field="dependency_receipt_digest")
            for value in self.dependency_receipt_digests
        )
        if len(dependencies) != len(set(dependencies)):
            raise P3T2EvidenceError("dependency receipt digests must be unique")
        object.__setattr__(self, "dependency_receipt_digests", dependencies)

    @property
    def source_revision(self) -> str:
        return self.proofs[0].source_revision

    @property
    def execution_subject(self) -> str:
        return self.proofs[0].execution_subject

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        ordered = sorted(self.proofs, key=lambda proof: proof.volume_ref)
        return {
            "task_id": self.task_id,
            "lane_id": self.lane_id,
            "expected_volume_refs": list(self.expected_volume_refs),
            "proofs": [proof.as_dict() for proof in ordered],
            "dependency_receipt_digests": list(self.dependency_receipt_digests),
            "source_revision": self.source_revision,
            "execution_subject": self.execution_subject,
            "promotion_authority": False,
        }


@dataclass(frozen=True, slots=True)
class P3T2ContinuationReceipt:
    """Dependency-ordered receipt set for multiple continuation lanes."""

    receipts: tuple[P3T2LaneReceipt, ...]
    required_dependencies: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        receipts = tuple(self.receipts)
        if not receipts:
            raise P3T2EvidenceError("continuation receipt requires at least one lane")
        task_ids = tuple(receipt.task_id for receipt in receipts)
        if len(task_ids) != len(set(task_ids)):
            raise P3T2EvidenceError("duplicate task receipt")
        object.__setattr__(self, "receipts", receipts)

        revisions = {receipt.source_revision for receipt in receipts}
        if len(revisions) != 1:
            raise P3T2EvidenceError("continuation receipts must share one exact source revision")
        subjects = {receipt.execution_subject for receipt in receipts}
        if len(subjects) != 1:
            raise P3T2EvidenceError("continuation receipts must share one execution subject")

        by_task = {receipt.task_id: receipt for receipt in receipts}
        normalized: dict[str, tuple[str, ...]] = {}
        for task_id, dependencies in self.required_dependencies.items():
            task = _nonempty(task_id, field="dependency task_id")
            deps = _unique_nonempty(dependencies, field=f"{task}.dependencies")
            normalized[task] = deps
            if task not in by_task:
                continue
            missing = [dependency for dependency in deps if dependency not in by_task]
            if missing:
                raise P3T2EvidenceError(
                    f"{task} missing dependency receipts: {sorted(missing)}"
                )
            expected_digests = tuple(by_task[dependency].digest for dependency in deps)
            actual = by_task[task].dependency_receipt_digests
            if actual != expected_digests:
                raise P3T2EvidenceError(
                    f"{task} dependency digest chain mismatch"
                )
        object.__setattr__(self, "required_dependencies", normalized)

    @property
    def source_revision(self) -> str:
        return self.receipts[0].source_revision

    @property
    def execution_subject(self) -> str:
        return self.receipts[0].execution_subject

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        ordered = sorted(self.receipts, key=lambda receipt: receipt.task_id)
        return {
            "receipts": [receipt.as_dict() for receipt in ordered],
            "required_dependencies": {
                key: list(value)
                for key, value in sorted(self.required_dependencies.items())
            },
            "source_revision": self.source_revision,
            "execution_subject": self.execution_subject,
            "promotion_authority": False,
        }
