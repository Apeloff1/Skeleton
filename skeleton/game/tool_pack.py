"""Named tools."""

from __future__ import annotations

from typing import Any


class ToolPackError(ValueError):
    pass


TOOLS = (
    "pick", "torch", "kit", "scope", "hook", "line", "wedge", "clamp",
    "file", "brush", "lens", "bell", "whistle", "chalk", "tape", "pin",
)


def own(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TOOLS:
        raise ToolPackError(name)
    nxt = dict(state)
    have = list(nxt.get("tools") or [])
    if name not in have:
        have.append(name)
    nxt["tools"] = have
    nxt["stored_prose"] = 0
    return nxt


def use(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TOOLS:
        raise ToolPackError(name)
    nxt = dict(state)
    if name not in list(nxt.get("tools") or []):
        raise ToolPackError("missing")
    nxt["last_tool"] = name
    nxt["stored_prose"] = 0
    return nxt
