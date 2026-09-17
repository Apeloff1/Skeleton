"""Named vats."""

from __future__ import annotations

from typing import Any


class VatPackError(ValueError):
    pass


VAT = tuple(f"vt_{i:02d}" for i in range(12))


def soak(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in VAT:
        raise VatPackError(name)
    nxt = dict(node)
    nxt["vat"] = name
    nxt["soak"] = int(nxt.get("soak", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
