"""Verified native transformer inference boundary witness

Plane: inference_boundary_witness
PR: https://github.com/Apeloff1/Skeleton/pull/3486
Branch: ai/native-runtime-landing-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3486.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3486"
KIND = "inference-boundary"


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
class TokenSpan:
    span_id: str
    prompt_hash: str
    token_ids: tuple
    max_new: int

    @classmethod
    def create(cls, prompt_hash: str, token_ids: Sequence[int], max_new: int):
        _id(prompt_hash, "prompt_hash")
        _u(max_new, "max_new")
        if max_new == 0:
            raise ValueError("max_new must be positive")
        ids = tuple(int(x) for x in token_ids)
        if any(x < 0 for x in ids):
            raise ValueError("token id must be non-negative")
        payload = {"prompt_hash": prompt_hash, "token_ids": ids, "max_new": max_new}
        return cls(_h("span-sha256:", payload), prompt_hash, ids, max_new)


@dataclass(frozen=True)
class BoundaryWitness:
    witness_id: str
    span_id: str
    accepted: int
    mismatch_at: int
    draft_hash: str
    verify_hash: str


def accept_until_mismatch(span: TokenSpan, draft: Sequence[int], verify: Sequence[int]) -> BoundaryWitness:
    d = tuple(int(x) for x in draft)
    v = tuple(int(x) for x in verify)
    if any(x < 0 for x in d + v):
        raise ValueError("token id must be non-negative")
    if len(d) > span.max_new or len(v) > span.max_new:
        raise PermissionError("generation exceeded boundary")
    limit = min(len(d), len(v))
    accepted = 0
    mismatch_at = -1
    for i in range(limit):
        if d[i] != v[i]:
            mismatch_at = i
            break
        accepted += 1
    if mismatch_at < 0 and len(d) != len(v):
        mismatch_at = limit
    payload = {
        "span_id": span.span_id,
        "accepted": accepted,
        "mismatch_at": mismatch_at,
        "draft_hash": _h("draft:", d),
        "verify_hash": _h("verify:", v),
    }
    return BoundaryWitness(
        _h("boundary-sha256:", payload),
        span.span_id,
        accepted,
        mismatch_at,
        payload["draft_hash"],
        payload["verify_hash"],
    )


def exit_card(span: TokenSpan, witness: BoundaryWitness) -> dict:
    hit = witness.mismatch_at < 0
    return card(hit, span_id=span.span_id, witness_id=witness.witness_id, accepted=witness.accepted, mismatch_at=witness.mismatch_at)
