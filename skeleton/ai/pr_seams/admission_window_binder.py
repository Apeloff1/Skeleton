"""Deterministic admission window binder for the runtime scheduler

Plane: admission_window_binder
PR: https://github.com/Apeloff1/Skeleton/pull/3487
Branch: ai/runtime-admission-scheduler-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3487.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3487"
KIND = "admission-window"


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

PARTICIPANTS = ("schedule", "resources", "ownership", "authorization")


@dataclass(frozen=True)
class Window:
    window_id: str
    workflow_id: str
    step_id: str
    generation: int
    open_ns: int
    close_ns: int
    quota: int

    @classmethod
    def create(cls, workflow_id, step_id, generation, open_ns, close_ns, quota):
        _id(workflow_id, "workflow_id")
        _id(step_id, "step_id")
        _u(generation, "generation")
        _u(open_ns, "open_ns")
        _u(close_ns, "close_ns")
        _u(quota, "quota")
        if close_ns <= open_ns:
            raise ValueError("window must be open before it closes")
        if quota == 0:
            raise ValueError("quota must be positive")
        payload = {
            "workflow_id": workflow_id,
            "step_id": step_id,
            "generation": generation,
            "open_ns": open_ns,
            "close_ns": close_ns,
            "quota": quota,
        }
        return cls(_h("window-sha256:", payload), workflow_id, step_id, generation, open_ns, close_ns, quota)


@dataclass(frozen=True)
class Bid:
    bid_id: str
    window_id: str
    participant: str
    rank: int
    mass: int
    evidence_id: str

    @classmethod
    def create(cls, window: Window, participant: str, rank: int, mass: int, evidence_id: str):
        if participant not in PARTICIPANTS:
            raise ValueError("unknown admission participant")
        _u(rank, "rank")
        _u(mass, "mass")
        _id(evidence_id, "evidence_id")
        if mass == 0 or mass > window.quota:
            raise PermissionError("bid mass outside window quota")
        payload = {
            "window_id": window.window_id,
            "participant": participant,
            "rank": rank,
            "mass": mass,
            "evidence_id": evidence_id,
        }
        return cls(_h("bid-sha256:", payload), window.window_id, participant, rank, mass, evidence_id)


@dataclass(frozen=True)
class Grant:
    grant_id: str
    window_id: str
    bid_ids: tuple
    admitted_mass: int
    residual: int


def bind(window: Window, bids: Sequence[Bid], now_ns: int) -> Grant:
    _u(now_ns, "now_ns")
    if now_ns < window.open_ns or now_ns >= window.close_ns:
        raise PermissionError("bid outside admission window")
    seen = {}
    for bid in bids:
        if bid.window_id != window.window_id:
            raise PermissionError("foreign window bid")
        prev = seen.get(bid.participant)
        if prev is not None and prev != bid:
            raise PermissionError("conflicting participant bid")
        seen[bid.participant] = bid
    if set(seen) != set(PARTICIPANTS):
        raise PermissionError("admission window is not fully bid")
    ordered = tuple(sorted(seen.values(), key=lambda b: (b.rank, b.participant)))
    admitted = 0
    chosen = []
    for bid in ordered:
        if admitted + bid.mass > window.quota:
            continue
        chosen.append(bid.bid_id)
        admitted += bid.mass
    if admitted == 0:
        raise PermissionError("no feasible admission under quota")
    payload = {
        "window_id": window.window_id,
        "bid_ids": tuple(chosen),
        "admitted_mass": admitted,
        "residual": window.quota - admitted,
    }
    return Grant(_h("grant-sha256:", payload), window.window_id, tuple(chosen), admitted, window.quota - admitted)


def exit_card(window: Window, grant: Grant) -> dict:
    return card(
        True,
        window_id=window.window_id,
        grant_id=grant.grant_id,
        admitted_mass=grant.admitted_mass,
        residual=grant.residual,
        reference={"title": "runtime-admission-scheduler", "era": "2026-10-07", "citation": CITATION, "url": CITATION},
    )
