"""skeleton/gameforge/safety.py

Unsafe-state refusal. Deterministic, rule-based screens for content and
state; anything flagged raises ``UnsafeStateError`` (top rung).
"""
from __future__ import annotations

import re
from typing import Iterable, Tuple

from .errors import UnsafeStateError

_BLOCKED_TERMS: Tuple[str, ...] = (
    "real-world violence instructions", "self-harm", "child exploitation", "malware", "credential harvesting",
    "doxx", "keylogger", "ransomware",
)
_SCRIPT_DENY = re.compile(r"\b(eval|exec|__import__|subprocess|os\.system|socket|open)\s*\(")
MAX_TEXT = 4000


def screen_text(step: str, *texts: str) -> None:
    for t in texts:
        if len(t) > MAX_TEXT:
            raise UnsafeStateError("text exceeds safe length", step=step, detail={"len": len(t)})
        low = t.lower()
        for term in _BLOCKED_TERMS:
            if term in low:
                raise UnsafeStateError(f"blocked content term {term!r}", step=step, detail={"term": term})
        if "\x00" in t:
            raise UnsafeStateError("NUL byte in text", step=step)


def screen_script(step: str, path: str, source: str) -> None:
    m = _SCRIPT_DENY.search(source)
    if m:
        raise UnsafeStateError(f"script {path} uses denied call {m.group(1)}", step=step, detail={"path": path})


def screen_paths(step: str, paths: Iterable[str]) -> None:
    for p in paths:
        if p.startswith("/") or ".." in p.split("/") or "\\" in p or ":" in p:
            raise UnsafeStateError(f"unsafe export path {p!r}", step=step, detail={"path": p})
