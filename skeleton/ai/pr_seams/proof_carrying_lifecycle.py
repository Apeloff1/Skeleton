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


def card(hit: bool, /, **extra: object) -> dict:
    body = {
        "kind": KIND,
        "hit": bool(hit),
        "law": LAW,
        "citation": CITATION,
        "stored_prose": 0,
    }
    if "stored_prose" in extra and extra["stored_prose"] != 0:
        raise PermissionError("stored prose is forbidden")
    if any(name in extra for name in ("kind", "hit", "law", "citation")):
        raise PermissionError("proof card authority fields are immutable")
    body.update(extra)
    return body

PHASES = ("propose", "admit", "hold", "promote")


@dataclass(frozen=True)
class Proof:
    proof_id: str
    phase: str
    claim_id: str
    digest: str

    def __post_init__(self):
        if self.phase not in PHASES:
            raise ValueError("unknown lifecycle phase")
        _id(self.claim_id, "claim_id")
        _id(self.digest, "digest")
        expected = _h("proof-sha256:", {
            "phase": self.phase, "claim_id": self.claim_id, "digest": self.digest,
        })
        if self.proof_id != expected:
            raise PermissionError("proof identity does not bind lifecycle claim")

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

    def __post_init__(self):
        _id(self.claim_id, "claim_id")
        if self.phase not in PHASES or self.phase == "propose":
            raise PermissionError("invalid lifecycle terminal phase")
        if not isinstance(self.proof_ids, tuple) or len(self.proof_ids) < 2:
            raise PermissionError("lifecycle requires multiple proof identities")
        if len(set(self.proof_ids)) != len(self.proof_ids):
            raise PermissionError("duplicate lifecycle proof identity")
        for proof_id in self.proof_ids:
            if not isinstance(proof_id, str) or not proof_id.startswith("proof-sha256:") or len(proof_id) != 77:
                raise PermissionError("invalid lifecycle proof id")
        expected = _h("life-sha256:", {
            "claim_id": self.claim_id, "proof_ids": self.proof_ids, "phase": self.phase,
        })
        if self.life_id != expected:
            raise PermissionError("lifecycle identity does not bind proofs")


def advance(proofs: Sequence[Proof]) -> Lifecycle:
    by = {}
    claim = None
    for proof in proofs:
        if not isinstance(proof, Proof):
            raise TypeError("Proof required")
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
    if not isinstance(life, Lifecycle):
        raise TypeError("Lifecycle required")
    return card(life.phase in {"hold", "promote"}, life_id=life.life_id, phase=life.phase, claim_id=life.claim_id)
