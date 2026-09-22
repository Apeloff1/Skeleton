"""Canonical bounded JSON contract primitives for automation planes.

This module defines the shared data boundary between planning, admission,
execution, and assurance layers. It carries evidence and intent; it does not
carry execution authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


SUPPORTED_SCHEMA_VERSIONS = frozenset({1})
MAX_PAYLOAD_BYTES = 48_000


class CanonicalContractError(ValueError):
    """Raised when a canonical envelope violates its contract."""


@dataclass(frozen=True, slots=True)
class Identity:
    repository: str
    commit_sha: str
    run_id: str = ""
    run_attempt: str = ""


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    source: str
    digest: str
    category: str = "repository_state"


@dataclass(frozen=True, slots=True)
class CanonicalEnvelope:
    schema_version: int
    kind: str
    identity: Identity
    evidence: tuple[EvidenceRef, ...]
    constraints: tuple[str, ...]
    payload: dict[str, Any]

    def canonical_payload(self) -> dict[str, Any]:
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise CanonicalContractError("unsupported schema version")
        if not self.kind:
            raise CanonicalContractError("missing envelope kind")
        raw = json.dumps(
            self.payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(raw) > MAX_PAYLOAD_BYTES:
            raise CanonicalContractError("payload exceeds byte budget")
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "identity": asdict(self.identity),
            "evidence": [asdict(item) for item in self.evidence],
            "constraints": sorted(set(self.constraints)),
            "payload": self.payload,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
