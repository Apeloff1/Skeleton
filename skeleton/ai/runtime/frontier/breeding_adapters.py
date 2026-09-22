"""Event, memory and achievement adapters for promoted breeding policy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from skeleton.frontier.breeding import OffspringPlan
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.events import DomainEvent


_HEX = frozenset("0123456789abcdef")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if normalized != value:
        raise ValueError(f"{field_name} must be normalized")
    return value


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _sha256(value: object, field_name: str) -> str:
    digest = _text(value, field_name)
    if len(digest) != 64 or any(character not in _HEX for character in digest):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return digest


def _plan_payload(plan: OffspringPlan) -> dict[str, object]:
    return {
        "offspring_id": plan.id,
        "species": plan.species,
        "name": plan.name,
        "traits": dict(plan.traits),
        "size": plan.size,
        "value": plan.value,
        "parents": list(plan.parents),
        "bred_at": plan.bred_at.astimezone(timezone.utc).isoformat(),
        "special_breed_id": plan.special_breed_id,
        "is_new_discovery": plan.is_new_discovery,
        "xp_reward": plan.xp_reward,
    }


def breeding_offspring_identity(subject_id: str, offspring_id: str) -> str:
    subject = _text(subject_id, "breeding subject_id")
    offspring = _text(offspring_id, "offspring id")
    return stable_content_digest(
        {"surface": "breeding-offspring", "subject_id": subject, "offspring_id": offspring}
    )


def breeding_offspring_digest(plan: OffspringPlan) -> str:
    return stable_content_digest(_plan_payload(plan))


def breeding_offspring_event(
    plan: OffspringPlan,
    *,
    subject_id: str,
    occurred_at: datetime,
) -> DomainEvent:
    subject = _text(subject_id, "breeding subject_id")
    occurred = _aware(occurred_at, "breeding occurred_at")
    bred_at = _aware(plan.bred_at, "offspring bred_at")
    if occurred < bred_at:
        raise ValueError("breeding event cannot occur before offspring bred_at")

    payload = _plan_payload(plan)
    payload.update(
        {
            "subject_id": subject,
            "breeding_identity_sha256": breeding_offspring_identity(subject, plan.id),
            "breeding_offspring_sha256": breeding_offspring_digest(plan),
        }
    )
    return DomainEvent(
        topic="breeding.offspring_collected",
        payload=payload,
        occurred_at=occurred,
    )


def breeding_event_to_memory_item(event: DomainEvent) -> Mapping[str, Any]:
    if event.topic != "breeding.offspring_collected":
        raise ValueError("expected a breeding offspring event")
    occurred = _aware(event.occurred_at, "breeding event occurred_at")
    payload = event.payload
    if not isinstance(payload, Mapping):
        raise TypeError("breeding event payload must be a mapping")

    subject = _text(payload.get("subject_id"), "breeding subject_id")
    offspring_id = _text(payload.get("offspring_id"), "offspring id")
    identity = _sha256(
        payload.get("breeding_identity_sha256"),
        "breeding_identity_sha256",
    )
    if identity != breeding_offspring_identity(subject, offspring_id):
        raise ValueError("breeding event identity digest mismatch")

    expected_digest = _sha256(
        payload.get("breeding_offspring_sha256"),
        "breeding_offspring_sha256",
    )

    bred_at_raw = payload.get("bred_at")
    if not isinstance(bred_at_raw, str):
        raise TypeError("offspring bred_at must be an ISO-8601 string")
    try:
        bred_at = datetime.fromisoformat(bred_at_raw)
    except ValueError as exc:
        raise ValueError("offspring bred_at must be ISO-8601") from exc
    bred_at = _aware(bred_at, "offspring bred_at")
    if occurred < bred_at:
        raise ValueError("breeding event occurred_at predates offspring bred_at")

    rebuilt = {
        "offspring_id": offspring_id,
        "species": _text(payload.get("species"), "offspring species"),
        "name": _text(payload.get("name"), "offspring name"),
        "traits": payload.get("traits"),
        "size": payload.get("size"),
        "value": payload.get("value"),
        "parents": payload.get("parents"),
        "bred_at": bred_at.isoformat(),
        "special_breed_id": payload.get("special_breed_id"),
        "is_new_discovery": payload.get("is_new_discovery"),
        "xp_reward": payload.get("xp_reward"),
    }
    if stable_content_digest(rebuilt) != expected_digest:
        raise ValueError("breeding event offspring digest mismatch")

    return {
        "id": identity,
        "content": f"bred offspring {rebuilt['species']} value {rebuilt['value']}",
        "metadata": {
            "subject_id": subject,
            "offspring_id": offspring_id,
            "species": rebuilt["species"],
            "special_breed_id": rebuilt["special_breed_id"],
            "is_new_discovery": rebuilt["is_new_discovery"],
            "value": rebuilt["value"],
            "xp_reward": rebuilt["xp_reward"],
            "bred_at": bred_at.isoformat(),
            "occurred_at": occurred.isoformat(),
            "breeding_identity_sha256": identity,
            "breeding_offspring_sha256": expected_digest,
        },
    }


def achievement_signals_from_offspring(plan: OffspringPlan) -> Mapping[str, int]:
    """Project breeding output into the existing achievement signal boundary."""

    return {
        "special_breed": 1 if plan.special_breed_id is not None else 0,
    }
