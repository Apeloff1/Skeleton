"""Boundary adapters for the promoted achievement policy.

Achievement qualification remains pure policy. These helpers compose an
unlocked/claimed achievement with the existing canonical ``DomainEvent`` and
``MemoryContract`` shapes without introducing a second event or persistence
system.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from skeleton.frontier.achievements import AchievementSpec, AchievementState
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.events import DomainEvent


_ALLOWED_ACTIONS = frozenset({"unlocked", "claimed"})
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


def achievement_identity(subject_id: str, achievement_id: str) -> str:
    """Return the stable identity shared by event and memory projections."""

    subject = _text(subject_id, "achievement subject_id")
    achievement = _text(achievement_id, "achievement id")
    return stable_content_digest(
        {"subject_id": subject, "achievement_id": achievement}
    )


def _spec_material(
    *,
    achievement_id: str,
    name: str,
    category: str,
    hidden: bool,
    requirement_type: str,
    requirement_count: int,
) -> Mapping[str, Any]:
    return {
        "achievement_id": achievement_id,
        "name": name,
        "category": category,
        "hidden": hidden,
        "requirement_type": requirement_type,
        "requirement_count": requirement_count,
    }


def achievement_spec_digest(achievement: AchievementSpec) -> str:
    """Digest the policy fields carried across achievement event boundaries."""

    return stable_content_digest(
        _spec_material(
            achievement_id=achievement.id,
            name=achievement.name,
            category=achievement.category,
            hidden=achievement.hidden,
            requirement_type=achievement.requirement.kind,
            requirement_count=achievement.requirement.count,
        )
    )


def achievement_event(
    achievement: AchievementSpec,
    *,
    subject_id: str,
    action: str,
    occurred_at: datetime,
) -> DomainEvent:
    """Project one achievement transition onto the canonical durable event bus."""

    subject = _text(subject_id, "achievement subject_id")
    normalized_action = _text(action, "achievement action").lower()
    if normalized_action not in _ALLOWED_ACTIONS:
        raise ValueError(f"unsupported achievement action: {normalized_action}")
    occurred = _aware(occurred_at, "achievement occurred_at")
    identity = achievement_identity(subject, achievement.id)
    spec_digest = achievement_spec_digest(achievement)

    return DomainEvent(
        topic=f"achievement.{normalized_action}",
        payload={
            "achievement_identity_sha256": identity,
            "achievement_spec_sha256": spec_digest,
            "achievement_id": achievement.id,
            "subject_id": subject,
            "name": achievement.name,
            "category": achievement.category,
            "hidden": achievement.hidden,
            "requirement_type": achievement.requirement.kind,
            "requirement_count": achievement.requirement.count,
        },
        occurred_at=occurred,
    )


def achievement_event_to_memory_item(event: DomainEvent) -> Mapping[str, Any]:
    """Validate an achievement transition and project it to canonical memory.

    The stable subject+achievement digest is revalidated before it becomes the
    memory id, while a separate spec digest binds the descriptive policy fields.
    At-least-once replay therefore converges through ordinary memory upsert
    without allowing altered achievement content to reuse the same entity id.
    """

    if event.topic not in {"achievement.unlocked", "achievement.claimed"}:
        raise ValueError("expected an achievement transition event")
    occurred = _aware(event.occurred_at, "achievement event occurred_at")

    payload = event.payload
    if not isinstance(payload, Mapping):
        raise TypeError("achievement event payload must be a mapping")
    identity = _sha256(
        payload.get("achievement_identity_sha256"),
        "achievement_identity_sha256",
    )
    spec_digest = _sha256(
        payload.get("achievement_spec_sha256"),
        "achievement_spec_sha256",
    )
    achievement_id = _text(payload.get("achievement_id"), "achievement_id")
    subject_id = _text(payload.get("subject_id"), "subject_id")
    name = _text(payload.get("name"), "achievement name")
    category = _text(payload.get("category"), "achievement category")
    hidden = payload.get("hidden")
    if not isinstance(hidden, bool):
        raise TypeError("achievement hidden must be a boolean")
    requirement_type = _text(
        payload.get("requirement_type"),
        "achievement requirement_type",
    )
    requirement_count = payload.get("requirement_count")
    if isinstance(requirement_count, bool) or not isinstance(requirement_count, int):
        raise TypeError("achievement requirement_count must be an integer")
    if requirement_count < 1:
        raise ValueError("achievement requirement_count must be positive")

    expected_identity = achievement_identity(subject_id, achievement_id)
    if identity != expected_identity:
        raise ValueError("achievement event identity digest mismatch")

    expected_spec_digest = stable_content_digest(
        _spec_material(
            achievement_id=achievement_id,
            name=name,
            category=category,
            hidden=hidden,
            requirement_type=requirement_type,
            requirement_count=requirement_count,
        )
    )
    if spec_digest != expected_spec_digest:
        raise ValueError("achievement event spec digest mismatch")

    action = event.topic.removeprefix("achievement.")
    return {
        "id": identity,
        "content": f"achievement.{action} {name} {category}",
        "metadata": {
            "achievement_id": achievement_id,
            "subject_id": subject_id,
            "achievement_identity_sha256": identity,
            "achievement_spec_sha256": spec_digest,
            "achievement_action": action,
            "achievement_category": category,
            "hidden": hidden,
            "requirement_type": requirement_type,
            "requirement_count": requirement_count,
            "occurred_at": occurred.isoformat(),
        },
    }


def achievement_state_memory_item(
    achievement: AchievementSpec,
    state: AchievementState,
    *,
    subject_id: str,
) -> Mapping[str, Any]:
    """Project current unlocked/claimed state to the same stable memory id."""

    if achievement.id not in state.unlocked:
        raise ValueError("achievement must be unlocked before memory projection")
    identity = achievement_identity(subject_id, achievement.id)
    spec_digest = achievement_spec_digest(achievement)
    return {
        "id": identity,
        "content": f"achievement {achievement.name} {achievement.category}",
        "metadata": {
            "achievement_id": achievement.id,
            "subject_id": subject_id,
            "achievement_identity_sha256": identity,
            "achievement_spec_sha256": spec_digest,
            "achievement_category": achievement.category,
            "unlocked": True,
            "claimed": achievement.id in state.claimed,
            "hidden": achievement.hidden,
        },
    }
