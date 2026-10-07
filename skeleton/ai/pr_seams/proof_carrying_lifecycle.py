"""Proof-carrying governed learning lifecycle

Plane: proof_carrying_lifecycle
PR: https://github.com/Apeloff1/Skeleton/pull/3482
Branch: automation/proof-carrying-ai-lifecycle-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3482.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3482"
KIND = "proof-lifecycle"


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

PHASES = ("propose", "admit", "hold", "promote")


@dataclass(frozen=True)
class Proof:
    proof_id: str
    phase: str
    claim_id: str
    digest: str

    @classmethod
    def create(cls, phase: str, claim_id: str, digest: str):
        if phase not in PHASES:
            raise ValueError("unknown lifecycle phase")
        _id(claim_id, "claim_id")
        _id(digest, "digest")
        payload = {"phase": phase, "claim_id": claim_id, "digest": digest}
        return cls(_h("proof-sha256:", payload), phase, claim_id, digest)


@dataclass(frozen=True)
class Lifecycle:
    life_id: str
    claim_id: str
    proof_ids: tuple
    phase: str


def advance(proofs: Sequence[Proof]) -> Lifecycle:
    by = {}
    claim = None
    for proof in proofs:
        if proof.phase in by:
            raise PermissionError("duplicate phase proof")
        if claim is None:
            claim = proof.claim_id
        elif claim != proof.claim_id:
            raise PermissionError("cross-claim proof")
        by[proof.phase] = proof
    if "propose" not in by or "admit" not in by:
        raise PermissionError("lifecycle cannot open without propose and admit")
    phase = "admit"
    if "hold" in by:
        phase = "hold"
    if "promote" in by:
        if "hold" not in by:
            raise PermissionError("promote requires hold")
        phase = "promote"
    ids = tuple(by[name].proof_id for name in PHASES if name in by)
    payload = {"claim_id": claim, "proof_ids": ids, "phase": phase}
    return Lifecycle(_h("life-sha256:", payload), claim, ids, phase)


def exit_card(life: Lifecycle) -> dict:
    return card(life.phase in {"hold", "promote"}, life_id=life.life_id, phase=life.phase, claim_id=life.claim_id)
