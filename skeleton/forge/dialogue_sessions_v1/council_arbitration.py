"""Immutable optimistic dialogue state machine for council_arbitration."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

SCENE = "council_arbitration"
BEATS = ("introduce", "listen", "reveal", "propose", "agree", "leave")
RAPPORT_GATE = 25
RAPPORT_GAIN = 5
TENSION_COST = 4
MAX_EVENTS = 256
MAX_TURNS = 16

@dataclass(frozen=True, slots=True)
class State:
    beat: int = 0
    rapport: int = 25
    tension: int = 12
    version: int = 0
    status: str = "active"
    ids: frozenset[str] = field(default_factory=frozenset)
    proofs: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self):
        if type(self.beat) is not int or not 0 <= self.beat <= len(BEATS):
            raise ValueError("beat")
        if type(self.rapport) is not int or not 0 <= self.rapport <= 100:
            raise ValueError("rapport")
        if type(self.tension) is not int or not 0 <= self.tension <= 100:
            raise ValueError("tension")
        if type(self.version) is not int or not 0 <= self.version <= MAX_EVENTS:
            raise ValueError("version")
        if self.status not in ("active", "resolved", "withdrawn", "failed"):
            raise ValueError("status")
        if self.status == "active" and self.beat == len(BEATS):
            raise ValueError("active-after-end")
        if self.status == "resolved" and self.beat != len(BEATS):
            raise ValueError("premature-resolution")
        if type(self.ids) is not frozenset or type(self.proofs) is not frozenset:
            raise ValueError("ledger")
        if len(self.ids) > MAX_EVENTS:
            raise ValueError("capacity")
        if any(type(x) is not str or not 1 <= len(x) <= 128 for x in self.ids | self.proofs):
            raise ValueError("invalid-id")

@dataclass(frozen=True, slots=True)
class Receipt:
    id: str
    accepted: bool
    reason: str
    version_before: int
    version_after: int
    status: str

def advance(state: State, cmd: dict[str, Any]) -> tuple[State, Receipt]:
    if type(state) is not State:
        raise TypeError("state")
    if type(cmd) is not dict or set(cmd) != {"id", "choice", "version", "evidence"}:
        raise ValueError("shape")
    key, choice, ver, proof = (cmd[x] for x in ("id", "choice", "version", "evidence"))
    if type(key) is not str or not 1 <= len(key) <= 128:
        raise ValueError("id")
    if type(choice) is not str or choice not in BEATS + ("withdraw",):
        raise ValueError("choice")
    if type(ver) is not int or ver < 0:
        raise ValueError("version")
    if type(proof) is not str or len(proof) > 128:
        raise ValueError("evidence")
    def reject(reason):
        return state, Receipt(key, False, reason, state.version, state.version, state.status)
    if key in state.ids:
        return reject("duplicate")
    if ver != state.version:
        return reject("stale")
    if state.status != "active":
        return reject("terminal")
    if ver >= MAX_TURNS or len(state.ids) >= MAX_EVENTS:
        return reject("capacity")
    if choice == "withdraw":
        next_state = State(state.beat, state.rapport, state.tension, ver+1, "withdrawn", state.ids | {key}, state.proofs)
        return next_state, Receipt(key, True, "withdrawn", ver, next_state.version, next_state.status)
    if choice != BEATS[state.beat]:
        return reject("out-of-order")
    if choice in ("reveal", "propose") and not proof:
        return reject("proof-required")
    if proof and proof in state.proofs:
        return reject("proof-used")
    if choice == "propose" and state.rapport < RAPPORT_GATE:
        return reject("rapport-low")
    new_rapport = min(100, state.rapport + (RAPPORT_GAIN if choice != "leave" else 0))
    new_tension = min(100, state.tension + (TENSION_COST if choice == "propose" else 1))
    beat = state.beat + 1
    status = "resolved" if beat == len(BEATS) else "failed" if new_tension >= 95 else "active"
    next_state = State(beat, new_rapport, new_tension, ver+1, status, state.ids | {key}, state.proofs | ({proof} if proof else set()))
    return next_state, Receipt(key, True, "accepted", ver, next_state.version, status)

def replay(commands: list[dict[str, Any]], initial: State | None = None):
    if type(commands) is not list or len(commands) > MAX_EVENTS:
        raise ValueError("batch")
    state = State() if initial is None else initial
    receipts = []
    for command in commands:
        state, receipt = advance(state, command)
        receipts.append(receipt)
    return state, tuple(receipts)

def snapshot(state: State):
    if type(state) is not State:
        raise TypeError("state")
    return {"schema": "skeleton.dialogue.v1", "scene": SCENE, "beat": state.beat,
            "next": BEATS[state.beat] if state.status == "active" else None,
            "rapport": state.rapport, "tension": state.tension,
            "version": state.version, "status": state.status}
