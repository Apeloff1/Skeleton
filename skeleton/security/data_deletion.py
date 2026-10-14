"""Evidence-only deletion contracts for the AI runtime.

This module records deletion intent, tombstones, and coverage evidence. It does
not delete data, mutate storage, erase backups, or authorize destructive work.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable


class DataDeletionError(ValueError):
    """A deletion scope, tombstone, or evidence invariant failed."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise DataDeletionError(f"{name} must be non-empty normalized text")
    if len(value) > 256:
        raise DataDeletionError(f"{name} exceeds maximum length")
    return value


def _tokens(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise DataDeletionError(f"{name} must be a collection")
    result = tuple(sorted({_token(name, value) for value in values}))
    if not result:
        raise DataDeletionError(f"{name} must be non-empty")
    return result


def _pairs(
    name: str,
    values: Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    if isinstance(values, (str, bytes)):
        raise DataDeletionError(f"{name} must be a collection")
    result: set[tuple[str, str]] = set()
    for value in values:
        if (
            not isinstance(value, tuple)
            or len(value) != 2
        ):
            raise DataDeletionError(f"{name} entries must be (target, surface) pairs")
        result.add(
            (
                _token("target_ref", value[0]),
                _token("surface", value[1]),
            )
        )
    return tuple(sorted(result))


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DataDeletionError(f"{name} must be a non-negative integer")
    return value


def _sha256(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise DataDeletionError(f"{name} must be a lowercase sha256 digest")
    return value


def _digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DataDeletionError("deletion evidence must be canonical JSON") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DeletionRequest:
    """Declared target/surface scope for a deletion operation."""

    request_id: str
    target_refs: tuple[str, ...]
    required_surfaces: tuple[str, ...]
    reason_code: str
    requested_at_ns: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _token("request_id", self.request_id))
        object.__setattr__(
            self,
            "target_refs",
            _tokens("target_ref", self.target_refs),
        )
        object.__setattr__(
            self,
            "required_surfaces",
            _tokens("required_surface", self.required_surfaces),
        )
        object.__setattr__(self, "reason_code", _token("reason_code", self.reason_code))
        object.__setattr__(
            self,
            "requested_at_ns",
            _non_negative_int("requested_at_ns", self.requested_at_ns),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "request_id": self.request_id,
                "target_refs": list(self.target_refs),
                "required_surfaces": list(self.required_surfaces),
                "reason_code": self.reason_code,
                "requested_at_ns": self.requested_at_ns,
            }
        )


@dataclass(frozen=True, slots=True)
class DeletionTombstone:
    """Evidence that one target/surface pair was deleted and fenced."""

    tombstone_id: str
    request_id: str
    target_ref: str
    surface: str
    source_digest: str
    deleted_at_ns: int
    resurrection_blocked: bool = True

    def __post_init__(self) -> None:
        for name in ("tombstone_id", "request_id", "target_ref", "surface"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        object.__setattr__(
            self,
            "source_digest",
            _sha256("source_digest", self.source_digest),
        )
        object.__setattr__(
            self,
            "deleted_at_ns",
            _non_negative_int("deleted_at_ns", self.deleted_at_ns),
        )
        if self.resurrection_blocked is not True:
            raise DataDeletionError(
                "deletion tombstone must block resurrection"
            )

    @property
    def pair(self) -> tuple[str, str]:
        return (self.target_ref, self.surface)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "tombstone_id": self.tombstone_id,
                "request_id": self.request_id,
                "target_ref": self.target_ref,
                "surface": self.surface,
                "source_digest": self.source_digest,
                "deleted_at_ns": self.deleted_at_ns,
                "resurrection_blocked": True,
            }
        )


