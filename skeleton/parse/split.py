"""Split stimulus into pointer clauses. Mesh keeps no sentence."""

from __future__ import annotations

import re

from skeleton.parse.law import N_CAP

_ARXIV = re.compile(r"https?://arxiv\.org/abs/[^\s]+", re.I)
_GITHUB = re.compile(r"(?:https?://)?github\.com/[^\s]+", re.I)
_URL = re.compile(r"https?://[^\s]+", re.I)


def _kind(token: str) -> str:
    low = token.lower()
    if "arxiv.org/abs/" in low:
        return "arxiv"
    if "github.com/" in low:
        return "github"
    return "url"


def split(stimulus: str) -> dict:
    found: list[str] = []
    for rx in (_ARXIV, _GITHUB, _URL):
        for m in rx.finditer(stimulus or ""):
            tok = m.group(0).rstrip(").,;")
            if tok not in found:
                found.append(tok)
    pointers = [{"kind": _kind(t), "ref": t} for t in found[:N_CAP]]
    dropped = max(0, len(found) - N_CAP)
    return {
        "kind": "parse",
        "n": len(pointers),
        "pointers": pointers,
        "hit": 0 if dropped else 1,
        "dropped": dropped,
        "stored_prose": 0,
    }
