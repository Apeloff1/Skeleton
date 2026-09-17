"""Named radio channels."""

from __future__ import annotations

from typing import Any


class RadioPackError(ValueError):
    pass


CH = tuple(f"ch_{i:02d}" for i in range(16))


def tune(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CH:
        raise RadioPackError(name)
    nxt = dict(state)
    nxt["channel"] = name
    nxt["stored_prose"] = 0
    return nxt


def say(state: dict[str, Any], name: str, sig: str) -> dict[str, Any]:
    if name not in CH:
        raise RadioPackError(name)
    nxt = dict(state)
    if nxt.get("channel") != name:
        raise RadioPackError("channel")
    nxt["heard"] = sig
    nxt["stored_prose"] = 0
    return nxt
