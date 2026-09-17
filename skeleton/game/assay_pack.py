"""Named assays."""

from __future__ import annotations

from typing import Any


class AssayPackError(ValueError):
    pass


ASSAY = tuple(f"as_{i:02d}" for i in range(12))


def test(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ASSAY:
        raise AssayPackError(name)
    nxt = dict(state)
    nxt["assay"] = name
    nxt["tested"] = 1
    nxt["stored_prose"] = 0
    return nxt
