"""Deterministic momentum mechanic for authored game worlds.

Independent bounded state transition with event identity, replay protection,
monotonic logical clock, validated inputs, and reproducible event receipts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NAME = "momentum"
DOMAIN = "arcane"
MAX_VALUE = 150
INITIAL_VALUE = 46
GAIN = 5
LOSS = 10
DRIFT = 0
LOW_WATERMARK = 21
SCHEMA = "skeleton.game_mechanic.v1"

@dataclass(frozen=True, slots=True)
class State:
    value: int = INITIAL_VALUE
    tick: int = 0
    event_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 0 <= self.value <= MAX_VALUE:
            raise ValueError("value-out-of-range")
        if type(self.tick) is not int or self.tick < 0:
            raise ValueError("invalid-tick")
        if not isinstance(self.event_ids, frozenset):
            raise ValueError("invalid-event-identity-set")
        if any(not isinstance(key, str) or not key or len(key) > 128 for key in self.event_ids):
            raise ValueError("invalid-event-identity")
        if len(self.event_ids) > 10000:
            raise ValueError("identity-capacity")
        if len(self.event_ids) > self.tick:
            raise ValueError("event-tick-inconsistent")

@dataclass(frozen=True, slots=True)
class Receipt:
    event_id: str
    accepted: bool
    reason: str
    before: int
    after: int
    tick: int

def _validate_event(event: dict[str, Any]) -> tuple[str, str, int, int]:
    if type(event) is not dict:
        raise ValueError("invalid-event")
    if set(event) != {"id", "action", "amount", "tick"}:
        raise ValueError("unexpected-event-fields")
    event_id, action = event["id"], event["action"]
    if not isinstance(event_id, str) or not 1 <= len(event_id) <= 128:
        raise ValueError("invalid-event-id")
    if action not in ("gain", "spend", "recover", "decay", "observe"):
        raise ValueError("unknown-action")
    amount, tick = event["amount"], event["tick"]
    if type(amount) is not int or not 0 <= amount <= MAX_VALUE:
        raise ValueError("invalid-amount")
    if type(tick) is not int or tick < 0:
        raise ValueError("invalid-tick")
    return event_id, action, amount, tick

def apply(state: State, event: dict[str, Any]) -> tuple[State, Receipt]:
    if not isinstance(state, State):
        raise TypeError("invalid-state")
    event_id, action, amount, tick = _validate_event(event)
    if event_id in state.event_ids:
        return state, Receipt(event_id, False, "duplicate", state.value, state.value, state.tick)
    if tick <= state.tick:
        return state, Receipt(event_id, False, "nonmonotonic-tick", state.value, state.value, state.tick)
    if len(state.event_ids) >= 10000:
        return state, Receipt(event_id, False, "identity-capacity", state.value, state.value, state.tick)
    if action == "gain":
        change = GAIN + amount
    elif action == "recover":
        change = max(1, (GAIN + amount) // 2)
    elif action == "spend":
        change = -(LOSS + amount)
    elif action == "decay":
        change = -(DRIFT + amount)
    else:
        change = 0
    after = max(0, min(MAX_VALUE, state.value + change))
    updated = State(after, tick, state.event_ids | {event_id})
    return updated, Receipt(event_id, True, "accepted", state.value, after, tick)

def assess(state: State) -> dict[str, Any]:
    if not isinstance(state, State):
        raise TypeError("invalid-state")
    return {
        "schema": SCHEMA, "mechanic": NAME, "domain": DOMAIN,
        "value": state.value, "capacity": MAX_VALUE, "tick": state.tick,
        "low": state.value <= LOW_WATERMARK,
        "saturated": state.value == MAX_VALUE,
        "remaining": MAX_VALUE - state.value,
        "receipt_count": len(state.event_ids),
    }

def replay(events: list[dict[str, Any]], initial: State | None = None) -> tuple[State, tuple[Receipt, ...]]:
    if type(events) is not list or len(events) > 10000:
        raise ValueError("invalid-event-batch")
    state = State() if initial is None else initial
    receipts: list[Receipt] = []
    for event in events:
        state, receipt = apply(state, event)
        receipts.append(receipt)
    return state, tuple(receipts)
