"""Typed receipt, evidence hashes and immutable causal parents."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .canonical import ContractError, canonical_bytes, fingerprint
from .identity import identifier

@dataclass(frozen=True)
class Receipt:
    operation_id: str
    sequence: int
    status: str
    request_digest: str
    result_digest: str
    parent_digest: str | None

    def __post_init__(self) -> None:
        identifier(self.operation_id)
        if type(self.sequence) is not int or self.sequence < 0:
            raise ContractError("invalid receipt sequence")
        if self.status not in ("admitted", "committed", "denied", "failed", "aborted"):
            raise ContractError("unknown receipt status")
        for value in (self.request_digest, self.result_digest, self.parent_digest):
            if value is not None and (not isinstance(value, str) or len(value) != 64 or
                                      set(value) - frozenset("0123456789abcdef")):
                raise ContractError("invalid receipt hash")

    def as_dict(self) -> dict[str, Any]:
        return {"operation_id": self.operation_id, "sequence": self.sequence,
                "status": self.status, "request_digest": self.request_digest,
                "result_digest": self.result_digest, "parent_digest": self.parent_digest}

    @property
    def digest(self) -> str:
        return fingerprint(self.as_dict())

def receipt_for(operation_id: str, sequence: int, status: str,
                request: dict[str, Any], result: dict[str, Any],
                previous: Receipt | None = None) -> Receipt:
    canonical_bytes(request)
    canonical_bytes(result)
    return Receipt(operation_id, sequence, status, fingerprint(request),
                   fingerprint(result), previous.digest if previous else None)
