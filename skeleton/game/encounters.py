"""Deterministic encounter / hazard / route tables. Catalog-adjacent. No coin."""

from __future__ import annotations

import hashlib
from typing import Any


MAX_ROWS = 16
KINDS = ("encounter", "hazard", "route")


class EncounterError(ValueError):
    """Encounter table contract violation."""


def _roll(seed: int, label: str) -> int:
    material = f"{int(seed)}:{label}:table".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _row(kind: str, seed: int, index: int) -> dict[str, Any]:
    if kind not in KINDS:
        raise EncounterError(f"unknown table kind: {kind}")
    roll = _roll(seed, f"{kind}:{index}")
    heat = roll % 8
    scrap = 1 + (roll // 8) % 4
    return {
        "id": f"{kind[0]}{index}",
        "kind": kind,
        "heat": heat,
        "scrap": scrap,
        "door": f"r{(roll // 32) % 4}",
        "stored_prose": 0,
    }


def table(*, seed: int, kind: str, n: int = 4) -> dict[str, Any]:
    if isinstance(n, bool) or not isinstance(n, int) or n < 1 or n > MAX_ROWS:
        raise EncounterError("row count out of range")
    rows = [_row(kind, int(seed), index) for index in range(n)]
    return {
        "kind": "catalog_table",
        "table": kind,
        "seed": int(seed),
        "n": n,
        "rows": rows,
        "meta": {"seed": int(seed), "step": "mass_forge", "rotor": kind},
        "stored_prose": 0,
    }


def pack_tables(seed: int) -> dict[str, Any]:
    tables = [table(seed=seed, kind=kind, n=4) for kind in KINDS]
    return {
        "kind": "catalog_pack",
        "seed": int(seed),
        "tables": tables,
        "n": sum(item["n"] for item in tables),
        "stored_prose": 0,
    }
