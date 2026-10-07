"""Bind verified generation evidence into project memory

Plane: generation_memory_bridge
PR: https://github.com/Apeloff1/Skeleton/pull/3478
Branch: automation/evidence-generation-memory-bridge-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3478.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3478"
KIND = "memory-bridge"


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
class Evidence:
    evidence_id: str
    generation_id: str
    digest: str
    verified: bool

    @classmethod
    def create(cls, generation_id: str, digest: str, verified: bool):
        _id(generation_id, "generation_id")
        _id(digest, "digest")
        if not isinstance(verified, bool):
            raise ValueError("verified must be bool")
        payload = {"generation_id": generation_id, "digest": digest, "verified": verified}
        return cls(_h("ev-sha256:", payload), generation_id, digest, verified)


@dataclass(frozen=True)
class MemorySlot:
    slot_id: str
    project_id: str
    evidence_id: str
    reversible: bool


def bind(project_id: str, evidence: Evidence) -> MemorySlot:
    _id(project_id, "project_id")
    if not evidence.verified:
        raise PermissionError("unverified generation cannot enter memory")
    payload = {"project_id": project_id, "evidence_id": evidence.evidence_id, "reversible": True}
    return MemorySlot(_h("slot-sha256:", payload), project_id, evidence.evidence_id, True)


def reverse(slot: MemorySlot) -> dict:
    if not slot.reversible:
        raise PermissionError("slot is not reversible")
    return card(True, slot_id=slot.slot_id, reversed=True, evidence_id=slot.evidence_id)


def exit_card(slot: MemorySlot) -> dict:
    return card(True, slot_id=slot.slot_id, project_id=slot.project_id, evidence_id=slot.evidence_id, reversible=True)
