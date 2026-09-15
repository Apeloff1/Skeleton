"""Event and memory adapters for the promoted aquarium policy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from skeleton.frontier.aquarium_models import AquariumPosition, DisplayFish, aware, count, counts, text
from skeleton.frontier.aquarium_state import AquariumState, AquariumTankState, PlacedDecoration
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.events import DomainEvent

_ALLOWED_ACTIONS = frozenset(
    {"fish_added", "fish_removed", "decoration_placed", "tank_purchased", "theme_changed"}
)
_HEX = frozenset("0123456789abcdef")


def _sha256(value: object, field_name: str) -> str:
    digest = text(value, field_name)
    if len(digest) != 64 or any(character not in _HEX for character in digest):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return digest


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    return value


def _optional_time(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be an ISO-8601 string or null")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601") from exc
    return aware(parsed, field_name)


def _position_payload(position: AquariumPosition) -> dict[str, int]:
    return {"x": position.x, "y": position.y}


def _fish_payload(fish: DisplayFish) -> dict[str, object]:
    return {
        "id": fish.id,
        "name": fish.name,
        "species": fish.species,
        "size": fish.size,
        "position": _position_payload(fish.position),
        "traits": dict(fish.traits),
        "color": fish.color,
        "added_at": fish.added_at.isoformat() if fish.added_at is not None else None,
    }


def _decoration_payload(decoration: PlacedDecoration) -> dict[str, object]:
    return {
        "id": decoration.id,
        "decoration_id": decoration.decoration_id,
        "name": decoration.name,
        "position": _position_payload(decoration.position),
        "placed_at": decoration.placed_at.isoformat(),
    }


def aquarium_state_payload(state: AquariumState) -> dict[str, object]:
    if not isinstance(state, AquariumState):
        raise TypeError("state must be an AquariumState")
    return {
        "tanks": {
            tank_id: {
                "tank_id": tank.tank_id,
                "theme": tank.theme,
                "fish": [_fish_payload(fish) for fish in tank.fish],
                "decorations": [_decoration_payload(item) for item in tank.decorations],
            }
            for tank_id, tank in sorted(state.tanks.items())
        },
        "owned_tanks": sorted(state.owned_tanks),
        "owned_decorations": dict(sorted(state.owned_decorations.items())),
        "total_fish_displayed": state.total_fish_displayed,
    }


def aquarium_identity(subject_id: str) -> str:
    subject = text(subject_id, "aquarium subject_id")
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
    subject = text(subject_id, "aquarium subject_id")
    normalized_action = text(action, "aquarium action").lower()
    if normalized_action not in _ALLOWED_ACTIONS:
        raise ValueError(f"unsupported aquarium action: {normalized_action}")
    occurred = aware(occurred_at, "aquarium occurred_at")
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
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return AquariumPosition(
        count(value.get("x"), f"{field_name} x"),
        count(value.get("y"), f"{field_name} y"),
    )


def _fish_from_payload(value: object) -> DisplayFish:
    if not isinstance(value, Mapping):
        raise TypeError("aquarium fish payload must be a mapping")
    traits = value.get("traits", {})
    if not isinstance(traits, Mapping):
        raise TypeError("aquarium fish traits must be a mapping")
    size = value.get("size")
    if isinstance(size, bool) or not isinstance(size, (int, float)):
        raise TypeError("aquarium fish size must be numeric")
    return DisplayFish(
        id=text(value.get("id"), "aquarium fish id"),
        name=text(value.get("name"), "aquarium fish name"),
        species=text(value.get("species"), "aquarium fish species"),
        size=float(size),
        position=_position_from_payload(value.get("position"), "aquarium fish position"),
        traits=dict(traits),
        color=text(value.get("color"), "aquarium fish color"),
        added_at=_optional_time(value.get("added_at"), "aquarium fish added_at"),
    )


def _decoration_from_payload(value: object) -> PlacedDecoration:
    if not isinstance(value, Mapping):
        raise TypeError("aquarium decoration payload must be a mapping")
    placed_raw = value.get("placed_at")
    if not isinstance(placed_raw, str):
        raise TypeError("aquarium decoration placed_at must be an ISO-8601 string")
    try:
        placed_at = datetime.fromisoformat(placed_raw)
    except ValueError as exc:
        raise ValueError("aquarium decoration placed_at must be ISO-8601") from exc
    return PlacedDecoration(
        id=text(value.get("id"), "placed decoration id"),
        decoration_id=text(value.get("decoration_id"), "decoration id"),
        name=text(value.get("name"), "placed decoration name"),
        position=_position_from_payload(value.get("position"), "decoration position"),
        placed_at=aware(placed_at, "placed_at"),
    )


def _state_from_payload(payload: Mapping[str, object]) -> AquariumState:
    raw_tanks = payload.get("tanks")
    if not isinstance(raw_tanks, Mapping):
        raise TypeError("aquarium tanks must be a mapping")
    tanks: dict[str, AquariumTankState] = {}
    for raw_key, raw_tank in raw_tanks.items():
        tank_id = text(raw_key, "aquarium tank key")
        if not isinstance(raw_tank, Mapping):
            raise TypeError("aquarium tank payload must be a mapping")
        fish = tuple(_fish_from_payload(item) for item in _sequence(raw_tank.get("fish", ()), "aquarium fish"))
        decorations = tuple(
            _decoration_from_payload(item)
            for item in _sequence(raw_tank.get("decorations", ()), "aquarium decorations")
        )
        tanks[tank_id] = AquariumTankState(
            tank_id=text(raw_tank.get("tank_id"), "aquarium tank id"),
            fish=fish,
            decorations=decorations,
            theme=text(raw_tank.get("theme"), "aquarium tank theme"),
        )

    raw_owned = _sequence(payload.get("owned_tanks"), "aquarium owned_tanks")
    owned_tanks = frozenset(text(item, "aquarium owned tank") for item in raw_owned)
    raw_inventory = payload.get("owned_decorations", {})
    if not isinstance(raw_inventory, Mapping):
        raise TypeError("aquarium owned_decorations must be a mapping")
    return AquariumState(
        tanks=tanks,
        owned_tanks=owned_tanks,
        owned_decorations=counts(raw_inventory, "aquarium owned decorations"),
        total_fish_displayed=count(
            payload.get("total_fish_displayed"), "aquarium total fish displayed"
        ),
    )


def aquarium_event_to_memory_item(event: DomainEvent) -> Mapping[str, Any]:
    if event.topic not in {f"aquarium.{action}" for action in _ALLOWED_ACTIONS}:
        raise ValueError("expected an aquarium transition event")
    occurred = aware(event.occurred_at, "aquarium event occurred_at")
    payload = event.payload
    if not isinstance(payload, Mapping):
        raise TypeError("aquarium event payload must be a mapping")

    subject = text(payload.get("subject_id"), "aquarium subject_id")
    identity = _sha256(
        payload.get("aquarium_identity_sha256"), "aquarium_identity_sha256"
    )
    if identity != aquarium_identity(subject):
        raise ValueError("aquarium event identity digest mismatch")

    expected_digest = _sha256(
        payload.get("aquarium_state_sha256"), "aquarium_state_sha256"
    )
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
            "decoration_count": sum(len(tank.decorations) for tank in state.tanks.values()),
            "occurred_at": occurred.astimezone(timezone.utc).isoformat(),
        },
    }


def aquarium_state_memory_item(
    state: AquariumState,
    *,
    subject_id: str,
) -> Mapping[str, Any]:
    subject = text(subject_id, "aquarium subject_id")
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
            "decoration_count": sum(len(tank.decorations) for tank in state.tanks.values()),
        },
    }
