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



def _canonical_json_bytes(value: Any) -> bytes:
    """Encode strict JSON deterministically for digests/signing inputs."""
    def check(item: Any) -> None:
        if item is None or isinstance(item, (str, bool, int)):
            return
        if isinstance(item, float):
            if item != item or item in {float("inf"), float("-inf")}:
                raise CanonicalContractError("non-finite numbers are not canonical JSON")
            return
        if isinstance(item, list):
            for child in item:
                check(child)
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise CanonicalContractError("canonical JSON object keys must be strings")
                check(child)
            return
        raise CanonicalContractError("canonical contract values must be strict JSON")

    check(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanonicalContractError("value cannot be canonicalized as JSON") from exc


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

    @property
    def identity(self) -> str:
        """Stable content identity for generic canonical evidence references."""
        return evidence_ref_identity(self)


def evidence_ref_identity(evidence: EvidenceRef) -> str:
    """Hash canonical evidence-ref metadata without inventing a second ID field."""
    if not isinstance(evidence, EvidenceRef):
        raise CanonicalContractError("evidence must be EvidenceRef")
    raw = _canonical_json_bytes(
        {
            "source": evidence.source,
            "digest": evidence.digest,
            "category": evidence.category,
        }
    )
    return hashlib.sha256(raw).hexdigest()


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
        raw = _canonical_json_bytes(self.payload)
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
        raw = _canonical_json_bytes(self.canonical_payload())
        return hashlib.sha256(raw).hexdigest()
