"""Version-fenced raid warning regional world event.

The director owns one world-instance-local event lifecycle. It does not
authenticate its caller, persist world state, or issue privilege grants.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EVENT_ID = "security_raid_warning"
DOMAIN = "security"
SCHEMA = "skeleton.world_event.v1"
SENSOR = "pressure"
TRIGGER_THRESHOLD = 16
RESOLUTION_COST = 6
RESOLUTION_GAIN = 17
COOLDOWN_TICKS = 7
SEVERITY = 1
MAX_IDS = 4096
ALLOWED_REGIONS = ("north", "south", "east", "west", "central")


@dataclass(frozen=True, slots=True)
class State:
    region: str = "central"
    lifecycle: str = "idle"
    pressure: int = 40
    resources: int = 60
    resilience: int = 50
    active_id: str = ""
    cooldown_until: int = 0
    tick: int = 0
    version: int = 0
    event_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if type(self.region) is not str or self.region not in ALLOWED_REGIONS:
            raise ValueError("invalid-region")
        if type(self.lifecycle) is not str or self.lifecycle not in (
            "idle", "active", "cooldown"
        ):
            raise ValueError("invalid-lifecycle")
        for field_name in ("pressure", "resources", "resilience"):
            value = getattr(self, field_name)
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError("invalid-" + field_name)
        if type(self.active_id) is not str or len(self.active_id) > 128:
            raise ValueError("invalid-active-id")
        if (self.lifecycle == "active") != bool(self.active_id):
            raise ValueError("active-id-lifecycle-mismatch")
        if type(self.cooldown_until) is not int or self.cooldown_until < 0:
            raise ValueError("invalid-cooldown")
        if type(self.tick) is not int or self.tick < 0:
            raise ValueError("invalid-tick")
        if type(self.version) is not int or self.version < 0:
            raise ValueError("invalid-version")
        if type(self.event_ids) is not frozenset or len(self.event_ids) > MAX_IDS:
            raise ValueError("invalid-event-ledger")
        if any(type(key) is not str or not 1 <= len(key) <= 128 for key in self.event_ids):
            raise ValueError("invalid-event-identity")


@dataclass(frozen=True, slots=True)
class Receipt:
    event_id: str
    accepted: bool
    reason: str
    before_version: int
    after_version: int
    lifecycle: str
    resources: int
    resilience: int


def _parse(command: dict[str, Any]) -> tuple[str, str, int, int, int, str]:
    if type(command) is not dict or set(command) != {
        "id", "action", "tick", "expected_version", "intensity", "evidence"
    }:
        raise ValueError("invalid-command-shape")
    identity = command["id"]
    action = command["action"]
    tick = command["tick"]
    version = command["expected_version"]
    intensity = command["intensity"]
    evidence = command["evidence"]
    if type(identity) is not str or not 1 <= len(identity) <= 128:
        raise ValueError("invalid-event-id")
    if type(action) is not str or action not in (
        "activate", "resolve", "abort", "release_cooldown", "observe"
    ):
        raise ValueError("unknown-action")
    if type(tick) is not int or tick < 0:
        raise ValueError("invalid-tick")
    if type(version) is not int or version < 0:
        raise ValueError("invalid-expected-version")
    if type(intensity) is not int or not 0 <= intensity <= 20:
        raise ValueError("invalid-intensity")
    if type(evidence) is not str or len(evidence) > 128:
        raise ValueError("invalid-evidence")
    return identity, action, tick, version, intensity, evidence


def transition(state: State, command: dict[str, Any]) -> tuple[State, Receipt]:
    """Reject invalid transitions without mutating the input state."""
    if type(state) is not State:
        raise TypeError("invalid-state")
    identity, action, tick, version, intensity, evidence = _parse(command)

    def reject(reason: str) -> tuple[State, Receipt]:
        return state, Receipt(
            identity, False, reason, state.version, state.version,
            state.lifecycle, state.resources, state.resilience
        )

    if identity in state.event_ids:
        return reject("duplicate-event")
    if version != state.version:
        return reject("stale-version")
    if tick <= state.tick:
        return reject("nonmonotonic-tick")
    if len(state.event_ids) >= MAX_IDS:
        return reject("event-ledger-capacity")
    if action == "observe":
        return reject("observation-readonly")

    lifecycle = state.lifecycle
    pressure, resources, resilience = (
        state.pressure, state.resources, state.resilience
    )
    active_id, until = state.active_id, state.cooldown_until
    reason = "accepted"

    if action == "activate":
        if lifecycle != "idle":
            return reject("event-not-idle")
        if pressure + intensity < TRIGGER_THRESHOLD:
            return reject("trigger-threshold-not-met")
        if resources < RESOLUTION_COST:
            return reject("activation-resource-shortage")
        active_id = identity
        lifecycle = "active"
        pressure = min(100, pressure + intensity + SEVERITY)
        reason = "activated"
    elif action == "resolve":
        if lifecycle != "active":
            return reject("event-not-active")
        if not evidence:
            return reject("resolution-evidence-missing")
        required = RESOLUTION_COST + intensity
        if resources < required:
            return reject("resolution-resource-shortage")
        resources -= required
        resilience = min(100, resilience + RESOLUTION_GAIN + intensity)
        pressure = max(0, pressure - RESOLUTION_GAIN - intensity)
        active_id = ""
        until = tick + COOLDOWN_TICKS
        lifecycle = "cooldown"
        reason = "resolved"
    elif action == "abort":
        if lifecycle != "active":
            return reject("event-not-active")
        active_id = ""
        pressure = min(100, pressure + SEVERITY)
        until = tick + COOLDOWN_TICKS
        lifecycle = "cooldown"
        reason = "aborted"
    elif action == "release_cooldown":
        if lifecycle != "cooldown":
            return reject("not-in-cooldown")
        if tick < until:
            return reject("cooldown-not-expired")
        until = 0
        lifecycle = "idle"
        reason = "ready"

    updated = State(
        state.region, lifecycle, pressure, resources, resilience, active_id,
        until, tick, state.version + 1, state.event_ids | {identity}
    )
    return updated, Receipt(
        identity, True, reason, state.version, updated.version,
        lifecycle, resources, resilience
    )


def snapshot(state: State) -> dict[str, Any]:
    if type(state) is not State:
        raise TypeError("invalid-state")
    return {
        "schema": SCHEMA, "world_event": EVENT_ID, "domain": DOMAIN,
        "region": state.region, "sensor": SENSOR,
        "threshold": TRIGGER_THRESHOLD, "severity": SEVERITY,
        "pressure": state.pressure, "resources": state.resources,
        "resilience": state.resilience, "lifecycle": state.lifecycle,
        "active_id": state.active_id, "cooldown_until": state.cooldown_until,
        "tick": state.tick, "version": state.version,
        "event_count": len(state.event_ids)
    }


def replay(
    commands: list[dict[str, Any]], initial: State | None = None
) -> tuple[State, tuple[Receipt, ...]]:
    if type(commands) is not list or len(commands) > MAX_IDS:
        raise ValueError("invalid-replay-batch")
    state = State() if initial is None else initial
    receipts: list[Receipt] = []
    for command in commands:
        state, receipt = transition(state, command)
        receipts.append(receipt)
    return state, tuple(receipts)
