"""Named kettle stitches."""

from __future__ import annotations

from typing import Any


class KettlestitchPackError(ValueError):
    pass


KETTLE = tuple(f"ks_{i:02d}" for i in range(12))


def sew(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in KETTLE:
        raise KettlestitchPackError(name)
    nxt = dict(state)
    nxt["kettlestitch"] = name
    nxt["sewn"] = int(nxt.get("sewn", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
