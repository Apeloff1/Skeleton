"""Named joints."""

from __future__ import annotations

from typing import Any


class JointPackError(ValueError):
    pass


JOINT = tuple(f"jt_{i:02d}" for i in range(28))


def set_joint(node: dict[str, Any], name: str, a: str, b: str) -> dict[str, Any]:
    if name not in JOINT:
        raise JointPackError(name)
    nxt = dict(node)
    cur = dict(nxt.get("joint") or {})
    cur[name] = (a, b)
    nxt["joint"] = cur
    nxt["stored_prose"] = 0
    return nxt
