"""Bounded canonical JSON snapshots shared by runtime and memory adapters."""
import json
from collections.abc import Mapping
from typing import Any

from skeleton.frontier.assurance.digest import normalize_state
from skeleton.frontier.execution import positive_int

_MAX_PAYLOAD = 8_388_608


def json_snapshot(value: Any, *, max_bytes: int = 1_048_576) -> Any:
    """Validate JSON-compatible state and detach nested mutable data."""
    positive_int("max_bytes", max_bytes)
    if max_bytes > _MAX_PAYLOAD:
        raise ValueError("payload limit exceeds hard ceiling")
    try:
        normalized = normalize_state(value, max_encoded_bytes=max_bytes)
        encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > max_bytes:
            raise ValueError("payload exceeds encoded byte budget")
        return normalized
    except (TypeError, OverflowError, UnicodeError) as exc:
        raise ValueError("payload must be valid JSON") from exc


def memory_payload(item: Mapping[str, Any], item_id: str, max_bytes: int) -> dict[str, Any]:
    if type(item_id) is not str or not item_id.strip() or len(item_id) > 256:
        raise ValueError("invalid memory identifier")
    normalized = json_snapshot(item, max_bytes=max_bytes)
    if not isinstance(normalized, dict):
        raise ValueError("memory payload must be an object")
    if "id" in normalized and normalized["id"] != item_id:
        raise ValueError("conflicting memory identifier")
    normalized["id"] = item_id
    return json_snapshot(normalized, max_bytes=max_bytes)
