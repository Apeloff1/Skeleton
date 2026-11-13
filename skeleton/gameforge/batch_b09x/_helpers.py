"""Shared contract helpers for the #807 B09x platform slice (local; no unmerged imports)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


class ContractError(ValueError):
    """A platform contract was violated."""


def canonical(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    )


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode("ascii")).hexdigest()


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise ContractError(msg)


def require_str(value: Any, name: str, *, max_len: int = 256) -> str:
    require(
        isinstance(value, str)
        and bool(value)
        and len(value) <= max_len
        and "\x00" not in value,
        f"{name} must be a non-empty string",
    )
    return value


@dataclass(frozen=True)
class Verdict:
    batch: str
    passed: bool
    findings: tuple[str, ...]
    detail: dict = field(default_factory=dict)


def verdict(batch: str, findings, **detail: Any) -> Verdict:
    f = tuple(findings)
    return Verdict(batch, not f, f, dict(detail))
