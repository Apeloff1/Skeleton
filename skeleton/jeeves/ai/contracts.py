"""Typed, deterministic assurance contracts for the Jeeves control plane.

This module is deliberately small.  Contract identity is derived from canonical JSON,
not Python repr(), and records copy caller-owned data before fingerprinting so later
mutation cannot silently change the meaning of an admitted contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_TEXT = 8192
MAX_EVIDENCE = 256
MAX_PAYLOAD_BYTES = 64 * 1024


class ContractState(str, Enum):
    NEW = "new"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"


class Authority(str, Enum):
    """Repository orchestration authority; ordering is intentionally not numeric."""

    SUPERVISOR = "supervisor"
    SECRETARY = "secretary"
    WORKER = "worker"


def _text(value: str, *, field_name: str = "text") -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT or "\x00" in value:
        raise ValueError(f"invalid {field_name}")
    return value


def _json_value(value: Any, *, depth: int = 0) -> Any:
    """Return a JSON-safe detached value with bounded recursive structure."""
    if depth > 12:
        raise ValueError("payload nesting too deep")
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and len(value) > MAX_TEXT:
            raise ValueError("payload text too long")
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non-finite payload number")
        return value
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            _text(key, field_name="payload key")
            if key in out:
                raise ValueError("duplicate payload key")
            out[key] = _json_value(item, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_json_value(item, depth=depth + 1) for item in value]
    raise ValueError(f"unsupported payload type: {type(value).__name__}")


def _canonical(value: Any) -> bytes:
    encoded = json.dumps(
        _json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError("payload too large")
    return encoded


def _digest(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class ContractRecord:
    name: str
    state: ContractState = ContractState.NEW
    payload: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    authority: Authority = Authority.WORKER
    parent_digest: str | None = None

    def __post_init__(self) -> None:
        _text(self.name, field_name="contract name")
        if not isinstance(self.state, ContractState):
            raise ValueError("invalid contract state")
        if not isinstance(self.authority, Authority):
            raise ValueError("invalid authority")
        if not isinstance(self.evidence, tuple) or len(self.evidence) > MAX_EVIDENCE:
            raise ValueError("invalid evidence")
        evidence = tuple(_text(item, field_name="evidence") for item in self.evidence)
        detached = _json_value(self.payload)
        _canonical(detached)
        object.__setattr__(self, "payload", MappingProxyType(detached))
        object.__setattr__(self, "evidence", evidence)
        if self.parent_digest is not None:
            if not isinstance(self.parent_digest, str) or len(self.parent_digest) != 64:
                raise ValueError("invalid parent digest")
            try:
                int(self.parent_digest, 16)
            except ValueError as exc:
                raise ValueError("invalid parent digest") from exc

    @property
    def digest(self) -> str:
        return _digest(
            {
                "authority": self.authority.value,
                "evidence": list(self.evidence),
                "name": self.name,
                "parent_digest": self.parent_digest,
                "payload": dict(self.payload),
                "state": self.state.value,
                "v": 1,
            }
        )


@dataclass(frozen=True)
class ContractLedger:
    records: tuple[ContractRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple):
            raise ValueError("records must be a tuple")
        names: set[str] = set()
        digests: set[str] = set()
        for record in self.records:
            if not isinstance(record, ContractRecord):
                raise ValueError("invalid record")
            if record.name in names or record.digest in digests:
                raise ValueError("duplicate record")
            names.add(record.name)
            digests.add(record.digest)

    def append(self, record: ContractRecord) -> "ContractLedger":
        if not isinstance(record, ContractRecord):
            raise ValueError("invalid record")
        return ContractLedger(self.records + (record,))

    @property
    def digest(self) -> str:
        return _digest({"records": [record.digest for record in self.records], "v": 1})


def validate_contract(records: Sequence[ContractRecord]) -> tuple[str, ...]:
    if isinstance(records, (str, bytes)):
        raise ValueError("records must be a sequence of contracts")
    ledger = ContractLedger(tuple(records))
    return tuple(record.digest for record in ledger.records)
