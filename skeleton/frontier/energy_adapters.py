"""Event and memory adapters for the promoted energy policy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.energy import EnergyState
from skeleton.frontier.events import DomainEvent


_ALLOWED_ACTIONS = frozenset(
    {"spent", "restored", "regenerated", "boosted", "synchronized"}
)
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


def _optional_datetime(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be an ISO-8601 string or null")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601") from exc
    return _aware(parsed, field_name)


def _sha256(value: object, field_name: str) -> str:
    digest = _text(value, field_name)
    if len(digest) != 64 or any(character not in _HEX for character in digest):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return digest


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    return value


def _state_payload(state: EnergyState) -> dict[str, object]:
    return {
        "current_energy": state.current_energy,
        "max_energy": state.max_energy,
        "last_updated": state.last_updated.astimezone(timezone.utc).isoformat(),
        "infinite_until": (
            state.infinite_until.astimezone(timezone.utc).isoformat()
            if state.infinite_until is not None
            else None
        ),
        "regen_multiplier": state.regen_multiplier,
        "regen_multiplier_until": (
            state.regen_multiplier_until.astimezone(timezone.utc).isoformat()
            if state.regen_multiplier_until is not None
            else None
        ),
        "total_energy_spent": state.total_energy_spent,
        "total_energy_restored": state.total_energy_restored,
        "ads_watched_today": state.ads_watched_today,
        "last_ad_watch": (
            state.last_ad_watch.astimezone(timezone.utc).isoformat()
            if state.last_ad_watch is not None
            else None
        ),
    }


def energy_identity(subject_id: str) -> str:
    subject = _text(subject_id, "energy subject_id")
    return stable_content_digest({"surface": "energy", "subject_id": subject})


def energy_state_digest(state: EnergyState) -> str:
    return stable_content_digest(_state_payload(state))


def energy_event(
    state: EnergyState,
    *,
    subject_id: str,
    action: str,
    occurred_at: datetime,
    delta: int = 0,
) -> DomainEvent:
    subject = _text(subject_id, "energy subject_id")
    normalized_action = _text(action, "energy action").lower()
    if normalized_action not in _ALLOWED_ACTIONS:
        raise ValueError(f"unsupported energy action: {normalized_action}")
    occurred = _aware(occurred_at, "energy occurred_at")
    if occurred < state.last_updated:
        raise ValueError("energy event cannot occur before state last_updated")
    if isinstance(delta, bool) or not isinstance(delta, int):
        raise TypeError("energy delta must be an integer")

    payload = _state_payload(state)
    payload.update(
        {
            "subject_id": subject,
            "energy_identity_sha256": energy_identity(subject),
            "energy_state_sha256": energy_state_digest(state),
            "delta": delta,
        }
    )
    return DomainEvent(
        topic=f"energy.{normalized_action}",
        payload=payload,
        occurred_at=occurred,
    )


def _state_from_payload(payload: Mapping[str, object]) -> EnergyState:
    last_updated_raw = payload.get("last_updated")
    if not isinstance(last_updated_raw, str):
        raise TypeError("energy last_updated must be an ISO-8601 string")
    try:
        last_updated = datetime.fromisoformat(last_updated_raw)
    except ValueError as exc:
        raise ValueError("energy last_updated must be ISO-8601") from exc

    multiplier = payload.get("regen_multiplier")
    if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)):
        raise TypeError("energy regen_multiplier must be numeric")

    return EnergyState(
        current_energy=_integer(payload.get("current_energy"), "energy current_energy"),
        max_energy=_integer(payload.get("max_energy"), "energy max_energy"),
        last_updated=_aware(last_updated, "energy last_updated"),
        infinite_until=_optional_datetime(
            payload.get("infinite_until"), "energy infinite_until"
        ),
        regen_multiplier=float(multiplier),
        regen_multiplier_until=_optional_datetime(
            payload.get("regen_multiplier_until"),
            "energy regen_multiplier_until",
        ),
        total_energy_spent=_integer(
            payload.get("total_energy_spent"), "energy total_energy_spent"
        ),
        total_energy_restored=_integer(
            payload.get("total_energy_restored"), "energy total_energy_restored"
        ),
        ads_watched_today=_integer(
            payload.get("ads_watched_today"), "energy ads_watched_today"
        ),
        last_ad_watch=_optional_datetime(
            payload.get("last_ad_watch"), "energy last_ad_watch"
        ),
    )


def energy_event_to_memory_item(event: DomainEvent) -> Mapping[str, Any]:
    if event.topic not in {f"energy.{action}" for action in _ALLOWED_ACTIONS}:
        raise ValueError("expected an energy transition event")
    occurred = _aware(event.occurred_at, "energy event occurred_at")

    payload = event.payload
    if not isinstance(payload, Mapping):
        raise TypeError("energy event payload must be a mapping")

    subject = _text(payload.get("subject_id"), "energy subject_id")
    identity = _sha256(
        payload.get("energy_identity_sha256"), "energy_identity_sha256"
    )
    if identity != energy_identity(subject):
        raise ValueError("energy event identity digest mismatch")

    expected_state_digest = _sha256(
        payload.get("energy_state_sha256"), "energy_state_sha256"
    )
    state = _state_from_payload(payload)
    if energy_state_digest(state) != expected_state_digest:
        raise ValueError("energy event state digest mismatch")
    if occurred < state.last_updated:
        raise ValueError("energy event occurred_at predates state last_updated")

    delta = _integer(payload.get("delta", 0), "energy delta")
    action = event.topic.removeprefix("energy.")
    return {
        "id": identity,
        "content": f"energy {action} {state.current_energy}/{state.max_energy}",
        "metadata": {
            "subject_id": subject,
            "energy_identity_sha256": identity,
            "energy_state_sha256": expected_state_digest,
            "energy_action": action,
            "current_energy": state.current_energy,
            "max_energy": state.max_energy,
            "delta": delta,
            "is_infinite": (
                state.infinite_until is not None and state.infinite_until > occurred
            ),
            "occurred_at": occurred.isoformat(),
            "last_updated": state.last_updated.isoformat(),
        },
    }


def energy_state_memory_item(
    state: EnergyState,
    *,
    subject_id: str,
) -> Mapping[str, Any]:
    subject = _text(subject_id, "energy subject_id")
    identity = energy_identity(subject)
    digest = energy_state_digest(state)
    return {
        "id": identity,
        "content": f"energy state {state.current_energy}/{state.max_energy}",
        "metadata": {
            "subject_id": subject,
            "energy_identity_sha256": identity,
            "energy_state_sha256": digest,
            "current_energy": state.current_energy,
            "max_energy": state.max_energy,
            "total_energy_spent": state.total_energy_spent,
            "total_energy_restored": state.total_energy_restored,
            "ads_watched_today": state.ads_watched_today,
            "last_updated": state.last_updated.isoformat(),
        },
    }
