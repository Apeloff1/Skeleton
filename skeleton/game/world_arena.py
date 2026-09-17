"""Sealed world-tick arena. Same seed matches. Split seed diverges."""

from __future__ import annotations

from typing import Any

from skeleton.game.world_tick import play


class WorldArenaError(ValueError):
    pass


def compare(*, seed_a: int, seed_b: int, ticks: int = 16) -> dict[str, Any]:
    if ticks < 1 or ticks > 64:
        raise WorldArenaError("ticks")
    left = play(seed=int(seed_a), ticks=ticks)
    right = play(seed=int(seed_b), ticks=ticks)
    match = left["digest"] == right["digest"]
    if int(seed_a) == int(seed_b) and not match:
        raise WorldArenaError("same seed must match")
    return {
        "kind": "world_arena",
        "seed_a": int(seed_a),
        "seed_b": int(seed_b),
        "match": match,
        "digest_a": left["digest"],
        "digest_b": right["digest"],
        "extract_a": left["extract_count"],
        "extract_b": right["extract_count"],
        "sota_ready": False,
        "stored_prose": 0,
        "ok": True,
    }


def monte(*, seed: int, n: int = 4, ticks: int = 16) -> dict[str, Any]:
    if n < 2 or n > 8:
        raise WorldArenaError("n")
    digests = []
    extracts = []
    for i in range(n):
        card = play(seed=int(seed) + i, ticks=ticks)
        digests.append(card["digest"])
        extracts.append(card["extract_count"])
    unique = len(set(digests))
    if unique != n:
        raise WorldArenaError("monte collision")
    if any(x != 1 for x in extracts):
        raise WorldArenaError("extract contract")
    return {
        "kind": "world_monte",
        "n": n,
        "unique_digests": unique,
        "extracts": extracts,
        "sota_ready": False,
        "stored_prose": 0,
        "ok": True,
    }
