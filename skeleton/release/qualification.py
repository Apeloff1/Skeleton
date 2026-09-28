"""P1 release qualification bundle.

This module composes the existing release-evidence engine with P1 dependency
evidence and executable lifecycle receipts. It does not build, install, publish,
promote, or mutate release state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.reproducibility import (
    ReplayDisposition,
    ReproducibilityBundle,
    ReproducibilityEvaluation,
)
from skeleton.release.evidence import (
    GateResult,
    ReleaseEvidence,
    evidence_digest,
)


RELEASE_QUALIFICATION_SCHEMA_VERSION = 1
RELEASE_QUALIFICATION_TASK_ID = "P1-REL-01"
RELEASE_QUALIFICATION_ACCOUNTABILITY_ID = "ACC-P1-REL-01"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")

_REQUIRED_DEPENDENCY_PREFIXES = {
    "tenant_storage_boundary": "p1:prod-05:tenant-storage:",
    "candidate_qualification": "p1:learn-03:candidate:",
    "safe_autonomy_qualification": "p1:auto-06:safe-autonomy-bundle",
}


class ReleaseQualificationError(ValueError):
    """P1 release qualification input is malformed or incomplete."""


class ReleaseLifecycleMode(str, Enum):
    CLEAN_MACHINE = "clean_machine"
    ROLLBACK = "rollback"
    RESTORE_DRILL = "restore_drill"


def _token(value: object, field: str, *, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not _TOKEN_RE.fullmatch(value)
    ):
        raise ReleaseQualificationError(
            f"{field} must be a canonical token"
        )
    return value


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseQualificationError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise ReleaseQualificationError(f"{field} must be normalized")
    return normalized


def _sha40(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA40_RE.fullmatch(value):
        raise ReleaseQualificationError(
            f"{field} must be lowercase 40-character git SHA"
        )
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ReleaseQualificationError(
            f"{field} must be lowercase sha256"
        )
    return value


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReleaseQualificationError(
            "release qualification payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise ReleaseQualificationError(
            "evidence_refs must contain EvidenceRef values"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise ReleaseQualificationError(
                "evidence_refs must contain EvidenceRef values"
            )
        _text(item.source, "evidence.source", maximum=2048)
        _sha256(item.digest, "evidence.digest")
        _token(item.category, "evidence.category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key:
        raise ReleaseQualificationError("evidence_refs must be non-empty")
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True)
class ReleaseLifecycleReceipt:
    mode: ReleaseLifecycleMode
    source_commit: str
    release_evidence_digest: str
    installer_metadata_digest: str
    configuration_digest: str
    environment_digest: str
    verifier_id: str
    verifier_digest: str
    test_manifest_digest: str
    evidence_refs: tuple[EvidenceRef, ...]
    passed: bool = True
    independent: bool = True
    production_mutation_count: int = 0

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "mode",
                ReleaseLifecycleMode(self.mode),
            )
        except ValueError as exc:
            raise ReleaseQualificationError(
                "invalid lifecycle mode"
            ) from exc
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        for field in (
            "release_evidence_digest",
            "installer_metadata_digest",
            "configuration_digest",
            "environment_digest",
            "verifier_digest",
            "test_manifest_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "verifier_id",
            _token(self.verifier_id, "verifier_id"),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence(self.evidence_refs),
        )
        if self.passed is not True:
            raise ReleaseQualificationError(
                "lifecycle receipt must be passing before qualification"
            )
        if self.independent is not True:
            raise ReleaseQualificationError(
                "lifecycle receipt must be independently verified"
            )
        if (
            isinstance(self.production_mutation_count, bool)
            or not isinstance(self.production_mutation_count, int)
            or self.production_mutation_count != 0
        ):
            raise ReleaseQualificationError(
                "lifecycle qualification cannot mutate production"
            )
        if self.mode.value not in {
            item.category for item in self.evidence_refs
        }:
            raise ReleaseQualificationError(
                "lifecycle evidence must include its exact mode category"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "source_commit": self.source_commit,
            "release_evidence_digest": self.release_evidence_digest,
            "installer_metadata_digest": self.installer_metadata_digest,
            "configuration_digest": self.configuration_digest,
            "environment_digest": self.environment_digest,
            "verifier_id": self.verifier_id,
            "verifier_digest": self.verifier_digest,
            "test_manifest_digest": self.test_manifest_digest,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
            "passed": self.passed,
            "independent": self.independent,
            "production_mutation_count": self.production_mutation_count,
        }

    @property
    def receipt_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ReleaseQualificationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    source_commit: str
    release_evidence_digest: str
    reproducibility_bundle_digest: str
    reproducibility_evaluation_digest: str
    dependency_evidence_digest: str
    sbom_digest: str
    provenance_digest: str
    installer_metadata_digest: str
    configuration_digest: str
    lifecycle_receipt_digests: tuple[str, ...]
    task_id: str = RELEASE_QUALIFICATION_TASK_ID
    accountability_id: str = RELEASE_QUALIFICATION_ACCOUNTABILITY_ID
    schema_version: int = RELEASE_QUALIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise ReleaseQualificationError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise ReleaseQualificationError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        for field in (
            "release_evidence_digest",
            "reproducibility_bundle_digest",
            "reproducibility_evaluation_digest",
            "dependency_evidence_digest",
            "sbom_digest",
            "provenance_digest",
            "installer_metadata_digest",
            "configuration_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if not isinstance(self.lifecycle_receipt_digests, tuple):
            raise ReleaseQualificationError(
                "lifecycle_receipt_digests must be tuple"
            )
        object.__setattr__(
            self,
            "lifecycle_receipt_digests",
            tuple(
                sorted(
                    {
                        _sha256(item, "lifecycle_receipt_digests")
                        for item in self.lifecycle_receipt_digests
                    }
                )
            ),
        )
        if self.task_id != RELEASE_QUALIFICATION_TASK_ID:
            raise ReleaseQualificationError("task_id drift")
        if (
            self.accountability_id
            != RELEASE_QUALIFICATION_ACCOUNTABILITY_ID
        ):
            raise ReleaseQualificationError("accountability_id drift")
        if self.schema_version != RELEASE_QUALIFICATION_SCHEMA_VERSION:
            raise ReleaseQualificationError(
                "unsupported release qualification schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "source_commit": self.source_commit,
            "release_evidence_digest": self.release_evidence_digest,
            "reproducibility_bundle_digest": (
                self.reproducibility_bundle_digest
            ),
            "reproducibility_evaluation_digest": (
                self.reproducibility_evaluation_digest
            ),
            "dependency_evidence_digest": self.dependency_evidence_digest,
            "sbom_digest": self.sbom_digest,
            "provenance_digest": self.provenance_digest,
            "installer_metadata_digest": self.installer_metadata_digest,
            "configuration_digest": self.configuration_digest,
            "lifecycle_receipt_digests": list(
                self.lifecycle_receipt_digests
            ),
            "production_authority": False,
            "publishing_authority": False,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise ReleaseQualificationError(
                "rejected release cannot become promotion evidence"
            )
        return EvidenceRef(
            source=f"p1:rel-01:release:{self.source_commit}",
            digest=self.decision_digest,
            category="release_qualification",
        )


def _dependency_digest(values: tuple[EvidenceRef, ...]) -> str:
    return _canonical_digest(
        [
            {
                "source": item.source,
                "digest": item.digest,
                "category": item.category,
            }
            for item in values
        ]
    )


def qualify_release_candidate(
    *,
    source_commit: str,
    release_evidence: ReleaseEvidence,
    release_gate: GateResult,
    reproducibility: ReproducibilityBundle,
    reproducibility_evaluation: ReproducibilityEvaluation,
    dependency_evidence: Iterable[EvidenceRef],
    lifecycle_receipts: Iterable[ReleaseLifecycleReceipt],
    installer_metadata_digest: str,
    configuration_digest: str,
) -> ReleaseQualificationDecision:
    if not isinstance(release_evidence, ReleaseEvidence):
        raise TypeError("release_evidence must be ReleaseEvidence")
    if not isinstance(release_gate, GateResult):
        raise TypeError("release_gate must be GateResult")
    if not isinstance(reproducibility, ReproducibilityBundle):
        raise TypeError(
            "reproducibility must be ReproducibilityBundle"
        )
    if not isinstance(
        reproducibility_evaluation,
        ReproducibilityEvaluation,
    ):
        raise TypeError(
            "reproducibility_evaluation must be ReproducibilityEvaluation"
        )
    commit = _sha40(source_commit, "source_commit")
    installer_digest = _sha256(
        installer_metadata_digest,
        "installer_metadata_digest",
    )
    config_digest = _sha256(
        configuration_digest,
        "configuration_digest",
    )
    deps = _evidence(dependency_evidence)
    receipts = tuple(lifecycle_receipts)
    if any(
        not isinstance(item, ReleaseLifecycleReceipt)
        for item in receipts
    ):
        raise TypeError(
            "lifecycle_receipts must contain ReleaseLifecycleReceipt"
        )

    reasons: list[str] = []
    if not release_gate.release_ready:
        reasons.append("release-evidence-not-ready")
    release_digest = _sha256(
        release_gate.evidence_digest,
        "release_gate.evidence_digest",
    )
    actual_release_digest = _sha256(
        evidence_digest(release_evidence),
        "release_evidence.digest",
    )
    if actual_release_digest != release_digest:
        reasons.append("release-evidence-digest-mismatch")
    if release_evidence.source_commit != commit:
        reasons.append("release-evidence-commit-mismatch")
    if release_evidence.sbom is None:
        reasons.append("release-sbom-missing")
        sbom_digest = _canonical_digest({"missing": "sbom"})
    else:
        sbom_digest = _sha256(
            release_evidence.sbom.sha256,
            "release_evidence.sbom.sha256",
        )
    if release_evidence.provenance is None:
        reasons.append("release-provenance-missing")
        provenance_digest = _canonical_digest(
            {"missing": "provenance"}
        )
    else:
        provenance_digest = _sha256(
            release_evidence.provenance.digest,
            "release_evidence.provenance.digest",
        )

    if reproducibility.task_id != "P1-EVID-05":
        reasons.append("reproducibility-task-identity-mismatch")
    if reproducibility.accountability_id != "ACC-P1-EVID-05":
        reasons.append("reproducibility-accountability-identity-mismatch")
    if reproducibility.commit_sha != commit:
        reasons.append("reproducibility-commit-mismatch")

    replay = reproducibility_evaluation
    if replay.bundle_digest != reproducibility.bundle_digest:
        reasons.append("reproducibility-evaluation-bundle-mismatch")
    if replay.disposition is not ReplayDisposition.REPRODUCED:
        reasons.append("reproducibility-replay-not-reproduced")
    if replay.compatible is not True:
        reasons.append("reproducibility-replay-incompatible")
    if replay.reproduced is not True:
        reasons.append("reproducibility-replay-failed")
    if replay.incompatibilities:
        reasons.append("reproducibility-replay-has-incompatibilities")
    if (
        replay.replay_subject_digest
        != reproducibility.expected_subject_digest
    ):
        reasons.append("reproducibility-replay-subject-mismatch")
    if (
        replay.replay_evidence_digest
        != reproducibility.expected_evidence_digest
    ):
        reasons.append("reproducibility-replay-evidence-mismatch")

    release_inputs = [
        item
        for item in reproducibility.inputs
        if item.category == "release_evidence"
    ]
    if len(release_inputs) != 1:
        reasons.append("reproducibility-release-evidence-cardinality")
    elif release_inputs[0].digest != release_digest:
        reasons.append("reproducibility-release-evidence-mismatch")

    by_category: dict[str, list[EvidenceRef]] = {}
    for item in deps:
        by_category.setdefault(item.category, []).append(item)
    for category, prefix in _REQUIRED_DEPENDENCY_PREFIXES.items():
        rows = by_category.get(category, [])
        if len(rows) != 1:
            reasons.append(
                f"dependency-evidence-cardinality:{category}"
            )
            continue
        if not rows[0].source.startswith(prefix):
            reasons.append(
                f"dependency-evidence-source-mismatch:{category}"
            )

    mode_rows: dict[ReleaseLifecycleMode, list[ReleaseLifecycleReceipt]] = {
        mode: [] for mode in ReleaseLifecycleMode
    }
    for receipt in receipts:
        mode_rows[receipt.mode].append(receipt)
        if receipt.source_commit != commit:
            reasons.append(
                f"lifecycle-commit-mismatch:{receipt.mode.value}"
            )
        if receipt.release_evidence_digest != release_digest:
            reasons.append(
                f"lifecycle-release-digest-mismatch:{receipt.mode.value}"
            )
        if receipt.installer_metadata_digest != installer_digest:
            reasons.append(
                f"lifecycle-installer-digest-mismatch:{receipt.mode.value}"
            )
        if receipt.configuration_digest != config_digest:
            reasons.append(
                f"lifecycle-config-digest-mismatch:{receipt.mode.value}"
            )
        if (
            receipt.environment_digest
            != reproducibility.environment_digest
        ):
            reasons.append(
                f"lifecycle-environment-digest-mismatch:"
                f"{receipt.mode.value}"
            )
    for mode, rows in mode_rows.items():
        if len(rows) != 1:
            reasons.append(
                f"lifecycle-receipt-cardinality:{mode.value}"
            )

    normalized = tuple(sorted(set(reasons)))
    return ReleaseQualificationDecision(
        accepted=not normalized,
        reasons=normalized,
        source_commit=commit,
        release_evidence_digest=release_digest,
        reproducibility_bundle_digest=reproducibility.bundle_digest,
        reproducibility_evaluation_digest=replay.evaluation_digest,
        dependency_evidence_digest=_dependency_digest(deps),
        sbom_digest=sbom_digest,
        provenance_digest=provenance_digest,
        installer_metadata_digest=installer_digest,
        configuration_digest=config_digest,
        lifecycle_receipt_digests=tuple(
            item.receipt_digest for item in receipts
        ),
    )


__all__ = [
    "RELEASE_QUALIFICATION_ACCOUNTABILITY_ID",
    "RELEASE_QUALIFICATION_SCHEMA_VERSION",
    "RELEASE_QUALIFICATION_TASK_ID",
    "ReleaseLifecycleMode",
    "ReleaseLifecycleReceipt",
    "ReleaseQualificationDecision",
    "ReleaseQualificationError",
    "qualify_release_candidate",
]
