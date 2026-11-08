"""Version-negotiated envelope for optional accelerator subprocesses."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
import json
import math
import uuid

MAX_ENVELOPE_PAYLOAD_BYTES = 1_048_576
MAX_ENVELOPE_DEPTH = 16
MAX_ENVELOPE_NODES = 262_144


def _bounded_wire_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the entire untrusted RPC payload before subprocess dispatch."""
    if len(payload) > MAX_ENVELOPE_NODES:
        raise AcceleratorProtocolError("payload node budget exceeded")
    root = dict(payload)
    pending: list[tuple[Any, int]] = [(root, 0)]
    visited: set[int] = set()
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > MAX_ENVELOPE_NODES:
            raise AcceleratorProtocolError("payload node budget exceeded")
        if depth > MAX_ENVELOPE_DEPTH:
            raise AcceleratorProtocolError("payload nesting limit exceeded")
        if isinstance(value, (dict, list, tuple)):
            identity = id(value)
            if identity in visited:
                raise AcceleratorProtocolError("payload contains cyclic or aliased containers")
            visited.add(identity)
            if isinstance(value, dict):
                if len(value) > MAX_ENVELOPE_NODES - nodes - len(pending):
                    raise AcceleratorProtocolError("payload node budget exceeded")
                for key in value:
                    if not isinstance(key, str):
                        raise AcceleratorProtocolError("payload object keys must be text")
                    if len(key) > MAX_ENVELOPE_PAYLOAD_BYTES:
                        raise AcceleratorProtocolError("payload text budget exceeded")
                pending.extend((v, depth + 1) for v in value.values())
            else:
                if len(value) > MAX_ENVELOPE_NODES - nodes:
                    raise AcceleratorProtocolError("payload node budget exceeded")
                pending.extend((v, depth + 1) for v in value)
        elif isinstance(value, str):
            if len(value) > MAX_ENVELOPE_PAYLOAD_BYTES:
                raise AcceleratorProtocolError("payload text budget exceeded")
        elif isinstance(value, bool) or value is None:
            continue
        elif isinstance(value, int):
            if value.bit_length() > MAX_ENVELOPE_PAYLOAD_BYTES * 4:
                raise AcceleratorProtocolError("payload integer budget exceeded")
        elif isinstance(value, float) and math.isfinite(value):
            continue
        else:
            raise AcceleratorProtocolError("payload contains unsupported or non-finite values")
    try:
        encoded = json.dumps(root, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, OverflowError, UnicodeError) as exc:
        raise AcceleratorProtocolError("payload cannot be encoded as JSON") from exc
    if len(encoded) > MAX_ENVELOPE_PAYLOAD_BYTES:
        raise AcceleratorProtocolError("payload byte budget exceeded")
    return root




class AcceleratorProtocolError(RuntimeError):
    pass


ACCELERATION_PROTOCOL_ID = "skeleton.acceleration.rpc"


@dataclass(frozen=True, order=True, slots=True)
class ProtocolVersion:
    major: int
    minor: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.major, bool)
            or isinstance(self.minor, bool)
            or not isinstance(self.major, int)
            or not isinstance(self.minor, int)
            or self.major < 0
            or self.minor < 0
        ):
            raise ValueError("protocol version components must be non-negative integers")

    @classmethod
    def parse(cls, raw: str) -> "ProtocolVersion":
        if not isinstance(raw, str):
            raise ValueError("protocol version must be text")
        parts = raw.split(".")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError(f"invalid protocol version: {raw!r}")
        parsed = cls(int(parts[0]), int(parts[1]))
        if str(parsed) != raw:
            raise ValueError(f"protocol version must use canonical decimal form: {raw!r}")
        return parsed

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"


CURRENT_PROTOCOL_VERSION = ProtocolVersion(1, 0)
SUPPORTED_PROTOCOL_VERSIONS = (CURRENT_PROTOCOL_VERSION,)


def negotiate_version(
    client_versions: Iterable[ProtocolVersion],
    server_versions: Iterable[ProtocolVersion],
) -> ProtocolVersion:
    if isinstance(client_versions, (str, bytes)) or isinstance(
        server_versions, (str, bytes)
    ):
        raise TypeError("protocol versions must be iterables of ProtocolVersion")
    client_items = tuple(client_versions)
    server_items = tuple(server_versions)
    if any(not isinstance(item, ProtocolVersion) for item in client_items):
        raise TypeError("client protocol versions must be ProtocolVersion")
    if any(not isinstance(item, ProtocolVersion) for item in server_items):
        raise TypeError("server protocol versions must be ProtocolVersion")
    client = set(client_items)
    server = set(server_items)
    shared = client & server
    if not shared:
        raise AcceleratorProtocolError("no compatible accelerator protocol version")
    return max(shared)


def negotiate_wire_major(peer_major: int) -> ProtocolVersion:
    if isinstance(peer_major, bool) or not isinstance(peer_major, int):
        raise AcceleratorProtocolError("wire protocol major must be an integer")
    if peer_major < 0:
        raise AcceleratorProtocolError("wire protocol major cannot be negative")
    peer = ProtocolVersion(peer_major, 0)
    return negotiate_version(SUPPORTED_PROTOCOL_VERSIONS, (peer,))


def make_request_envelope(
    *,
    protocol_id: str,
    version: ProtocolVersion,
    operation: str,
    payload: Mapping[str, Any],
    deadline_utc: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    for name, value in (
        ("protocol_id", protocol_id),
        ("operation", operation),
        ("deadline_utc", deadline_utc),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be non-empty text")
        if value != value.strip():
            raise ValueError(f"{name} must use canonical text")
    if protocol_id != ACCELERATION_PROTOCOL_ID:
        raise AcceleratorProtocolError(
            f"unsupported accelerator protocol id: {protocol_id!r}"
        )
    if not isinstance(version, ProtocolVersion):
        raise TypeError("version must be ProtocolVersion")
    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        raise AcceleratorProtocolError(
            f"unsupported accelerator protocol version: {version}"
        )
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    if not deadline_utc.endswith("Z"):
        raise ValueError("deadline_utc must be canonical RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(deadline_utc[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("deadline_utc must be RFC3339 UTC") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("deadline_utc must be UTC")
    if parsed <= datetime.now(timezone.utc):
        raise ValueError("deadline_utc must be in the future")

    if request_id is None:
        rid = str(uuid.uuid4())
    else:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must be non-empty text")
        if request_id != request_id.strip():
            raise ValueError("request_id must use canonical text")
        rid = request_id
    return {
        "protocol_id": protocol_id,
        "version": str(version),
        "request_id": rid,
        "operation": operation,
        "deadline_utc": deadline_utc,
        "payload": _bounded_wire_payload(payload),
    }


__all__ = [
    "ACCELERATION_PROTOCOL_ID",
    "AcceleratorProtocolError",
    "CURRENT_PROTOCOL_VERSION",
    "ProtocolVersion",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "make_request_envelope",
    "negotiate_version",
    "negotiate_wire_major",
]
