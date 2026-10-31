"""NPC researcher behavior policy for the academy simulation plane.

Pure deterministic transition with explicit optimistic fencing. Trusted world
evidence must be authenticated by its caller; this code provides no authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA = "skeleton.npc_behavior.v1"
IDENTITY = "academy_researcher"
DOMAIN = "academy"
ROLE = "researcher"
HOME = "home"
PREFERRED_LOCATION = "sanctuary"
SECONDARY_LOCATION = "hall"
ALLOWED_LOCATIONS = ['home','market','outpost','sanctuary','camp','hall']
INITIAL_ENERGY = 60
INITIAL_TRUST = 15
WORK_COST = 8
REST_GAIN = 13
SOCIAL_GAIN = 4
STRESS_STEP = 6
EVENT_CAPACITY = 4096
MAX_EFFORT = 12


@dataclass(frozen=True, slots=True)
class NPCState:
    energy: int = INITIAL_ENERGY
    trust: int = INITIAL_TRUST
    stress: int = 0
    location: str = HOME
    tick: int = 0
    version: int = 0
    event_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        for name in ("energy", "trust", "stress"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError("invalid-" + name)
        if self.location not in ALLOWED_LOCATIONS or type(self.location) is not str:
            raise ValueError("invalid-location")
        if type(self.tick) is not int or self.tick < 0:
            raise ValueError("invalid-tick")
        if type(self.version) is not int or self.version < 0:
            raise ValueError("invalid-version")
        if type(self.event_ids) is not frozenset or len(self.event_ids) > EVENT_CAPACITY:
            raise ValueError("invalid-event-ledger")
        if any(type(key) is not str or not 1 <= len(key) <= 128 for key in self.event_ids):
            raise ValueError("invalid-event-identity")


@dataclass(frozen=True, slots=True)
class BehaviorReceipt:
    event_id: str
    accepted: bool
    reason: str
    before_version: int
    after_version: int
    energy: int
    trust: int
    stress: int
    location: str


def _event(raw: dict[str, Any]) -> tuple[str, str, int, int, int, str, str]:
    if type(raw) is not dict or set(raw) != {
        "id", "action", "effort", "tick", "expected_version", "destination", "witness"
    }:
        raise ValueError("invalid-event-shape")
    identity = raw["id"]
    action = raw["action"]
    effort = raw["effort"]
    tick = raw["tick"]
    version = raw["expected_version"]
    destination = raw["destination"]
    witness = raw["witness"]
    if type(identity) is not str or not 1 <= len(identity) <= 128:
        raise ValueError("invalid-event-id")
    if type(action) is not str or action not in (
        "observe", "work", "rest", "socialize", "travel",
        "retreat", "negotiate", "guard"
    ):
        raise ValueError("unknown-action")
    if type(effort) is not int or not 0 <= effort <= MAX_EFFORT:
        raise ValueError("invalid-effort")
    if type(tick) is not int or tick < 0:
        raise ValueError("invalid-tick")
    if type(version) is not int or version < 0:
        raise ValueError("invalid-expected-version")
    if type(destination) is not str or destination not in ALLOWED_LOCATIONS:
        raise ValueError("invalid-destination")
    if type(witness) is not str or len(witness) > 128:
        raise ValueError("invalid-witness")
    return identity, action, effort, tick, version, destination, witness


def transition(state: NPCState, event: dict[str, Any]) -> tuple[NPCState, BehaviorReceipt]:
    """Apply an NPC action once or reject without modifying the prior state."""
    if type(state) is not NPCState:
        raise TypeError("invalid-npc-state")
    identity, action, effort, tick, version, destination, witness = _event(event)

    def reject(reason: str) -> tuple[NPCState, BehaviorReceipt]:
        return state, BehaviorReceipt(
            identity, False, reason, state.version, state.version,
            state.energy, state.trust, state.stress, state.location
        )

    if identity in state.event_ids:
        return reject("duplicate-event")
    if version != state.version:
        return reject("stale-version")
    if tick <= state.tick:
        return reject("nonmonotonic-tick")
    if len(state.event_ids) >= EVENT_CAPACITY:
        return reject("event-capacity")
    energy, trust, stress, location = (
        state.energy, state.trust, state.stress, state.location
    )
    if action == "work":
        cost = WORK_COST + effort
        if energy < cost:
            return reject("insufficient-energy")
        energy -= cost
        stress = min(100, stress + STRESS_STEP + effort)
    elif action == "guard":
        cost = WORK_COST + 1 + effort
        if energy < cost:
            return reject("insufficient-energy")
        energy -= cost
        stress = min(100, stress + 1 + effort)
    elif action == "rest":
        energy = min(100, energy + REST_GAIN + effort)
        stress = max(0, stress - STRESS_STEP)
    elif action == "socialize":
        if energy == 0:
            return reject("insufficient-energy")
        energy -= 1
        trust = min(100, trust + SOCIAL_GAIN + effort)
    elif action == "travel":
        if energy < 3 + effort:
            return reject("insufficient-energy")
        if destination == location:
            return reject("already-at-destination")
        energy -= 3 + effort
        location = destination
    elif action == "retreat":
        stress = max(0, stress - REST_GAIN - effort)
        trust = max(0, trust - 1)
        location = HOME
    elif action == "negotiate":
        if not witness:
            return reject("missing-witness")
        if energy < 2 + effort:
            return reject("insufficient-energy")
        energy -= 2 + effort
        trust = min(100, trust + SOCIAL_GAIN + 2)
    # Observe is a zero-resource, still-ledgered world observation.
    next_state = NPCState(
        energy, trust, stress, location, tick, state.version + 1,
        state.event_ids | {identity},
    )
    receipt = BehaviorReceipt(
        identity, True, "accepted", state.version, next_state.version,
        energy, trust, stress, location,
    )
    return next_state, receipt


def snapshot(state: NPCState) -> dict[str, Any]:
    if type(state) is not NPCState:
        raise TypeError("invalid-npc-state")
    return {
        "schema": SCHEMA, "identity": IDENTITY, "role": ROLE, "domain": DOMAIN,
        "energy": state.energy, "trust": state.trust, "stress": state.stress,
        "location": state.location, "tick": state.tick, "version": state.version,
        "exhausted": state.energy < WORK_COST,
        "distressed": state.stress >= 80, "trusted": state.trust >= 70,
        "ledger_size": len(state.event_ids),
    }


def replay(
    events: list[dict[str, Any]], initial: NPCState | None = None
) -> tuple[NPCState, tuple[BehaviorReceipt, ...]]:
    if type(events) is not list or len(events) > EVENT_CAPACITY:
        raise ValueError("invalid-replay-batch")
    state = NPCState() if initial is None else initial
    receipts: list[BehaviorReceipt] = []
    for event in events:
        state, receipt = transition(state, event)
        receipts.append(receipt)
    return state, tuple(receipts)
