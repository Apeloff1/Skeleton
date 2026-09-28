"""Versioned API contract registry and compatibility evaluator.

P1-PROD-01 owns *descriptions* of externally visible API contracts.  It does
not register FastAPI routes or mutate runtime state.  Release tooling can
compare two immutable registries and reject unacknowledged breaking drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef


API_CONTRACT_SCHEMA_VERSION = 1
API_CONTRACT_TASK_ID = "P1-PROD-01"
API_CONTRACT_ACCOUNTABILITY_ID = "ACC-P1-PROD-01"

_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_MAX_CONSUMERS = 256


class ApiContractError(ValueError):
    """API contract metadata is malformed or compatibility cannot be proven."""


class CompatibilityClass(str, Enum):
    ADDITIVE = "additive"
    COMPATIBLE = "compatible"
    BREAKING = "breaking"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ApiContractError(f"{field} must be a canonical token")
    return value


def _path(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("/") or "//" in value:
        raise ApiContractError("path must be an absolute normalized API path")
    if value != "/" and value.endswith("/"):
        raise ApiContractError("path must not have a trailing slash")
    if any(ch.isspace() for ch in value):
        raise ApiContractError("path must not contain whitespace")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ApiContractError(f"{field} must be lowercase sha256")
    return value


def _consumers(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ApiContractError("consumers must be an iterable")
    items = tuple(sorted({_token(value, "consumer") for value in values}))
    if not items:
        raise ApiContractError("consumers must be non-empty")
    if len(items) > _MAX_CONSUMERS:
        raise ApiContractError("consumer count exceeds limit")
    return items


def _canonical_digest(value: Any) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ApiContractError("API contract payload must be canonical JSON") from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ApiContract:
    contract_id: str
    version: int
    method: str
    path: str
    producer: str
    consumers: tuple[str, ...]
    request_schema_digest: str
    response_schema_digest: str
    tenant_scoped: bool
    idempotent: bool
    schema_version: int = API_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_id", _token(self.contract_id, "contract_id"))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ApiContractError("version must be a positive integer")
        method = str(self.method).upper()
        if method not in _METHODS:
            raise ApiContractError("method is unsupported")
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "path", _path(self.path))
        object.__setattr__(self, "producer", _token(self.producer, "producer"))
        object.__setattr__(self, "consumers", _consumers(self.consumers))
        object.__setattr__(
            self,
            "request_schema_digest",
            _digest(self.request_schema_digest, "request_schema_digest"),
        )
        object.__setattr__(
            self,
            "response_schema_digest",
            _digest(self.response_schema_digest, "response_schema_digest"),
        )
        if not isinstance(self.tenant_scoped, bool) or not isinstance(self.idempotent, bool):
            raise ApiContractError("tenant_scoped and idempotent must be boolean")
        if self.schema_version != API_CONTRACT_SCHEMA_VERSION:
            raise ApiContractError("unsupported API contract schema version")

    @property
    def operation_key(self) -> str:
        return f"{self.method} {self.path}"

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "version": self.version,
            "method": self.method,
            "path": self.path,
            "producer": self.producer,
            "consumers": list(self.consumers),
            "request_schema_digest": self.request_schema_digest,
            "response_schema_digest": self.response_schema_digest,
            "tenant_scoped": self.tenant_scoped,
            "idempotent": self.idempotent,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.identity_payload())


@dataclass(frozen=True, slots=True)
class MigrationRule:
    contract_id: str
    from_version: int
    to_version: int
    compatibility: CompatibilityClass
    migration_id: str
    expires_at_epoch: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_id", _token(self.contract_id, "contract_id"))
        for field in ("from_version", "to_version"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ApiContractError(f"{field} must be a positive integer")
        if self.to_version <= self.from_version:
            raise ApiContractError("migration to_version must advance")
        try:
            object.__setattr__(self, "compatibility", CompatibilityClass(self.compatibility))
        except ValueError as exc:
            raise ApiContractError("invalid compatibility class") from exc
        object.__setattr__(self, "migration_id", _token(self.migration_id, "migration_id"))
        if self.expires_at_epoch is not None and (
            isinstance(self.expires_at_epoch, bool)
            or not isinstance(self.expires_at_epoch, int)
            or self.expires_at_epoch <= 0
        ):
            raise ApiContractError("expires_at_epoch must be a positive integer")


@dataclass(frozen=True, slots=True)
class ApiCompatibilityDecision:
    accepted: bool
    baseline_digest: str
    candidate_digest: str
    breaking: tuple[str, ...]
    incompatible: tuple[str, ...]
    additive: tuple[str, ...]
    unchanged: tuple[str, ...]
    task_id: str = API_CONTRACT_TASK_ID
    accountability_id: str = API_CONTRACT_ACCOUNTABILITY_ID

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(
            {
                "task_id": self.task_id,
                "accountability_id": self.accountability_id,
                "baseline_digest": self.baseline_digest,
                "candidate_digest": self.candidate_digest,
                "accepted": self.accepted,
                "breaking": list(self.breaking),
                "incompatible": list(self.incompatible),
                "additive": list(self.additive),
                "unchanged": list(self.unchanged),
            }
        )

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise ApiContractError(
                "rejected API compatibility decision cannot become promotion evidence"
            )
        return EvidenceRef(
            source="p1:prod-01:api-contract-compatibility",
            digest=self.decision_digest,
            category="api_contract_compatibility",
        )


def registry_digest(contracts: Iterable[ApiContract]) -> str:
    rows = sorted(
        (contract.identity_payload() for contract in contracts),
        key=lambda row: (row["contract_id"], row["version"]),
    )
    return _canonical_digest({"contracts": rows})


def _index(
    contracts: Iterable[ApiContract],
    *,
    allow_empty: bool = False,
) -> dict[str, ApiContract]:
    result: dict[str, ApiContract] = {}
    operation_keys: set[str] = set()
    for contract in contracts:
        if not isinstance(contract, ApiContract):
            raise ApiContractError("registry entries must be ApiContract")
        if contract.contract_id in result:
            raise ApiContractError(f"duplicate contract_id: {contract.contract_id}")
        if contract.operation_key in operation_keys:
            raise ApiContractError(f"duplicate operation: {contract.operation_key}")
        result[contract.contract_id] = contract
        operation_keys.add(contract.operation_key)
    if not result and not allow_empty:
        raise ApiContractError("registry must be non-empty")
    return result


def evaluate_compatibility(
    baseline: Iterable[ApiContract],
    candidate: Iterable[ApiContract],
    *,
    migrations: Iterable[MigrationRule] = (),
    observed_at_epoch: int,
) -> ApiCompatibilityDecision:
    if isinstance(observed_at_epoch, bool) or not isinstance(observed_at_epoch, int) or observed_at_epoch < 0:
        raise ApiContractError("observed_at_epoch must be a non-negative integer")

    before = _index(tuple(baseline))
    after = _index(tuple(candidate), allow_empty=True)
    rules: dict[tuple[str, int, int], MigrationRule] = {}
    for rule in migrations:
        if not isinstance(rule, MigrationRule):
            raise ApiContractError("migrations must contain MigrationRule")
        key = (rule.contract_id, rule.from_version, rule.to_version)
        if key in rules:
            raise ApiContractError("duplicate migration rule")
        rules[key] = rule

    breaking: list[str] = []
    incompatible: list[str] = []
    additive: list[str] = []
    unchanged: list[str] = []

    for contract_id, old in before.items():
        new = after.get(contract_id)
        if new is None:
            breaking.append(f"{contract_id}:removed")
            continue
        if new.version < old.version:
            incompatible.append(f"{contract_id}:version-regressed")
            continue

        schema_change = (
            old.request_schema_digest != new.request_schema_digest
            or old.response_schema_digest != new.response_schema_digest
        )
        consumer_loss = bool(set(old.consumers) - set(new.consumers))
        producer_change = old.producer != new.producer
        operation_move = old.method != new.method or old.path != new.path
        authority_change = old.tenant_scoped != new.tenant_scoped
        idempotency_change = old.idempotent != new.idempotent
        if not any(
            (
                schema_change,
                consumer_loss,
                producer_change,
                operation_move,
                authority_change,
                idempotency_change,
            )
        ):
            unchanged.append(contract_id)
            continue

        if operation_move:
            breaking.append(f"{contract_id}:operation-moved")
            continue
        if authority_change:
            breaking.append(f"{contract_id}:tenant-scope-semantics-changed")
            continue
        if idempotency_change:
            breaking.append(f"{contract_id}:idempotency-semantics-changed")
            continue
        if consumer_loss:
            breaking.append(f"{contract_id}:consumer-removed")
            continue
        if new.version <= old.version:
            breaking.append(f"{contract_id}:changed-without-version-advance")
            continue

        rule = rules.get((contract_id, old.version, new.version))
        if rule is None:
            breaking.append(f"{contract_id}:missing-migration-rule")
            continue
        if rule.compatibility is CompatibilityClass.BREAKING:
            breaking.append(f"{contract_id}:declared-breaking")
            continue
        if rule.expires_at_epoch is not None and observed_at_epoch >= rule.expires_at_epoch:
            breaking.append(f"{contract_id}:migration-window-expired")
            continue

    for contract_id in sorted(set(after) - set(before)):
        additive.append(contract_id)

    accepted = not breaking and not incompatible
    return ApiCompatibilityDecision(
        accepted=accepted,
        baseline_digest=registry_digest(before.values()),
        candidate_digest=registry_digest(after.values()),
        breaking=tuple(sorted(breaking)),
        incompatible=tuple(sorted(incompatible)),
        additive=tuple(sorted(additive)),
        unchanged=tuple(sorted(unchanged)),
    )


__all__ = [
    "API_CONTRACT_ACCOUNTABILITY_ID",
    "API_CONTRACT_SCHEMA_VERSION",
    "API_CONTRACT_TASK_ID",
    "ApiCompatibilityDecision",
    "ApiContract",
    "ApiContractError",
    "CompatibilityClass",
    "MigrationRule",
    "evaluate_compatibility",
    "registry_digest",
]
