"""Bounded JSON serialization helpers for shell-plane records."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from typing import Any, Mapping

from skeleton.shells.receipts import ExecutionReceipt


class SerializationError(ValueError):
    pass


def _normalize(value: Any, *, depth: int, max_depth: int) -> Any:
    if depth > max_depth:
        raise SerializationError("serialization depth exceeded")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return {"type": "bytes", "length": len(value)}
    if isinstance(value, Mapping):
        return {str(key): _normalize(child, depth=depth + 1, max_depth=max_depth) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(child, depth=depth + 1, max_depth=max_depth) for child in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_normalize(child, depth=depth + 1, max_depth=max_depth) for child in value)
    if hasattr(value, "to_dict"):
        return _normalize(value.to_dict(), depth=depth + 1, max_depth=max_depth)
    if is_dataclass(value):
        return _normalize(asdict(value), depth=depth + 1, max_depth=max_depth)
    raise SerializationError(f"unsupported value type: {type(value).__name__}")


def dumps(value: Any, *, max_bytes: int = 1_048_576, max_depth: int = 24, pretty: bool = False) -> str:
    if max_bytes <= 0 or max_depth <= 0:
        raise ValueError("serialization bounds must be positive")
    normalized = _normalize(value, depth=0, max_depth=max_depth)
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )
    if len(encoded.encode("utf-8")) > max_bytes:
        raise SerializationError("serialized payload exceeds byte limit")
    return encoded


def loads_object(payload: str | bytes, *, max_bytes: int = 1_048_576) -> dict[str, Any]:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    if len(raw) > max_bytes:
        raise SerializationError("serialized payload exceeds byte limit")
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SerializationError("invalid JSON payload") from exc
    if not isinstance(decoded, dict):
        raise SerializationError("JSON payload must be an object")
    return decoded


def receipt_from_dict(payload: Mapping[str, Any]) -> ExecutionReceipt:
    required = {
        "command",
        "correlation_id",
        "fingerprint",
        "started_at",
        "finished_at",
        "duration_ms",
        "returncode",
        "ok",
        "timed_out",
        "output_limited",
        "stdout_bytes",
        "stderr_bytes",
    }
    missing = required - set(payload)
    if missing:
        raise SerializationError("receipt is missing required fields")
    return ExecutionReceipt(
        receipt_id=str(payload.get("receipt_id") or ""),
        command=str(payload["command"]),
        correlation_id=str(payload["correlation_id"]),
        fingerprint=str(payload["fingerprint"]),
        started_at=str(payload["started_at"]),
        finished_at=str(payload["finished_at"]),
        duration_ms=float(payload["duration_ms"]),
        returncode=None if payload["returncode"] is None else int(payload["returncode"]),
        ok=bool(payload["ok"]),
        timed_out=bool(payload["timed_out"]),
        output_limited=bool(payload["output_limited"]),
        stdout_bytes=int(payload["stdout_bytes"]),
        stderr_bytes=int(payload["stderr_bytes"]),
        attempt=int(payload.get("attempt", 1)),
        metadata=dict(payload.get("metadata") or {}),
    )
