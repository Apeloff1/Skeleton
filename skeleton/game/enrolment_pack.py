"""Named enrolments."""

from __future__ import annotations

from typing import Any


class EnrolmentPackError(ValueError):
    pass


ENROL = tuple(f"en_{i:02d}" for i in range(16))


def enrol(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ENROL:
        raise EnrolmentPackError(name)
    nxt = dict(state)
    have = list(nxt.get("enrolment") or [])
    have.append(name)
    nxt["enrolment"] = have
    nxt["stored_prose"] = 0
    return nxt
