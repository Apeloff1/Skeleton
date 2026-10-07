"""Validated outcome receipts for autonomous work."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass, asdict
from typing import Any, Mapping

SCHEMA="autonomous-studio.outcome.v1"

@dataclass(frozen=True)
class OutcomeReceipt:
    allocation_sha256: str
    allocation_nonce: str
    task_id: str
    lane_id: str
    candidate_patch_sha256: str
    applied_diff_sha256: str
    validation_passed: bool
    validation_commands: tuple[tuple[str,...], ...]
    schema: str = SCHEMA

    def payload(self) -> dict[str, Any]:
        return asdict(self)

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.payload(),sort_keys=True,separators=(",",":")).encode()).hexdigest()

def verify_outcome(payload: Mapping[str, Any], expected_allocation: str) -> None:
    if payload.get("schema") != SCHEMA: raise ValueError("outcome schema mismatch")
    if payload.get("allocation_sha256") != expected_allocation: raise ValueError("outcome allocation mismatch")
    for field in ("candidate_patch_sha256","applied_diff_sha256"):
        value=str(payload.get(field,""))
        if len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value): raise ValueError(f"malformed {field}")
