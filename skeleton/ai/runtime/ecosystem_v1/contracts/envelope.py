"""Immutable operation identity, provenance and request envelope."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .canonical import ContractError, canonical_bytes, fingerprint
from .identity import identifier
from .waves import WAVE_ORDER

_HEX = frozenset("0123456789abcdef")
_FIELDS = frozenset({"operation_id", "tenant", "principal", "wave",
                    "kind", "source_digest", "max_steps", "request"})

@dataclass(frozen=True)
class Envelope:
    operation_id: str
    tenant: str
    principal: str
    wave: str
    kind: str
    source_digest: str
    max_steps: int
    request: dict[str, Any]

    def __post_init__(self) -> None:
        for name in (self.operation_id, self.tenant, self.principal, self.kind):
            identifier(name)
        if self.wave not in WAVE_ORDER:
            raise ContractError("unknown operation wave")
        if (not isinstance(self.source_digest, str) or len(self.source_digest) != 64
                or set(self.source_digest) - _HEX):
            raise ContractError("source digest not SHA256")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 100000:
            raise ContractError("invalid step ceiling")
        if type(self.request) is not dict:
            raise ContractError("request must be object")
        canonical_bytes(self.request)

    def as_dict(self) -> dict[str, Any]:
        return {"operation_id": self.operation_id, "tenant": self.tenant,
                "principal": self.principal, "wave": self.wave, "kind": self.kind,
                "source_digest": self.source_digest, "max_steps": self.max_steps,
                "request": self.request}

    @property
    def digest(self) -> str:
        return fingerprint(self.as_dict())

def parse_envelope(value: dict[str, Any]) -> Envelope:
    if not isinstance(value, dict) or frozenset(value) != _FIELDS:
        raise ContractError("envelope has unknown or missing keys")
    return Envelope(**value)
