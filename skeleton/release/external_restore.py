"""Post-restore external reality qualification for P1 AC-08."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable


class ExternalRestoreError(ValueError):
    """Restored local state disagrees with external reality."""


class ExternalReferenceKind(str, Enum):
    CREDENTIAL = "credential"
    EXTERNAL_RESOURCE = "external_resource"
    TOMBSTONE = "tombstone"


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ExternalRestoreError("external restore payload must be canonical JSON") from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ExternalRestoreReference:
    reference_id: str
    kind: ExternalReferenceKind
    expected_external_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.reference_id, str) or not self.reference_id.strip():
            raise ExternalRestoreError("reference_id must be non-empty")
        object.__setattr__(self, "kind", ExternalReferenceKind(self.kind))
        if len(self.expected_external_digest) != 64:
            raise ExternalRestoreError("expected_external_digest must be SHA-256 hex")
        try:
            bytes.fromhex(self.expected_external_digest)
        except ValueError as exc:
            raise ExternalRestoreError(
                "expected_external_digest must be hexadecimal"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExternalRestoreReceipt:
    reference_id: str
    observed_external_digest: str
    reconciled: bool
    credential_revalidated: bool = False
    tombstone_propagated: bool = False
    resurrected: bool = False

    def __post_init__(self) -> None:
        if len(self.observed_external_digest) != 64:
            raise ExternalRestoreError("observed_external_digest must be SHA-256 hex")
        try:
            bytes.fromhex(self.observed_external_digest)
        except ValueError as exc:
            raise ExternalRestoreError(
                "observed_external_digest must be hexadecimal"
            ) from exc
        for field in (
            "reconciled",
            "credential_revalidated",
            "tombstone_propagated",
            "resurrected",
        ):
            if not isinstance(getattr(self, field), bool):
                raise ExternalRestoreError(f"{field} must be boolean")


@dataclass(frozen=True, slots=True)
class ExternalRestoreDecision:
    accepted: bool
    reasons: tuple[str, ...]
    receipt_digests: tuple[str, ...]

    @property
    def decision_digest(self) -> str:
        return _digest(
            {
                "accepted": self.accepted,
                "reasons": list(self.reasons),
                "receipt_digests": list(self.receipt_digests),
            }
        )


def qualify_external_restore(
    *,
    references: Iterable[ExternalRestoreReference],
    receipts: Iterable[ExternalRestoreReceipt],
) -> ExternalRestoreDecision:
    """Require post-restore proof against external authority for every reference."""

    refs = tuple(references)
    rows = tuple(receipts)
    if not refs:
        raise ExternalRestoreError("references must be non-empty")
    if any(not isinstance(item, ExternalRestoreReference) for item in refs):
        raise TypeError("references must contain ExternalRestoreReference")
    if any(not isinstance(item, ExternalRestoreReceipt) for item in rows):
        raise TypeError("receipts must contain ExternalRestoreReceipt")

    by_id: dict[str, list[ExternalRestoreReceipt]] = {
        item.reference_id: [] for item in refs
    }
    if len(by_id) != len(refs):
        raise ExternalRestoreError("reference IDs must be unique")

    reasons: list[str] = []
    for row in rows:
        if row.reference_id not in by_id:
            reasons.append(f"unexpected-receipt:{row.reference_id}")
            continue
        by_id[row.reference_id].append(row)

    receipt_digests: list[str] = []
    for ref in refs:
        matches = by_id[ref.reference_id]
        if len(matches) != 1:
            reasons.append(f"{ref.reference_id}:receipt-cardinality")
            continue
        row = matches[0]
        receipt_digests.append(
            _digest(
                {
                    "reference_id": row.reference_id,
                    "observed_external_digest": row.observed_external_digest,
                    "reconciled": row.reconciled,
                    "credential_revalidated": row.credential_revalidated,
                    "tombstone_propagated": row.tombstone_propagated,
                    "resurrected": row.resurrected,
                }
            )
        )
        if not row.reconciled:
            reasons.append(f"{ref.reference_id}:external-not-reconciled")
        if row.observed_external_digest != ref.expected_external_digest:
            reasons.append(f"{ref.reference_id}:external-digest-mismatch")

        if ref.kind is ExternalReferenceKind.CREDENTIAL:
            if not row.credential_revalidated:
                reasons.append(f"{ref.reference_id}:credential-not-revalidated")
            if row.tombstone_propagated:
                reasons.append(f"{ref.reference_id}:unexpected-tombstone")
        elif ref.kind is ExternalReferenceKind.EXTERNAL_RESOURCE:
            if row.credential_revalidated:
                reasons.append(f"{ref.reference_id}:unexpected-credential-proof")
            if row.tombstone_propagated:
                reasons.append(f"{ref.reference_id}:unexpected-tombstone")
        else:
            if not row.tombstone_propagated:
                reasons.append(f"{ref.reference_id}:tombstone-not-propagated")
            if row.resurrected:
                reasons.append(f"{ref.reference_id}:tombstone-resurrected")

    normalized = tuple(sorted(set(reasons)))
    return ExternalRestoreDecision(
        accepted=not normalized,
        reasons=normalized,
        receipt_digests=tuple(sorted(receipt_digests)),
    )


__all__ = [
    "ExternalReferenceKind",
    "ExternalRestoreDecision",
    "ExternalRestoreError",
    "ExternalRestoreReceipt",
    "ExternalRestoreReference",
    "qualify_external_restore",
]