@dataclass(frozen=True, slots=True)
class DeletionEvidence:
    """Coverage projection for one deletion request."""

    evidence_id: str
    request_digest: str
    tombstone_digests: tuple[str, ...]
    covered_pairs: tuple[tuple[str, str], ...]
    missing_pairs: tuple[tuple[str, str], ...]
    assessed_at_ns: int
    external_side_effects: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _token("evidence_id", self.evidence_id))
        object.__setattr__(
            self,
            "request_digest",
            _sha256("request_digest", self.request_digest),
        )
        tombstones = tuple(sorted(set(self.tombstone_digests)))
        if any(
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in tombstones
        ):
            raise DataDeletionError(
                "tombstone_digests must contain lowercase sha256 digests"
            )
        object.__setattr__(self, "tombstone_digests", tombstones)
        object.__setattr__(
            self,
            "covered_pairs",
            _pairs("covered_pairs", self.covered_pairs),
        )
        object.__setattr__(
            self,
            "missing_pairs",
            _pairs("missing_pairs", self.missing_pairs),
        )
        if set(self.covered_pairs) & set(self.missing_pairs):
            raise DataDeletionError(
                "covered and missing deletion pairs must be disjoint"
            )
        object.__setattr__(
            self,
            "assessed_at_ns",
            _non_negative_int("assessed_at_ns", self.assessed_at_ns),
        )
        if self.external_side_effects is not False:
            raise DataDeletionError(
                "deletion evidence cannot perform external side effects"
            )

    @property
    def coverage_complete(self) -> bool:
        return not self.missing_pairs

    @property
    def digest(self) -> str:
        return _digest(
            {
                "evidence_id": self.evidence_id,
                "request_digest": self.request_digest,
                "tombstone_digests": list(self.tombstone_digests),
                "covered_pairs": [list(pair) for pair in self.covered_pairs],
                "missing_pairs": [list(pair) for pair in self.missing_pairs],
                "assessed_at_ns": self.assessed_at_ns,
                "external_side_effects": False,
            }
        )


def assess_deletion_evidence(
    *,
    evidence_id: str,
    request: DeletionRequest,
    tombstones: Iterable[DeletionTombstone],
    assessed_at_ns: int,
) -> DeletionEvidence:
    """Assess exact deletion-scope coverage without performing deletion."""

    if not isinstance(request, DeletionRequest):
        raise TypeError("request must be DeletionRequest")
    rows = tuple(tombstones)
    if any(not isinstance(item, DeletionTombstone) for item in rows):
        raise DataDeletionError(
            "tombstones must contain DeletionTombstone values"
        )
    assessed = _non_negative_int("assessed_at_ns", assessed_at_ns)
    if assessed < request.requested_at_ns:
        raise DataDeletionError(
            "deletion assessment cannot predate request"
        )

    expected = {
        (target, surface)
        for target in request.target_refs
        for surface in request.required_surfaces
    }
    covered: set[tuple[str, str]] = set()
    tombstone_ids: set[str] = set()
    for item in rows:
        if item.tombstone_id in tombstone_ids:
            raise DataDeletionError("tombstone IDs must be unique")
        tombstone_ids.add(item.tombstone_id)
        if item.request_id != request.request_id:
            raise DataDeletionError("tombstone request identity mismatch")
        if item.pair not in expected:
            raise DataDeletionError(
                "tombstone is outside declared deletion scope"
            )
        if item.pair in covered:
            raise DataDeletionError(
                "duplicate tombstone for deletion target/surface pair"
            )
        if item.deleted_at_ns < request.requested_at_ns:
            raise DataDeletionError("tombstone predates deletion request")
        if assessed < item.deleted_at_ns:
            raise DataDeletionError("deletion assessment predates tombstone")
        covered.add(item.pair)

    return DeletionEvidence(
        evidence_id=evidence_id,
        request_digest=request.digest,
        tombstone_digests=tuple(sorted(item.digest for item in rows)),
        covered_pairs=tuple(sorted(covered)),
        missing_pairs=tuple(sorted(expected - covered)),
        assessed_at_ns=assessed,
    )


__all__ = [
    "DataDeletionError",
    "DeletionEvidence",
    "DeletionRequest",
    "DeletionTombstone",
    "assess_deletion_evidence",
]
