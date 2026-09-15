"""Canonical event/memory projection for the promoted aquarium policy.

The aquarium domain stays in :mod:`skeleton.frontier.aquarium`. This module only
connects that canonical state to the existing frontier ``DomainEvent`` and
memory-item boundaries; it does not introduce a second aquarium model,
persistence layer, event bus, or memory store.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence

from skeleton.frontier.aquarium import (
    AquariumPosition,
    AquariumState,
    AquariumTankState,
    DisplayFish,
    PlacedDecoration,
)
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.events import DomainEvent

_ALLOWED_ACTIONS = frozenset(
    {
        "fish_added",
        "fish_removed",
        "decoration_placed",
        "tank_purchased",
        "theme_changed",
        "visit_recorded",
        "like_recorded",
    }
)
_HEX = frozenset("0123456789abcdef")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be non-empty and normalized")
    return value


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _finite_nonnegative(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"{field_name} must be finite and nonnegative")
    return numeric


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return value


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    return value


def _sha256(value: object, field_name: str) -> str:
    digest = _text(value, field_name)
    if len(digest) != 64 or any(character not in _HEX for character in digest):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return digest


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


def _time_from_text(value: object, field_name: str) -> datetime:
    raw = _text(value, field_name)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601") from exc
    return _aware(parsed, field_name)


def _position_payload(position: AquariumPosition) -> dict[str, int]:
    if not isinstance(position, AquariumPosition):
        raise TypeError("position must be AquariumPosition")
    return position.as_dict()


def _fish_payload(fish: DisplayFish) -> dict[str, object]:
    return {
        "id": fish.id,
        "name": fish.name,
        "species": fish.species,
        "size": fish.size,
        "color": fish.color,
        "traits": dict(fish.traits),
        "position": _position_payload(fish.position),
        "added_at": fish.added_at.astimezone(timezone.utc).isoformat(),
    }


def _decoration_payload(decoration: PlacedDecoration) -> dict[str, object]:
    return {
        "id": decoration.id,
        "decoration_id": decoration.decoration_id,
        "name": decoration.name,
        "icon": decoration.icon,
        "position": _position_payload(decoration.position),
        "placed_at": decoration.placed_at.astimezone(timezone.utc).isoformat(),
    }


def aquarium_state_payload(state: AquariumState) -> dict[str, object]:
    if not isinstance(state, AquariumState):
        raise TypeError("state must be AquariumState")
    return {
        "tanks": {
            tank_id: {
                "tank_id": tank.tank_id,
                "fish": [_fish_payload(fish) for fish in tank.fish],
                "decorations": [_decoration_payload(item) for item in tank.decorations],
                "theme": tank.theme,
                "background": tank.background,
            }
            for tank_id, tank in sorted(state.tanks.items())
        },
        "owned_tanks": sorted(state.owned_tanks),
        "owned_decorations": dict(sorted(state.owned_decorations.items())),
        "visitors": state.visitors,
        "likes": state.likes,
    }


def aquarium_identity(subject_id: str) -> str:
    subject = _text(subject_id, "aquarium subject_id")
    return stable_content_digest({"surface": "aquarium", "subject_id": subject})


def aquarium_state_digest(state: AquariumState) -> str:
    return stable_content_digest(aquarium_state_payload(state))


def aquarium_event(
    state: AquariumState,
    *,
    subject_id: str,
    action: str,
    occurred_at: datetime,
) -> DomainEvent:
    subject = _text(subject_id, "aquarium subject_id")
    normalized_action = _text(action, "aquarium action").lower()
    if normalized_action not in _ALLOWED_ACTIONS:
        raise ValueError(f"unsupported aquarium action: {normalized_action}")
    occurred = _aware(occurred_at, "aquarium occurred_at")
    payload = aquarium_state_payload(state)
    payload.update(
        {
            "subject_id": subject,
            "aquarium_identity_sha256": aquarium_identity(subject),
            "aquarium_state_sha256": aquarium_state_digest(state),
        }
    )
    return DomainEvent(
        topic=f"aquarium.{normalized_action}",
        payload=payload,
        occurred_at=occurred,
    )


def _position_from_payload(value: object, field_name: str) -> AquariumPosition:
    position = _mapping(value, field_name)
    return AquariumPosition(
        x=_nonnegative_int(position.get("x"), f"{field_name} x"),
        y=_nonnegative_int(position.get("y"), f"{field_name} y"),
    )


def _fish_from_payload(value: object) -> DisplayFish:
    raw = _mapping(value, "aquarium fish payload")
    traits = _mapping(raw.get("traits", {}), "aquarium fish traits")
    return DisplayFish(
        id=_text(raw.get("id"), "aquarium fish id"),
        name=_text(raw.get("name"), "aquarium fish name"),
        species=_text(raw.get("species"), "aquarium fish species"),
        size=_finite_nonnegative(raw.get("size"), "aquarium fish size"),
        color=_text(raw.get("color"), "aquarium fish color"),
        traits=dict(traits),
        position=_position_from_payload(raw.get("position"), "aquarium fish position"),
        added_at=_time_from_text(raw.get("added_at"), "aquarium fish added_at"),
    )


def _decoration_from_payload(value: object) -> PlacedDecoration:
    raw = _mapping(value, "aquarium decoration payload")
    icon = raw.get("icon", "")
    if not isinstance(icon, str):
        raise TypeError("aquarium decoration icon must be a string")
    return PlacedDecoration(
        id=_text(raw.get("id"), "placed decoration id"),
        decoration_id=_text(raw.get("decoration_id"), "decoration id"),
        name=_text(raw.get("name"), "placed decoration name"),
        icon=icon,
        position=_position_from_payload(raw.get("position"), "decoration position"),
        placed_at=_time_from_text(raw.get("placed_at"), "decoration placed_at"),
    )


def _state_from_payload(payload: Mapping[str, object]) -> AquariumState:
    raw_tanks = _mapping(payload.get("tanks"), "aquarium tanks")
    tanks: dict[str, AquariumTankState] = {}
    for raw_key, raw_tank_value in raw_tanks.items():
        tank_id = _text(raw_key, "aquarium tank key")
        raw_tank = _mapping(raw_tank_value, "aquarium tank payload")
        fish = tuple(
            _fish_from_payload(item)
            for item in _sequence(raw_tank.get("fish", ()), "aquarium fish")
        )
        decorations = tuple(
            _decoration_from_payload(item)
            for item in _sequence(raw_tank.get("decorations", ()), "aquarium decorations")
        )
        tanks[tank_id] = AquariumTankState(
            tank_id=_text(raw_tank.get("tank_id"), "aquarium tank id"),
            fish=fish,
            decorations=decorations,
            theme=_text(raw_tank.get("theme"), "aquarium tank theme"),
            background=_optional_text(raw_tank.get("background"), "aquarium tank background"),
        )

    owned_raw = _sequence(payload.get("owned_tanks"), "aquarium owned_tanks")
    owned_tanks = frozenset(_text(item, "aquarium owned tank id") for item in owned_raw)
    inventory_raw = _mapping(payload.get("owned_decorations", {}), "aquarium owned decorations")
    inventory: dict[str, int] = {}
    for raw_key, raw_count in inventory_raw.items():
        key = _text(raw_key, "aquarium decoration inventory id")
        inventory[key] = _nonnegative_int(
            raw_count, f"aquarium decoration inventory count for {key}"
        )

    return AquariumState(
        tanks=tanks,
        owned_tanks=owned_tanks,
        owned_decorations=inventory,
        visitors=_nonnegative_int(payload.get("visitors"), "aquarium visitors"),
        likes=_nonnegative_int(payload.get("likes"), "aquarium likes"),
    )


def aquarium_event_to_memory_item(event: DomainEvent) -> Mapping[str, Any]:
    if event.topic not in {f"aquarium.{action}" for action in _ALLOWED_ACTIONS}:
        raise ValueError("expected an aquarium transition event")
    occurred = _aware(event.occurred_at, "aquarium event occurred_at")
    payload = _mapping(event.payload, "aquarium event payload")

    subject = _text(payload.get("subject_id"), "aquarium subject_id")
    identity = _sha256(payload.get("aquarium_identity_sha256"), "aquarium_identity_sha256")
    if identity != aquarium_identity(subject):
        raise ValueError("aquarium event identity digest mismatch")

    expected_digest = _sha256(payload.get("aquarium_state_sha256"), "aquarium_state_sha256")
    state = _state_from_payload(payload)
    if aquarium_state_digest(state) != expected_digest:
        raise ValueError("aquarium event state digest mismatch")

    action = event.topic.removeprefix("aquarium.")
    return {
        "id": identity,
        "content": f"aquarium {action} {state.total_fish_displayed} fish",
        "metadata": {
            "subject_id": subject,
            "aquarium_identity_sha256": identity,
            "aquarium_state_sha256": expected_digest,
            "aquarium_action": action,
            "tank_count": len(state.tanks),
            "fish_count": state.total_fish_displayed,
            "decoration_count": state.total_decorations_placed,
            "visitors": state.visitors,
            "likes": state.likes,
            "occurred_at": occurred.isoformat(),
        },
    }


def aquarium_state_memory_item(state: AquariumState, *, subject_id: str) -> Mapping[str, Any]:
    subject = _text(subject_id, "aquarium subject_id")
    identity = aquarium_identity(subject)
    digest = aquarium_state_digest(state)
    return {
        "id": identity,
        "content": f"aquarium state {state.total_fish_displayed} fish",
        "metadata": {
            "subject_id": subject,
            "aquarium_identity_sha256": identity,
            "aquarium_state_sha256": digest,
            "tank_count": len(state.tanks),
            "fish_count": state.total_fish_displayed,
            "decoration_count": state.total_decorations_placed,
            "visitors": state.visitors,
            "likes": state.likes,
        },
    }
