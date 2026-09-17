"""Split a vision stimulus into pointer clauses. Mesh stores no sentence."""

from __future__ import annotations

import re
from typing import Any


N_CAP = 8
_URL = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_REPO = re.compile(r"\b([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)\b")
_ARXIV = re.compile(r"\barxiv\.org/abs/([0-9.]+)\b", re.IGNORECASE)
_ISSUE = re.compile(r"#(\d+)\b")


class VisionParseError(ValueError):
    """Pointer parse violation."""


def parse_pointers(stimulus: str, *, cap: int = N_CAP) -> dict[str, Any]:
    if not isinstance(stimulus, str):
        raise VisionParseError("stimulus must be a string")
    if cap < 1 or cap > N_CAP:
        raise VisionParseError("pointer cap out of range")
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(kind: str, value: str) -> None:
        key = f"{kind}:{value}"
        if key in seen:
            return
        seen.add(key)
        found.append({"kind": kind, "value": value})

    for match in _URL.finditer(stimulus):
        _add("url", match.group(0).rstrip(").,]"))
    for match in _ARXIV.finditer(stimulus):
        _add("arxiv", match.group(1))
    for match in _ISSUE.finditer(stimulus):
        _add("issue", match.group(1))
    for match in _REPO.finditer(stimulus):
        owner, name = match.group(1), match.group(2)
        if owner.lower() in {"http", "https", "www"}:
            continue
        _add("repo", f"{owner}/{name}")

    kept = found[:cap]
    return {
        "kind": "parse",
        "n": len(kept),
        "dropped": max(0, len(found) - len(kept)),
        "pointers": kept,
        "stored_prose": 0,
        "hit": 0 if len(found) > cap else 1,
    }
