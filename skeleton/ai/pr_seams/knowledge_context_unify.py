"""Unify governed web evidence and project memory context

Plane: knowledge_context_unify
PR: https://github.com/Apeloff1/Skeleton/pull/3479
Branch: automation/unified-knowledge-context-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3479.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3479"
KIND = "knowledge-unify"


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

@dataclass(frozen=True)
class Shard:
    shard_id: str
    origin: str
    url: str
    weight_ppm: int

    @classmethod
    def create(cls, origin: str, url: str, weight_ppm: int):
        if origin not in {"web", "memory"}:
            raise ValueError("origin must be web or memory")
        _id(url, "url")
        _u(weight_ppm, "weight_ppm")
        if weight_ppm == 0:
            raise ValueError("weight must be positive")
        payload = {"origin": origin, "url": url, "weight_ppm": weight_ppm}
        return cls(_h("shard-sha256:", payload), origin, url, weight_ppm)


@dataclass(frozen=True)
class Unified:
    unified_id: str
    shard_ids: tuple
    weight_ppm: int


def unify(shards: Sequence[Shard]) -> Unified:
    if not shards:
        raise ValueError("unify requires shards")
    if len(shards) > 8:
        raise PermissionError("pointer N-cap exceeded")
    origins = {s.origin for s in shards}
    if origins != {"web", "memory"}:
        raise PermissionError("unify requires both web and memory")
    total = sum(s.weight_ppm for s in shards)
    if total != 1_000_000:
        raise PermissionError("lineage weights must sum to 1")
    ordered = tuple(sorted(shards, key=lambda s: (s.origin, s.url)))
    ids = tuple(s.shard_id for s in ordered)
    return Unified(_h("unify-sha256:", {"shard_ids": ids, "weight_ppm": total}), ids, total)


def exit_card(bound: Unified) -> dict:
    return card(True, unified_id=bound.unified_id, weight_ppm=bound.weight_ppm, n=len(bound.shard_ids))
