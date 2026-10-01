"""Owned, evidence-backed, expiring anti-pattern exceptions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


class AntiPatternPolicyError(RuntimeError):
    pass


def _text(value: str, field: str, max_len: int = 2048) -> str:
    text = str(value).strip()
    if not text or len(text) > max_len:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


def _utc(value: str, field: str) -> datetime:
    text = _text(value, field, 64)
    if not text.endswith("Z"):
        raise ValueError(f"{field} must be RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{field} must be RFC3339 UTC") from exc
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class AntiPatternException:
    exception_id: str
    pattern_id: str
    owner_id: str
    rationale: str
    created_at_utc: str
    expires_at_utc: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for field, limit in (
            ("exception_id", 192),
            ("pattern_id", 192),
            ("owner_id", 192),
            ("rationale", 2048),
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field, limit))
        created = _utc(self.created_at_utc, "created_at_utc")
        expires = _utc(self.expires_at_utc, "expires_at_utc")
        if expires <= created:
            raise ValueError("exception expiry must be after creation")
        refs = tuple(_text(item, "evidence_ref") for item in self.evidence_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ValueError("anti-pattern exception requires unique evidence_refs")
        object.__setattr__(self, "evidence_refs", refs)


def validate_exception(
    exception: AntiPatternException,
    *,
    policy: Mapping[str, tuple[bool, int | None]],
    as_of: datetime | None = None,
) -> None:
    if exception.pattern_id not in policy:
        raise AntiPatternPolicyError("unknown anti-pattern")
    allowed, max_ttl_days = policy[exception.pattern_id]
    if not allowed:
        raise AntiPatternPolicyError("anti-pattern is non-waivable")
    if not isinstance(max_ttl_days, int) or isinstance(max_ttl_days, bool) or max_ttl_days <= 0:
        raise AntiPatternPolicyError("waivable anti-pattern requires positive max TTL")
    created = _utc(exception.created_at_utc, "created_at_utc")
    expires = _utc(exception.expires_at_utc, "expires_at_utc")
    if (expires - created).total_seconds() > max_ttl_days * 86400:
        raise AntiPatternPolicyError("anti-pattern exception exceeds max TTL")
    if as_of is None:
        now = datetime.now(timezone.utc)
    else:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise AntiPatternPolicyError("as_of must be timezone-aware")
        now = as_of.astimezone(timezone.utc)
    if now < created:
        raise AntiPatternPolicyError("anti-pattern exception is not yet active")
    if now >= expires:
        raise AntiPatternPolicyError("anti-pattern exception is expired")


__all__ = [
    "AntiPatternException",
    "AntiPatternPolicyError",
    "validate_exception",
]
