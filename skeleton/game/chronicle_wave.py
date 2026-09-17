"""Wave-4 chronicle stamps."""

from __future__ import annotations

from typing import Any

from skeleton.game.seal_card import seal


class ChronicleWaveError(ValueError):
    pass


MARKS = tuple(f"ch_{i:02d}" for i in range(20))


def stamp(name: str, digest: str, seed: int) -> dict[str, Any]:
    if name not in MARKS:
        raise ChronicleWaveError(name)
    if not digest:
        raise ChronicleWaveError("digest")
    return seal({"kind": name, "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})
