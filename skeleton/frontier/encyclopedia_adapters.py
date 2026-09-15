"""Event and memory adapters for canonical fish collection state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.encyclopedia import (
    FishCollectionState,
    FishDiscoveryStats,
    collection_summary,
)
from skeleton.frontier.events import DomainEvent


_ALLOWED_ACTIONS = frozenset({"fish_discovered", "fish_caught"})
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


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def _positive_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        raise ValueError(f"{field_name} must be finite")
    if numeric <= 0:
        raise ValueError(f"{field_name} must be positive")
    return numeric


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_aware(value: object, field_name: str) -> datetime:
    text = _text(value, field_name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601") from exc
    return _aware(parsed, field_name)


def _sha256(value: object, field_name: str) -> str:
    digest = _text(value, field_name)
    if len(digest) != 64 or any(character not in _HEX for character in digest):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return digest


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return value


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    return value


def collection_identity(subject_id: str) -> str:
    subject = _text(subject_id, "collection subject_id")
    return stable_content_digest({"surface": "fish_collection", "subject_id": subject})


def collection_payload(collection: FishCollectionState) -> Mapping[str, Any]:
    if not isinstance(collection, FishCollectionState):
        raise TypeError("collection must be FishCollectionState")
    return {
        "discovered_fish": sorted(collection.discovered_fish),
        "fish_stats": {
            fish_id: {
                "caught": stats.caught,
                "largest": stats.largest,
                "smallest": stats.smallest,
                "first_caught": stats.first_caught.isoformat(),
            }
            for fish_id, stats in sorted(collection.fish_stats.items())
        },
    }


def collection_digest(collection: FishCollectionState) -> str:
    return stable_content_digest(collection_payload(collection))


def collection_event(
    collection: FishCollectionState,
    *,
    subject_id: str,
    fish_id: str,
    action: str,
    occurred_at: datetime,
) -> DomainEvent:
    subject = _text(subject_id, "collection subject_id")
    fish = _text(fish_id, "collection fish_id")
    normalized_action = _text(action, "collection action").lower()
    if normalized_action not in _ALLOWED_ACTIONS:
        raise ValueError(f"unsupported collection action: {normalized_action}")
    occurred = _aware(occurred_at, "collection occurred_at")
    if fish not in collection.discovered_fish:
        raise ValueError("collection event fish must already be discovered")

    payload = dict(collection_payload(collection))
    payload.update(
        {
            "subject_id": subject,
            "fish_id": fish,
            "collection_identity_sha256": collection_identity(subject),
            "collection_state_sha256": collection_digest(collection),
        }
    )
    return DomainEvent(
        topic=f"encyclopedia.{normalized_action}",
        payload=payload,
        occurred_at=occurred,
    )


def _collection_from_payload(payload: Mapping[str, object]) -> FishCollectionState:
    discovered = frozenset(
        _text(value, "discovered fish id")
        for value in _sequence(payload.get("discovered_fish"), "discovered_fish")
    )
    raw_stats = _mapping(payload.get("fish_stats"), "fish_stats")
    stats: dict[str, FishDiscoveryStats] = {}
    for raw_fish_id, raw_value in raw_stats.items():
        fish_id = _text(raw_fish_id, "fish_stats key")
        record = _mapping(raw_value, f"fish_stats[{fish_id!r}]")
        stats[fish_id] = FishDiscoveryStats(
            caught=_positive_int(record.get("caught"), f"{fish_id} caught"),
            largest=_positive_number(record.get("largest"), f"{fish_id} largest"),
            smallest=_positive_number(record.get("smallest"), f"{fish_id} smallest"),
            first_caught=_parse_aware(
                record.get("first_caught"), f"{fish_id} first_caught"
            ),
        )
    return FishCollectionState(discovered_fish=discovered, fish_stats=stats)


def collection_event_to_memory_item(event: DomainEvent) -> Mapping[str, Any]:
    if not isinstance(event, DomainEvent):
        raise TypeError("event must be DomainEvent")
    if event.topic not in {f"encyclopedia.{action}" for action in _ALLOWED_ACTIONS}:
        raise ValueError("expected an encyclopedia collection event")
    occurred = _aware(event.occurred_at, "collection event occurred_at")
    payload = _mapping(event.payload, "collection event payload")
    subject = _text(payload.get("subject_id"), "collection subject_id")
    fish_id = _text(payload.get("fish_id"), "collection fish_id")

    identity = _sha256(
        payload.get("collection_identity_sha256"), "collection_identity_sha256"
    )
    if identity != collection_identity(subject):
        raise ValueError("collection event identity digest mismatch")

    expected_digest = _sha256(
        payload.get("collection_state_sha256"), "collection_state_sha256"
    )
    collection = _collection_from_payload(payload)
    if fish_id not in collection.discovered_fish:
        raise ValueError("collection event fish is absent from rehydrated state")
    actual_digest = collection_digest(collection)
    if actual_digest != expected_digest:
        raise ValueError("collection event state digest mismatch")

    summary = collection_summary(collection)
    action = event.topic.removeprefix("encyclopedia.")
    return {
        "id": identity,
        "content": (
            f"encyclopedia {action} {fish_id} "
            f"{summary.unique_species_discovered} species"
        ),
        "metadata": {
            "subject_id": subject,
            "fish_id": fish_id,
            "collection_identity_sha256": identity,
            "collection_state_sha256": expected_digest,
            "collection_action": action,
            "unique_species_discovered": summary.unique_species_discovered,
            "total_fish_caught": summary.total_fish_caught,
            "largest_catch_id": summary.largest_catch_id,
            "largest_catch_size": summary.largest_catch_size,
            "most_caught_id": summary.most_caught_id,
            "most_caught_count": summary.most_caught_count,
            "occurred_at": occurred.isoformat(),
        },
    }


def collection_memory_item(
    collection: FishCollectionState,
    *,
    subject_id: str,
) -> Mapping[str, Any]:
    subject = _text(subject_id, "collection subject_id")
    identity = collection_identity(subject)
    digest = collection_digest(collection)
    summary = collection_summary(collection)
    return {
        "id": identity,
        "content": (
            f"fish collection {summary.unique_species_discovered} species "
            f"{summary.total_fish_caught} catches"
        ),
        "metadata": {
            "subject_id": subject,
            "collection_identity_sha256": identity,
            "collection_state_sha256": digest,
            "unique_species_discovered": summary.unique_species_discovered,
            "total_fish_caught": summary.total_fish_caught,
            "largest_catch_id": summary.largest_catch_id,
            "largest_catch_size": summary.largest_catch_size,
            "most_caught_id": summary.most_caught_id,
            "most_caught_count": summary.most_caught_count,
        },
    }
