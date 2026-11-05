"""Strict host-side contracts for offline Jeeves operational subsystems.

No runtime contract is a model permission. All records are deliberately
JSON round-trippable and hash bound to a tenant/subject/model, with finite
resource ceilings and no fallback interpretation of missing information.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
import re
import time
from typing import Any, Mapping

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
_SCHEMAS = {"jeeves.fabric.scope.v1", "jeeves.fabric.proof.v1"}


class ContractHold(ValueError):
    """Invalid, unapproved or ambiguous operational contract."""


def identifier(value: object, label: str = "identifier") -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ContractHold("invalid " + label)
    return value


def digest(value: object) -> str:
    if type(value) is not str or not _SHA.fullmatch(value):
        raise ContractHold("invalid sha256 digest")
    return value


def finite(value: object, *, minimum: float = 0, maximum: float = 1e12) -> float:
    if type(value) not in (int, float):
        raise ContractHold("finite numeric value required")
    numeric = float(value)
    if not math.isfinite(numeric) or not minimum <= numeric <= maximum:
        raise ContractHold("numeric value outside admission ceiling")
    return numeric


def exact_integer(value: object, *, minimum: int = 0, maximum: int = 1_000_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ContractHold("bounded integer required")
    return value


def text(value: object, *, maximum_bytes: int = 32768, may_be_empty: bool = False) -> str:
    if type(value) is not str:
        raise ContractHold("UTF-8 text required")
    try:
        raw = value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise ContractHold("text contains invalid Unicode") from exc
    if (not may_be_empty and not value.strip()) or len(raw) > maximum_bytes:
        raise ContractHold("text violates finite UTF-8 ceiling")
    if "\x00" in value:
        raise ContractHold("NUL forbidden in host text")
    return value


def canonical_bytes(value: object, *, max_bytes: int = 1_048_576) -> bytes:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (ValueError, TypeError, OverflowError, UnicodeError) as exc:
        raise ContractHold("value has no canonical JSON representation") from exc
    if len(encoded) > max_bytes:
        raise ContractHold("canonical JSON exceeds byte ceiling")
    return encoded


def fingerprint(value: object) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def parse_json(data: bytes, *, max_bytes: int = 1_048_576) -> object:
    if type(data) is not bytes or not 1 <= len(data) <= max_bytes:
        raise ContractHold("bounded JSON bytes required")
    try:
        def pair_hook(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ContractHold("duplicate JSON key")
                result[key] = value
            return result
        def reject_constant(value):
            raise ContractHold("nonfinite JSON constant")
        result = json.loads(data.decode("utf-8", "strict"),
                            object_pairs_hook=pair_hook,
                            parse_constant=reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ContractHold("invalid strict JSON") from exc
    return result


@dataclass(frozen=True, slots=True)
class Scope:
    tenant: str
    subject: str
    model_sha256: str
    tokenizer_sha256: str
    workspace: str = "default"
    session: str | None = None

    def __post_init__(self):
        identifier(self.tenant, "tenant")
        identifier(self.subject, "subject")
        identifier(self.workspace, "workspace")
        digest(self.model_sha256)
        digest(self.tokenizer_sha256)
        if self.session is not None:
            identifier(self.session, "session")

    @property
    def principal(self) -> tuple[str, str]:
        return self.tenant, self.subject

    @property
    def binding(self) -> str:
        return fingerprint({
            "schema": "jeeves.fabric.scope.v1",
            "tenant": self.tenant, "subject": self.subject,
            "workspace": self.workspace, "session": self.session,
            "model": self.model_sha256, "tokenizer": self.tokenizer_sha256,
        })

    def matches(self, other: "Scope", *, require_session: bool = True) -> bool:
        if not isinstance(other, Scope):
            return False
        if require_session:
            return self == other
        return (
            self.tenant, self.subject, self.model_sha256,
            self.tokenizer_sha256, self.workspace,
        ) == (
            other.tenant, other.subject, other.model_sha256,
            other.tokenizer_sha256, other.workspace,
        )


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    input_bytes: int = 32768
    output_bytes: int = 131072
    context_tokens: int = 4096
    output_tokens: int = 512
    model_calls: int = 8
    tool_calls: int = 0
    work_items: int = 128
    deadline_ms: int = 90000

    def __post_init__(self):
        for name, maximum in (
            ("input_bytes", 1048576), ("output_bytes", 2097152),
            ("context_tokens", 131072), ("output_tokens", 8192),
            ("model_calls", 10000), ("tool_calls", 10000),
            ("work_items", 100000), ("deadline_ms", 600000),
        ):
            exact_integer(getattr(self, name), minimum=0, maximum=maximum)
        if self.input_bytes == 0 or self.output_bytes == 0:
            raise ContractHold("nonzero input/output budgets required")
        if not 128 <= self.context_tokens or not 1 <= self.output_tokens < self.context_tokens:
            raise ContractHold("native context/output limits inconsistent")
        if self.deadline_ms < 1:
            raise ContractHold("monotonic deadline required")

    def to_record(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in (
            "input_bytes", "output_bytes", "context_tokens", "output_tokens",
            "model_calls", "tool_calls", "work_items", "deadline_ms",
        )}


@dataclass(frozen=True, slots=True)
class Verdict:
    accepted: bool
    code: str
    reasons: tuple[str, ...]
    evidence: tuple[str, ...] = ()
    pending: bool = False

    def __post_init__(self):
        if type(self.accepted) is not bool or type(self.pending) is not bool:
            raise ContractHold("strict boolean verdict required")
        identifier(self.code, "verdict code")
        if type(self.reasons) is not tuple or len(self.reasons) > 32:
            raise ContractHold("bounded reason tuple required")
        for reason in self.reasons:
            text(reason, maximum_bytes=1024)
        if type(self.evidence) is not tuple or len(self.evidence) > 64:
            raise ContractHold("bounded evidence tuple required")
        for item in self.evidence:
            digest(item)
        if self.accepted and (self.pending or self.reasons):
            raise ContractHold("accepted verdict cannot contain unresolved holds")

    @classmethod
    def hold(cls, code: str, *reasons: str) -> "Verdict":
        return cls(False, identifier(code), tuple(reasons or ("unresolved",)))

    @classmethod
    def allow(cls, code: str, *evidence: str) -> "Verdict":
        return cls(True, identifier(code), (), tuple(evidence))


@dataclass(frozen=True, slots=True)
class Proof:
    scope: Scope
    payload_sha256: str
    issuer: str
    purpose: str
    issued_at: int
    expires_at: int
    facts: Mapping[str, object] = field(default_factory=dict)
    operator_approved: bool = False

    def __post_init__(self):
        if not isinstance(self.scope, Scope):
            raise ContractHold("typed principal scope required")
        digest(self.payload_sha256)
        identifier(self.issuer, "issuer")
        identifier(self.purpose, "purpose")
        exact_integer(self.issued_at, maximum=4102444800)
        exact_integer(self.expires_at, maximum=4102444800)
        if self.expires_at <= self.issued_at:
            raise ContractHold("expired-before-issued proof")
        if type(self.operator_approved) is not bool:
            raise ContractHold("explicit approval boolean required")
        if type(self.facts) is not dict or len(self.facts) > 64:
            raise ContractHold("bounded proof facts mapping required")
        canonical_bytes(self.facts, max_bytes=16384)

    def valid_at(self, when: int, *, scope: Scope | None = None) -> Verdict:
        exact_integer(when, maximum=4102444800)
        if scope is not None and self.scope != scope:
            return Verdict.hold("scope_mismatch", "proof belongs to different principal")
        if not self.issued_at <= when < self.expires_at:
            return Verdict.hold("proof_expired", "approval is not current")
        if not self.operator_approved:
            return Verdict.hold("approval_missing", "operator has not approved the operation")
        return Verdict.allow("bounded_approval", self.payload_sha256)

    def to_public_record(self) -> dict[str, object]:
        # These are assertions held by the issuer, not verification of model
        # rights, binary signatures, material quality, or legal provenance.
        return {
            "schema": "jeeves.fabric.proof.v1", "scope_sha256": self.scope.binding,
            "payload_sha256": self.payload_sha256,
            "issuer": self.issuer, "purpose": self.purpose,
            "issued_at": self.issued_at, "expires_at": self.expires_at,
            "operator_approved": self.operator_approved,
            "source_rights_independently_verified": False,
            "release_certified": False,
        }


def require_same_scope(expected: Scope, actual: Scope) -> None:
    if not isinstance(expected, Scope) or not expected.matches(actual):
        raise ContractHold("cross-principal or cross-model operational data")


def bounded_mapping(value: object, *, fields: set[str], required: set[str] = frozenset()) -> dict:
    if type(value) is not dict or not required <= set(value) or not set(value) <= fields:
        raise ContractHold("unknown or absent contract fields")
    canonical_bytes(value)
    return dict(value)


__all__ = [
    "ContractHold", "identifier", "digest", "finite", "exact_integer",
    "text", "canonical_bytes", "parse_json", "fingerprint",
    "Scope", "ResourceLimits", "Verdict", "Proof",
    "require_same_scope", "bounded_mapping",
]
