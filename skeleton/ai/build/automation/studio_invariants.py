"""Cross-layer invariants for autonomous execution."""
from __future__ import annotations
from typing import Iterable

def require_unique(values: Iterable[str], label: str) -> tuple[str,...]:
    rows=tuple(values)
    if any(not value for value in rows): raise ValueError(f"{label} contains empty identity")
    if len(set(rows)) != len(rows): raise ValueError(f"{label} contains duplicate identity")
    return rows

def require_subset(actual: Iterable[str], allowed: Iterable[str], label: str) -> None:
    extra=set(actual)-set(allowed)
    if extra: raise ValueError(f"{label} escaped authority: {sorted(extra)}")

def require_hex_digest(value: str, label: str, length: int=64) -> str:
    if len(value)!=length or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} is malformed")
    return value
