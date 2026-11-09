"""Pure optimistic, evidence-gated dialogue director: civic_hearing."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

SCENE = "civic_hearing"
STAGES = ("greet", "ask", "explain", "negotiate", "reconcile", "close")
MIN_TRUST = 20
TRUST_GAIN = 3
TENSION_GAIN = 4
MAX_TURNS = 16
MAX_EVENTS = 256

@dataclass(frozen=True)
class State:
    stage: int = 0
    trust: int = 25
    tension: int = 10
    version: int = 0
    status: str = "active"
    receipts: frozenset[str] = field(default_factory=frozenset)
    evidence: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self):
        if type(self.stage) is not int or not 0 <= self.stage <= len(STAGES):
            raise ValueError("stage")
        if any(type(n) is not int or not 0 <= n <= 100 for n in (self.trust, self.tension)):
            raise ValueError("scores")
        if type(self.version) is not int or not 0 <= self.version <= MAX_EVENTS:
            raise ValueError("version")
        if self.status not in ("active", "resolved", "withdrawn", "failed"):
            raise ValueError("status")
        if self.status == "active" and self.stage == len(STAGES):
            raise ValueError("terminal-stage")
        if self.status == "resolved" and self.stage != len(STAGES):
            raise ValueError("premature-resolution")
        if type(self.receipts) is not frozenset or type(self.evidence) is not frozenset:
            raise ValueError("ledger")
        if any(type(x) is not str or not 1 <= len(x) <= 128 for x in self.receipts | self.evidence):
            raise ValueError("invalid-ledger-id")

@dataclass(frozen=True)
class Receipt:
    id: str
    accepted: bool
    reason: str
    before: int
    after: int
    status: str

def choose(state: State, command: dict[str, Any]) -> tuple[State, Receipt]:
    if type(state) is not State:
        raise TypeError("state")
    if type(command) is not dict or set(command) != {"id", "choice", "expected_version", "evidence"}:
        raise ValueError("command-shape")
    key, choice, ver, proof = (command[k] for k in ("id", "choice", "expected_version", "evidence"))
    if type(key) is not str or not 1 <= len(key) <= 128:
        raise ValueError("id")
    if type(choice) is not str or choice not in STAGES + ("withdraw",):
        raise ValueError("choice")
    if type(ver) is not int or ver < 0:
        raise ValueError("version")
    if type(proof) is not str or len(proof) > 128:
        raise ValueError("evidence")
    def reject(reason):
        return state, Receipt(key, False, reason, state.version, state.version, state.status)
    if key in state.receipts:
        return reject("replay")
    if ver != state.version:
        return reject("stale")
    if state.status != "active":
        return reject("terminal")
    if len(state.receipts) >= MAX_EVENTS or state.version >= MAX_TURNS:
        return reject("capacity")
    if choice == "withdraw":
        next_state = State(state.stage, state.trust, state.tension, ver + 1, "withdrawn", state.receipts | {key}, state.evidence)
        return next_state, Receipt(key, True, "withdrawn", ver, ver + 1, "withdrawn")
    if choice != STAGES[state.stage]:
        return reject("stage-order")
    if choice in ("explain", "negotiate") and not proof:
        return reject("proof-required")
    if proof and proof in state.evidence:
        return reject("proof-replayed")
    if choice == "negotiate" and state.trust < MIN_TRUST:
        return reject("rapport-gate")
    trust = min(100, state.trust + (TRUST_GAIN if choice != "close" else 0))
    tension = min(100, state.tension + (TENSION_GAIN if choice == "negotiate" else 1))
    stage = state.stage + 1
    status = "resolved" if stage == len(STAGES) else "failed" if tension >= 95 else "active"
    next_state = State(stage, trust, tension, ver + 1, status, state.receipts | {key}, state.evidence | ({proof} if proof else set()))
    return next_state, Receipt(key, True, "accepted", ver, ver + 1, status)

def replay(commands: list[dict[str, Any]], initial: State | None = None):
    if type(commands) is not list or len(commands) > MAX_EVENTS:
        raise ValueError("batch")
    state = State() if initial is None else initial
    receipts = []
    for command in commands:
        state, receipt = choose(state, command)
        receipts.append(receipt)
    return state, tuple(receipts)

def snapshot(state: State):
    if type(state) is not State:
        raise TypeError("state")
    return {"schema": "skeleton.dialogue.v1", "scene": SCENE, "stage": state.stage,
            "choice": STAGES[state.stage] if state.status == "active" else None,
            "trust": state.trust, "tension": state.tension, "version": state.version,
            "status": state.status, "receipt_count": len(state.receipts)}
