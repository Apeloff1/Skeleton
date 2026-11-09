"""Deterministic privacy-label and purpose contracts for the AI runtime.

This module evaluates declared technical policy only. It does not infer legal
requirements, perform data export, mutate stored data, or grant authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable


_LEVELS = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


class PrivacyEngineError(ValueError):
    """A privacy-label, grant, or decision invariant failed."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PrivacyEngineError(f"{name} must be non-empty normalized text")
    if len(value) > 256:
        raise PrivacyEngineError(f"{name} exceeds maximum length")
    return value


def _tokens(
    name: str,
    values: Iterable[str],
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise PrivacyEngineError(f"{name} must be a collection")
    result = tuple(sorted({_token(name, value) for value in values}))
    if not result and not allow_empty:
        raise PrivacyEngineError(f"{name} must be non-empty")
    return result


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PrivacyEngineError(f"{name} must be a non-negative integer")
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
        raise PrivacyEngineError("privacy evidence must be canonical JSON") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PrivacyLabel:
    """Declared privacy constraints attached to data or a derived artifact."""

    label_id: str
    classification: str
    allowed_purposes: tuple[str, ...]
    jurisdiction_scopes: tuple[str, ...]
    source_ref: str
    parent_label_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "label_id", _token("label_id", self.label_id))
        classification = _token("classification", self.classification)
        if classification not in _LEVELS:
            raise PrivacyEngineError(
                "classification must be public, internal, confidential, or restricted"
            )
        object.__setattr__(self, "classification", classification)
        object.__setattr__(
            self,
            "allowed_purposes",
            _tokens("allowed_purpose", self.allowed_purposes),
        )
        object.__setattr__(
            self,
            "jurisdiction_scopes",
            _tokens("jurisdiction_scope", self.jurisdiction_scopes),
        )
        object.__setattr__(self, "source_ref", _token("source_ref", self.source_ref))
        parent_digests = tuple(sorted(set(self.parent_label_digests)))
        if any(
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in parent_digests
        ):
            raise PrivacyEngineError(
                "parent_label_digests must contain lowercase sha256 digests"
            )
        object.__setattr__(self, "parent_label_digests", parent_digests)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "label_id": self.label_id,
                "classification": self.classification,
                "allowed_purposes": list(self.allowed_purposes),
                "jurisdiction_scopes": list(self.jurisdiction_scopes),
                "source_ref": self.source_ref,
                "parent_label_digests": list(self.parent_label_digests),
            }
        )


@dataclass(frozen=True, slots=True)
class PurposeGrant:
    """Time-bounded declared permission for one subject and one purpose."""

    grant_id: str
    subject_id: str
    purpose: str
    jurisdiction_scopes: tuple[str, ...]
    expires_at_ns: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "grant_id", _token("grant_id", self.grant_id))
        object.__setattr__(self, "subject_id", _token("subject_id", self.subject_id))
        object.__setattr__(self, "purpose", _token("purpose", self.purpose))
        object.__setattr__(
            self,
            "jurisdiction_scopes",
            _tokens("jurisdiction_scope", self.jurisdiction_scopes),
        )
        expires = _non_negative_int("expires_at_ns", self.expires_at_ns)
        if expires == 0:
            raise PrivacyEngineError("expires_at_ns must be positive")
        object.__setattr__(self, "expires_at_ns", expires)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "grant_id": self.grant_id,
                "subject_id": self.subject_id,
                "purpose": self.purpose,
                "jurisdiction_scopes": list(self.jurisdiction_scopes),
                "expires_at_ns": self.expires_at_ns,
            }
        )


