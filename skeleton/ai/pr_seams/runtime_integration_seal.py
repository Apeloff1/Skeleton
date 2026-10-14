"""Native runtime integration seal against current main

Plane: runtime_integration_seal
PR: https://github.com/Apeloff1/Skeleton/pull/3485
Branch: ai/native-runtime-integration-v2-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3485.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3485"
KIND = "runtime-integration"


def _canon(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _h(prefix: str, payload: object) -> str:
    return prefix + sha256(_canon(payload).encode("utf-8")).hexdigest()


def _id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    if "\n" in value or len(value) > 240:
        raise ValueError(f"{name} must be a pointer clause")
    return value.strip()


def _u(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


def card(hit: bool, **extra: object) -> dict:
    body = {
        "kind": KIND,
        "hit": bool(hit),
        "law": LAW,
        "citation": CITATION,
        "stored_prose": 0,
    }
    body.update(extra)
    if body["stored_prose"] != 0:
        raise PermissionError("stored prose is forbidden")
    return body

REQUIRED = ("tokenizer", "weights", "kv", "sampler", "stop")


@dataclass(frozen=True)
class PlanePin:
    pin_id: str
    name: str
    digest: str
    generation: int

    @classmethod
    def create(cls, name: str, digest: str, generation: int):
        if name not in REQUIRED:
            raise ValueError("unknown integration plane")
        _id(digest, "digest")
        _u(generation, "generation")
        payload = {"name": name, "digest": digest, "generation": generation}
        return cls(_h("pin-sha256:", payload), name, digest, generation)


@dataclass(frozen=True)
class IntegrationSeal:
    seal_id: str
    generation: int
    pin_ids: tuple
    root: str


def seal(pins: Sequence[PlanePin]) -> IntegrationSeal:
    by = {}
    for pin in pins:
        prev = by.get(pin.name)
        if prev is not None and prev != pin:
            raise PermissionError("conflicting plane pin")
        by[pin.name] = pin
    if set(by) != set(REQUIRED):
        raise PermissionError("integration seal is incomplete")
    generations = {p.generation for p in by.values()}
    if len(generations) != 1:
        raise PermissionError("plane generation skew")
    generation = generations.pop()
    ordered = tuple(by[name].pin_id for name in REQUIRED)
    root = _h("integration-root:", {"generation": generation, "pin_ids": ordered})
    return IntegrationSeal(_h("seal-sha256:", {"root": root}), generation, ordered, root)


def exit_card(bound: IntegrationSeal) -> dict:
    return card(True, seal_id=bound.seal_id, generation=bound.generation, root=bound.root, pin_count=len(bound.pin_ids))
