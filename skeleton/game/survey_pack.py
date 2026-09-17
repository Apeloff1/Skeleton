"""Named surveys. Pointer only."""

from __future__ import annotations

from typing import Any


class SurveyPackError(ValueError):
    pass


SURVEY = tuple(f"sy_{i:02d}" for i in range(28))


def log(state: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    if name not in SURVEY:
        raise SurveyPackError(name)
    if not digest:
        raise SurveyPackError("digest")
    nxt = dict(state)
    cur = dict(nxt.get("survey") or {})
    cur[name] = digest
    nxt["survey"] = cur
    nxt["stored_prose"] = 0
    return nxt
