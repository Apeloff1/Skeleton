"""Deterministic catalog row materializer. Tables expand from seed+index."""

from __future__ import annotations

from typing import Any, Callable


N = 1000


class CatalogGenError(ValueError):
    """Catalog generator contract violation."""


def _item(i: int) -> dict[str, Any]:
    return {"id": f"item_{i:04d}", "k": i % 10, "c": 1 + i % 9, "h": i % 8, "p": 0}


def _enc(i: int) -> dict[str, Any]:
    return {"id": f"e{i:04d}", "k": i % 3, "h": i % 8, "s": 1 + i % 5, "p": 0}


def _room(i: int) -> dict[str, Any]:
    return {"id": f"lvl_{i:04d}", "k": i % 7, "h": i % 8, "d": i % 8, "p": 0}


def _recipe(i: int) -> dict[str, Any]:
    return {"id": f"rec_{i:04d}", "a": i % 200, "b": (i + 7) % 200, "o": (i + 13) % 200, "h": 2 + i % 6, "p": 0}


def _quest(i: int) -> dict[str, Any]:
    return {"id": f"q_{i:04d}", "v": i % 8, "n": 1 + i % 8, "r": i % 400, "p": 0}


def _ai(i: int) -> dict[str, Any]:
    return {"id": f"ai_{i:04d}", "x": i % 64, "y": (i * 3) % 48, "h": i % 8, "r": i % 800, "p": 0}


def _tok(i: int) -> dict[str, Any]:
    return {"id": f"tok_{i:04d}", "t": i, "per": 4 + i % 4, "g": 1 + i % 3, "p": 0}


def _bal(i: int) -> dict[str, Any]:
    return {"id": f"bal_{i:04d}", "ax": i % 4, "b": 20 + i % 70, "d": 1 + i % 5, "p": 0}


def _door(i: int) -> dict[str, Any]:
    return {"id": f"door_{i:04d}", "a": i % 8, "b": (i + 1) % 8, "l": int(i % 7 == 0), "p": 0}


def _ext(i: int) -> dict[str, Any]:
    return {"id": f"ext_{i:04d}", "r": i, "s": 1 + i % 4, "h": 8 + i % 8, "p": 0}


def _mass(i: int) -> dict[str, Any]:
    return {"id": f"mass_{i:04d}", "f": 1 + i % 8, "m": round(1.1 ** (1 + i % 8), 6), "p": 0}


def _fix(i: int) -> dict[str, Any]:
    return {"id": f"fix_{i:04d}", "t": i % 64, "v": i % 5, "s": i % 16, "p": 0}


def _right(i: int) -> dict[str, Any]:
    return {"id": f"right_{i:04d}", "rel": int(i % 20 == 0), "p": 0}


def _heat(i: int) -> dict[str, Any]:
    return {"id": f"heat_{i:04d}", "t": i, "h": i % 101, "s": (100 - i) % 101, "p": 0}


def _seed(i: int) -> dict[str, Any]:
    return {"id": f"seed_{i:04d}", "s": 1000 + i, "r": 2 + i % 7, "e": i % 3, "p": 0}


def _tick(i: int) -> dict[str, Any]:
    return {"id": f"tick_{i:04d}", "t": i, "v": i % 8, "to": i % 8, "k": int(i % 4 == 3), "p": 0}


def _bank(bank: int) -> Callable[[int], dict[str, Any]]:
    def row(i: int) -> dict[str, Any]:
        return {"id": f"lb{bank}_{i:04d}", "b": bank, "i": i, "v": i % 8, "r": (bank * 1000 + i) % 800, "p": 0}

    return row


BUILDERS: dict[str, Callable[[int], dict[str, Any]]] = {
    "catalog_items_table": _item,
    "catalog_encounters_table": _enc,
    "catalog_rooms_table": _room,
    "catalog_recipes_table": _recipe,
    "catalog_quests_table": _quest,
    "catalog_ai_table": _ai,
    "catalog_tokens_table": _tok,
    "catalog_balance_table": _bal,
    "catalog_doors_table": _door,
    "catalog_extracts_table": _ext,
    "catalog_mass_table": _mass,
    "catalog_replay_fix_table": _fix,
    "catalog_rights_table": _right,
    "catalog_heat_table": _heat,
    "catalog_seeds_table": _seed,
    "catalog_ticks_table": _tick,
    "catalog_level_bank_0": _bank(0),
    "catalog_level_bank_1": _bank(1),
    "catalog_level_bank_2": _bank(2),
    "catalog_level_bank_3": _bank(3),
    "catalog_level_bank_4": _bank(4),
    "catalog_level_bank_5": _bank(5),
    "catalog_level_bank_6": _bank(6),
    "catalog_level_bank_7": _bank(7),
}


def table(kind: str, n: int = N) -> tuple[dict[str, Any], ...]:
    if kind not in BUILDERS:
        raise CatalogGenError(f"unknown catalog kind: {kind}")
    if n < 1 or n > N:
        raise CatalogGenError("n out of range")
    build = BUILDERS[kind]
    return tuple(build(i) for i in range(n))