@dataclass(frozen=True, slots=True)
class PrivacyDecision:
    """Evidence-only outcome of declared privacy policy evaluation."""

    decision_id: str
    label_digest: str
    grant_digest: str
    subject_id: str
    purpose: str
    jurisdiction_scope: str
    allowed: bool
    reason_code: str
    evaluated_at_ns: int
    external_side_effects: bool = False

    def __post_init__(self) -> None:
        for name in (
            "decision_id",
            "subject_id",
            "purpose",
            "jurisdiction_scope",
            "reason_code",
        ):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        for name in ("label_digest", "grant_digest"):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise PrivacyEngineError(f"{name} must be a lowercase sha256 digest")
        if not isinstance(self.allowed, bool):
            raise PrivacyEngineError("allowed must be boolean")
        object.__setattr__(
            self,
            "evaluated_at_ns",
            _non_negative_int("evaluated_at_ns", self.evaluated_at_ns),
        )
        if self.external_side_effects is not False:
            raise PrivacyEngineError(
                "privacy decisions cannot perform external side effects"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "decision_id": self.decision_id,
                "label_digest": self.label_digest,
                "grant_digest": self.grant_digest,
                "subject_id": self.subject_id,
                "purpose": self.purpose,
                "jurisdiction_scope": self.jurisdiction_scope,
                "allowed": self.allowed,
                "reason_code": self.reason_code,
                "evaluated_at_ns": self.evaluated_at_ns,
                "external_side_effects": False,
            }
        )


def derive_privacy_label(
    *,
    label_id: str,
    parents: Iterable[PrivacyLabel],
    source_ref: str,
) -> PrivacyLabel:
    """Derive the most restrictive label shared by all parent evidence."""

    parent_rows = tuple(parents)
    if not parent_rows:
        raise PrivacyEngineError("derived label requires at least one parent")
    if any(not isinstance(item, PrivacyLabel) for item in parent_rows):
        raise PrivacyEngineError("parents must contain PrivacyLabel values")

    classification = max(
        (item.classification for item in parent_rows),
        key=lambda value: _LEVELS[value],
    )
    purposes = set(parent_rows[0].allowed_purposes)
    jurisdictions = set(parent_rows[0].jurisdiction_scopes)
    for item in parent_rows[1:]:
        purposes.intersection_update(item.allowed_purposes)
        jurisdictions.intersection_update(item.jurisdiction_scopes)
    if not purposes:
        raise PrivacyEngineError(
            "parent labels have no common allowed purpose"
        )
    if not jurisdictions:
        raise PrivacyEngineError(
            "parent labels have no common jurisdiction scope"
        )

    return PrivacyLabel(
        label_id=label_id,
        classification=classification,
        allowed_purposes=tuple(sorted(purposes)),
        jurisdiction_scopes=tuple(sorted(jurisdictions)),
        source_ref=source_ref,
        parent_label_digests=tuple(
            sorted({item.digest for item in parent_rows})
        ),
    )


def evaluate_privacy_use(
    *,
    decision_id: str,
    label: PrivacyLabel,
    grant: PurposeGrant,
    subject_id: str,
    purpose: str,
    jurisdiction_scope: str,
    now_ns: int,
) -> PrivacyDecision:
    """Evaluate declared purpose/scope compatibility without side effects."""

    if not isinstance(label, PrivacyLabel):
        raise TypeError("label must be PrivacyLabel")
    if not isinstance(grant, PurposeGrant):
        raise TypeError("grant must be PurposeGrant")
    subject = _token("subject_id", subject_id)
    requested_purpose = _token("purpose", purpose)
    jurisdiction = _token("jurisdiction_scope", jurisdiction_scope)
    now = _non_negative_int("now_ns", now_ns)

    allowed = False
    if grant.subject_id != subject:
        reason = "subject-mismatch"
    elif now >= grant.expires_at_ns:
        reason = "grant-expired"
    elif grant.purpose != requested_purpose:
        reason = "grant-purpose-mismatch"
    elif requested_purpose not in label.allowed_purposes:
        reason = "label-purpose-denied"
    elif jurisdiction not in grant.jurisdiction_scopes:
        reason = "grant-jurisdiction-denied"
    elif jurisdiction not in label.jurisdiction_scopes:
        reason = "label-jurisdiction-denied"
    else:
        allowed = True
        reason = "allowed"

    return PrivacyDecision(
        decision_id=decision_id,
        label_digest=label.digest,
        grant_digest=grant.digest,
        subject_id=subject,
        purpose=requested_purpose,
        jurisdiction_scope=jurisdiction,
        allowed=allowed,
        reason_code=reason,
        evaluated_at_ns=now,
    )


__all__ = [
    "PrivacyDecision",
    "PrivacyEngineError",
    "PrivacyLabel",
    "PurposeGrant",
    "derive_privacy_label",
    "evaluate_privacy_use",
]
