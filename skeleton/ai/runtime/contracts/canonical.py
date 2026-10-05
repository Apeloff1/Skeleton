"""Canonical bounded JSON contract primitives for automation planes.

This module defines the shared data boundary between planning, admission,
execution, and assurance layers. It carries evidence and intent; it does not
carry execution authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping


SUPPORTED_SCHEMA_VERSIONS = frozenset({1})
MAX_PAYLOAD_BYTES = 48_000


class CanonicalContractError(ValueError):
    """Raised when a canonical envelope violates its contract."""


def _validate_mapping_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if type(key) is not str:
                raise CanonicalContractError("canonical mappings require string keys")
            _validate_mapping_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _validate_mapping_keys(child)


def canonical_json_bytes(value: Any) -> bytes:
    """Return one strict deterministic JSON byte representation."""
    _validate_mapping_keys(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanonicalContractError("value is not strict canonical JSON") from exc


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
    raw = canonical_json_bytes(
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
        raw = canonical_json_bytes(self.payload)
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
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_payload())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()



def canonical_conformance_vector(envelope: CanonicalEnvelope) -> Mapping[str, object]:
    """Materialize a deterministic conformance vector without granting authority."""
    if not isinstance(envelope, CanonicalEnvelope):
        raise CanonicalContractError("envelope must be CanonicalEnvelope")
    payload = envelope.canonical_payload()
    return {
        "schema_version": envelope.schema_version,
        "kind": envelope.kind,
        "canonical_hex": envelope.canonical_bytes.hex(),
        "digest": envelope.digest,
        "payload_bytes": len(canonical_json_bytes(envelope.payload)),
        "evidence_identities": tuple(item.identity for item in envelope.evidence),
        "constraints": tuple(payload["constraints"]),
        "authority_scope": "contract-conformance-only",
    }
