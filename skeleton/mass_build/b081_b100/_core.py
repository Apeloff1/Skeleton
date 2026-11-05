"""Shared deterministic primitives for B081-B100 evidence contracts.

Every batch module produces a frozen, canonical-JSON evidence record whose
SHA-256 digest is stable across runs, so release gates (B090) and the
concept-to-release arena (B100) can replay and compare verdicts exactly.
Fail-closed: any malformed input raises ``ContractError`` rather than passing.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


class ContractError(ValueError):
    """Raised when evidence input is malformed or a gate cannot be evaluated."""


MAX_CANONICAL_BYTES = 4 * 1024 * 1024


def canonical(obj: Any) -> str:
    """Reject nonfinite values and oversized evidence before hashing or release use."""
    try:
        result = json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False, default=_reject,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContractError("non-canonical evidence value") from exc
    if len(result) > MAX_CANONICAL_BYTES:
        raise ContractError("canonical evidence exceeds byte bound")
    return result


def _reject(obj: Any) -> Any:
    raise ContractError(f"non-canonical value: {type(obj).__name__}")


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise ContractError(msg)


def require_str(value: Any, name: str) -> str:
    require(isinstance(value, str) and value.strip() != "", f"{name} must be a non-empty string")
    return value


def require_keys(m: Mapping[str, Any], keys: Iterable[str], name: str) -> None:
    require(isinstance(m, Mapping), f"{name} must be a mapping")
    missing = sorted(k for k in keys if k not in m)
    require(not missing, f"{name} missing keys: {missing}")


@dataclass(frozen=True)
class Verdict:
    batch: str
    passed: bool
    findings: tuple[str, ...] = ()
    facts: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch": self.batch,
            "passed": self.passed,
            "findings": list(self.findings),
            "facts": dict(self.facts),
        }

    @property
    def digest(self) -> str:
        return digest(self.as_dict())


def verdict(batch: str, findings: Iterable[str], **facts: Any) -> Verdict:
    f = tuple(sorted(set(findings)))
    return Verdict(batch=batch, passed=not f, findings=f, facts=facts)
