"""Versioned local protocol envelopes for worker control messages.

This module defines data only. It intentionally does not open sockets, spawn
threads, or perform transport I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
from types import MappingProxyType
from typing import Mapping

from skeleton.shells.worker_identity import WorkerIdentity


class WorkerMessageKind(str, Enum):
    HELLO = "hello"
    HEARTBEAT = "heartbeat"
    ASSIGN = "assign"
    ACK = "ack"
    COMPLETE = "complete"
    FAIL = "fail"
    STOP = "stop"
    DRAIN = "drain"
    STATUS = "status"


_MESSAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


@dataclass(frozen=True)
class WorkerMessage:
    message_id: str
    sequence: int
    kind: WorkerMessageKind
    sender: WorkerIdentity
    recipient: str
    payload: Mapping[str, object] = field(default_factory=dict)
    protocol_version: int = 1
    correlation_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.message_id, str) or not _MESSAGE_ID.fullmatch(self.message_id):
            raise ValueError("invalid message_id")
        if self.sequence <= 0:
            raise ValueError("message sequence must be positive")
        if not isinstance(self.kind, WorkerMessageKind):
            object.__setattr__(self, "kind", WorkerMessageKind(self.kind))
        if not self.recipient or len(self.recipient) > 128:
            raise ValueError("invalid message recipient")
        if self.protocol_version <= 0 or self.protocol_version > 1024:
            raise ValueError("invalid protocol_version")
        if len(self.correlation_id) > 160:
            raise ValueError("correlation_id too long")
        payload = dict(self.payload)
        if len(payload) > 64:
            raise ValueError("worker message payload has too many fields")
        # Fail closed on opaque runtime objects. Protocol payloads must remain
        # JSON-shaped so they can be audited and transported by an outer layer.
        try:
            json.dumps(payload, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("worker message payload must be JSON serializable") from exc
        object.__setattr__(self, "payload", MappingProxyType(payload))

    def to_dict(self) -> dict[str, object]:
        return {
            "message_id": self.message_id,
            "sequence": self.sequence,
            "kind": self.kind.value,
            "sender": self.sender.to_dict(),
            "recipient": self.recipient,
            "payload": dict(self.payload),
            "protocol_version": self.protocol_version,
            "correlation_id": self.correlation_id,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ProtocolCursor:
    sender_id: str
    generation: int
    last_sequence: int = 0


class ProtocolGuard:
    """Reject replay, generation rollback, and incompatible protocol versions."""

    def __init__(self, *, protocol_version: int = 1, max_senders: int = 4096) -> None:
        if protocol_version <= 0:
            raise ValueError("protocol_version must be positive")
        self.protocol_version = protocol_version
        self.max_senders = max_senders
        self._cursors: dict[str, ProtocolCursor] = {}

    def accept(self, message: WorkerMessage) -> ProtocolCursor:
        if message.protocol_version != self.protocol_version:
            raise RuntimeError("worker protocol version mismatch")
        worker_id = message.sender.worker_id
        current = self._cursors.get(worker_id)
        if current is None:
            if len(self._cursors) >= self.max_senders:
                raise RuntimeError("worker protocol sender capacity exhausted")
            cursor = ProtocolCursor(worker_id, message.sender.generation, message.sequence)
            self._cursors[worker_id] = cursor
            return cursor
        if message.sender.generation < current.generation:
            raise RuntimeError("worker protocol generation rollback")
        if message.sender.generation == current.generation and message.sequence <= current.last_sequence:
            raise RuntimeError("worker protocol replay detected")
        cursor = ProtocolCursor(worker_id, message.sender.generation, message.sequence)
        self._cursors[worker_id] = cursor
        return cursor

    def cursor(self, worker_id: str) -> ProtocolCursor | None:
        return self._cursors.get(worker_id)

    def reset(self, worker_id: str) -> None:
        self._cursors.pop(worker_id, None)
