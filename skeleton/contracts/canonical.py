"""Canonical bounded JSON contract primitives for automation planes.

This module defines the shared data boundary between planning, admission,
execution, and assurance layers. It carries evidence and intent; it does not
carry execution authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping


SUPPORTED_SCHEMA_VERSIONS = frozenset({1})
MAX_PAYLOAD_BYTES = 48_000
MAX_PORTABLE_INTEGER = 9_007_199_254_740_991


class CanonicalContractError(ValueError):
    """Raised when a canonical envelope violates its contract."""


MAX_CANONICAL_DEPTH = 64


def _unicode_scalar_text(value: str) -> None:
    """Forbid lone UTF-16 surrogates: not interoperable UTF-8/JSON text."""
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise CanonicalContractError("unpaired Unicode surrogate in canonical JSON")


def _validate_mapping_keys(
    value: Any,
    *,
    _depth: int = 0,
    _active: set[int] | None = None,
) -> None:
    """Bound traversals and reject cyclic structures before json.dumps."""
    if _depth > MAX_CANONICAL_DEPTH:
        raise CanonicalContractError("canonical JSON nesting depth exceeded")
    if not isinstance(value, (dict, list, tuple)):
        return
    active = _active if _active is not None else set()
    marker = id(value)
    if marker in active:
        raise CanonicalContractError("cyclic canonical JSON structure")
    active.add(marker)
    try:
        if isinstance(value, dict):
            for key, child in value.items():
                if type(key) is not str:
                    raise CanonicalContractError("canonical mappings require string keys")
                _unicode_scalar_text(key)
                _validate_mapping_keys(child, _depth=_depth + 1, _active=active)
        else:
            for child in value:
                _validate_mapping_keys(child, _depth=_depth + 1, _active=active)
    finally:
        active.remove(marker)


def _validate_portable_json_scalars(value: Any, *, _depth: int = 0) -> None:
    """Reject JSON scalars with nonportable text/numeric representation."""
    if _depth > MAX_CANONICAL_DEPTH:
        raise CanonicalContractError("canonical JSON nesting depth exceeded")
    if isinstance(value, dict):
        for child in value.values():
            _validate_portable_json_scalars(child, _depth=_depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _validate_portable_json_scalars(child, _depth=_depth + 1)
        return
    if isinstance(value, str):
        _unicode_scalar_text(value)
    if type(value) is int and abs(value) > MAX_PORTABLE_INTEGER:
        raise CanonicalContractError("integer exceeds portable JSON range")
    if type(value) is float:
        if not math.isfinite(value):
            raise CanonicalContractError("non-finite numbers are not canonical JSON")
        if value == 0.0 and math.copysign(1.0, value) < 0:
            raise CanonicalContractError("negative zero is not portable canonical JSON")


def canonical_json_bytes(value: Any) -> bytes:
    """Return one strict deterministic JSON byte representation."""
    _validate_mapping_keys(value)
    _validate_portable_json_scalars(value)
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
        # bool and 1.0 compare equal to integer 1 in Python; neither is an
        # acceptable serialized schema version at an authority boundary.
        if type(self.schema_version) is not int or self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise CanonicalContractError("unsupported schema version")
        if not isinstance(self.kind, str) or not self.kind or not self.kind.strip():
            raise CanonicalContractError("missing envelope kind")
        if not isinstance(self.identity, Identity):
            raise CanonicalContractError("envelope identity must be Identity")
        for label, value in (
            ("identity.repository", self.identity.repository),
            ("identity.commit_sha", self.identity.commit_sha),
            ("identity.run_id", self.identity.run_id),
            ("identity.run_attempt", self.identity.run_attempt),
        ):
            if not isinstance(value, str) or (label in {"identity.repository", "identity.commit_sha"} and not value.strip()):
                raise CanonicalContractError(f"{label} must be text")
            _unicode_scalar_text(value)
        if not isinstance(self.evidence, tuple) or any(
            not isinstance(item, EvidenceRef) for item in self.evidence
        ):
            raise CanonicalContractError("envelope evidence must contain EvidenceRef")
        for item in self.evidence:
            for label, value in (
                ("evidence.source", item.source),
                ("evidence.digest", item.digest),
                ("evidence.category", item.category),
            ):
                if not isinstance(value, str) or not value.strip():
                    raise CanonicalContractError(f"{label} must be non-empty text")
                _unicode_scalar_text(value)
        if not isinstance(self.constraints, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.constraints
        ):
            raise CanonicalContractError("envelope constraints must be non-empty strings")
        for constraint in self.constraints:
            _unicode_scalar_text(constraint)
        if not isinstance(self.payload, dict):
            raise CanonicalContractError("envelope payload must be an object")
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
