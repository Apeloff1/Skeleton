"""Version-negotiated envelope for optional accelerator subprocesses."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
import uuid


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
    client = set(client_versions)
    server = set(server_versions)
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
            raise ValueError(f"{name} must be non-empty")
    if protocol_id != ACCELERATION_PROTOCOL_ID:
        raise AcceleratorProtocolError(
            f"unsupported accelerator protocol id: {protocol_id!r}"
        )
    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        raise AcceleratorProtocolError(
            f"unsupported accelerator protocol version: {version}"
        )
    try:
        parsed = datetime.fromisoformat(deadline_utc.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("deadline_utc must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise ValueError("deadline_utc must be timezone-aware")
    if parsed.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        raise ValueError("deadline_utc must be in the future")

    rid = request_id or str(uuid.uuid4())
    if not isinstance(rid, str) or not rid.strip():
        raise ValueError("request_id must be non-empty")
    return {
        "protocol_id": protocol_id,
        "version": str(version),
        "request_id": rid,
        "operation": operation,
        "deadline_utc": deadline_utc,
        "payload": dict(payload),
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
