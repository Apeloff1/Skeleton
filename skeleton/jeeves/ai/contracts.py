"""Typed, deterministic assurance contracts for the Jeeves control plane."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ._canonical import bounded_text, canonical_digest, detached_json, frozen_mapping

MAX_TEXT = 8192
MAX_CONTRACTS = 4096
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
    SUPERVISOR = "supervisor"
    SECRETARY = "secretary"
    WORKER = "worker"


def _digest(value: Any) -> str:
    return canonical_digest(value, max_bytes=MAX_PAYLOAD_BYTES)


@dataclass(frozen=True)
class ContractRecord:
    name: str
    state: ContractState = ContractState.NEW
    payload: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    authority: Authority = Authority.WORKER
    parent_digest: str | None = None

    def __post_init__(self) -> None:
        bounded_text(self.name, "contract name")
        if not isinstance(self.state, ContractState):
            raise ValueError("invalid contract state")
        if not isinstance(self.authority, Authority):
            raise ValueError("invalid authority")
        if not isinstance(self.evidence, tuple) or len(self.evidence) > MAX_EVIDENCE:
            raise ValueError("invalid evidence")
        evidence = tuple(bounded_text(item, "evidence") for item in self.evidence)
        object.__setattr__(self, "payload", frozen_mapping(self.payload, max_bytes=MAX_PAYLOAD_BYTES))
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
        return _digest({
            "authority": self.authority.value,
            "evidence": list(self.evidence),
            "name": self.name,
            "parent_digest": self.parent_digest,
            "payload": dict(self.payload),
            "state": self.state.value,
            "v": 1,
        })


@dataclass(frozen=True)
class ContractLedger:
    records: tuple[ContractRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or len(self.records) > MAX_CONTRACTS:
            raise ValueError("invalid contract records")
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
