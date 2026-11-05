"""Evidence-gated commerce_contract dialogue simulation with replay-safe receipts."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

SCENE = "commerce_contract"
BEATS = ("opening", "question", "disclosure", "offer", "agreement", "departure")
MIN_RAPPORT = 23
RAPPORT_GAIN = 5
STRESS_GAIN = 3
MAX_EVENTS = 256
MAX_TURNS = 16

@dataclass(frozen=True, slots=True)
class State:
    beat: int = 0
    rapport: int = 25
    stress: int = 10
    version: int = 0
    status: str = "active"
    identities: frozenset[str] = field(default_factory=frozenset)
    proofs: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self):
        if type(self.beat) is not int or not 0 <= self.beat <= len(BEATS):
            raise ValueError("beat")
        if type(self.rapport) is not int or not 0 <= self.rapport <= 100:
            raise ValueError("rapport")
        if type(self.stress) is not int or not 0 <= self.stress <= 100:
            raise ValueError("stress")
        if type(self.version) is not int or not 0 <= self.version <= MAX_EVENTS:
            raise ValueError("version")
        if self.status not in ("active", "resolved", "withdrawn", "failed"):
            raise ValueError("status")
        if self.status == "active" and self.beat == len(BEATS):
            raise ValueError("active-beat")
        if self.status == "resolved" and self.beat != len(BEATS):
            raise ValueError("resolved-beat")
        if type(self.identities) is not frozenset or type(self.proofs) is not frozenset:
            raise ValueError("ledgers")
        if any(type(k) is not str or not 1 <= len(k) <= 128 for k in self.identities | self.proofs):
            raise ValueError("ledger-key")
        if len(self.identities) > MAX_EVENTS:
            raise ValueError("identity-capacity")

@dataclass(frozen=True, slots=True)
class Receipt:
    identity: str
    accepted: bool
    reason: str
    old_version: int
    new_version: int
    stage: int
    status: str

def apply(state: State, command: dict[str, Any]) -> tuple[State, Receipt]:
    if type(state) is not State:
        raise TypeError("state")
    if type(command) is not dict or set(command) != {"id", "choice", "version", "proof"}:
        raise ValueError("command-shape")
    key, choice, version, proof = (command[k] for k in ("id", "choice", "version", "proof"))
    if type(key) is not str or not 1 <= len(key) <= 128:
        raise ValueError("event-id")
    if type(choice) is not str or choice not in BEATS + ("withdraw",):
        raise ValueError("choice")
    if type(version) is not int or version < 0:
        raise ValueError("version")
    if type(proof) is not str or len(proof) > 128:
        raise ValueError("proof")
    def reject(reason: str):
        return state, Receipt(key, False, reason, state.version, state.version, state.beat, state.status)
    if key in state.identities:
        return reject("duplicate")
    if version != state.version:
        return reject("stale")
    if state.status != "active":
        return reject("terminal")
    if state.version >= MAX_TURNS or len(state.identities) >= MAX_EVENTS:
        return reject("capacity")
    if choice == "withdraw":
        nxt = State(state.beat, state.rapport, state.stress, version+1, "withdrawn", state.identities | {key}, state.proofs)
        return nxt, Receipt(key, True, "withdrawn", version, nxt.version, nxt.beat, nxt.status)
    if choice != BEATS[state.beat]:
        return reject("out-of-order")
    if choice in ("disclosure", "offer") and not proof:
        return reject("proof-required")
    if proof and proof in state.proofs:
        return reject("proof-reused")
    if choice == "offer" and state.rapport < MIN_RAPPORT:
        return reject("rapport")
    rapport = min(100, state.rapport + (RAPPORT_GAIN if choice != "departure" else 0))
    stress = min(100, state.stress + (STRESS_GAIN if choice == "offer" else 1))
    beat = state.beat + 1
    status = "resolved" if beat == len(BEATS) else "failed" if stress >= 90 else "active"
    nxt = State(beat, rapport, stress, version+1, status, state.identities | {key}, state.proofs | ({proof} if proof else set()))
    return nxt, Receipt(key, True, "accepted", version, nxt.version, beat, status)

def replay(commands: list[dict[str, Any]], initial: State | None = None):
    if type(commands) is not list or len(commands) > MAX_EVENTS:
        raise ValueError("batch")
    state = State() if initial is None else initial
    receipts = []
    for command in commands:
        state, receipt = apply(state, command)
        receipts.append(receipt)
    return state, tuple(receipts)

def snapshot(state: State):
    if type(state) is not State:
        raise TypeError("state")
    return {"schema": "skeleton.dialogue.v1", "scene": SCENE, "beat": state.beat,
            "next": BEATS[state.beat] if state.status == "active" else None,
            "rapport": state.rapport, "stress": state.stress,
            "status": state.status, "version": state.version}
