"""Named chronicle stamps. Pointer only."""
from __future__ import annotations
from typing import Any
from skeleton.game.seal_card import seal

class ChroniclePackError(ValueError):
    pass

def stamp_world(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_world", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_flesh(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_flesh", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_campus(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_campus", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_lab(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_lab", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_sim(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_sim", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_nexus(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_nexus", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_turn(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_turn", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_compose(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_compose", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_bundle(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_bundle", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_monte(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_monte", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_warena(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_warena", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_hunt(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_hunt", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_occ(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_occ", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_extract(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_extract", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_path(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_path", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

def stamp_kit(digest: str, seed: int) -> dict[str, Any]:
    if not digest:
        raise ChroniclePackError("digest")
    return seal({"kind": "stamp_kit", "seed": int(seed), "src": digest, "sota_ready": False, "stored_prose": 0})

STAMP = {
    "world": stamp_world, "flesh": stamp_flesh, "campus": stamp_campus, "lab": stamp_lab,
    "sim": stamp_sim, "nexus": stamp_nexus, "turn": stamp_turn, "compose": stamp_compose,
    "bundle": stamp_bundle, "monte": stamp_monte, "warena": stamp_warena, "hunt": stamp_hunt,
    "occ": stamp_occ, "extract": stamp_extract, "path": stamp_path, "kit": stamp_kit,
}

def stamp(name: str, digest: str, seed: int) -> dict[str, Any]:
    if name not in STAMP:
        raise ChroniclePackError(name)
    return STAMP[name](digest, seed)
