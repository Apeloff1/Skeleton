"""Canonical control-plane / data-plane isolation contract for hostile gap G013.

Plane role is not inferred from package names. It is derived from the canonical
architecture execution profile and pinned in machine/control_data_plane_contract.json.

Cross-role exchanges are reference-only:
* raw tenant payload is never carried by a control-role boundary request;
* data -> control is restricted to bounded policy/admission/evidence queries;
* control -> data is restricted to authority/configuration/execution decisions;
* control -> data decisions require an exact authority receipt digest;
* unknown planes and cross-role operations fail closed.

This module does not replace authorization inside each plane. It is the
structural boundary that prevents a data processor from silently becoming a
control authority, or a control path from becoming a raw-data transport.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


SCHEMA = "skeleton.ai.control_data_plane_contract.v1"
CONTROL_ROLE = "control"
DATA_ROLE = "data"
ROLES = frozenset({CONTROL_ROLE, DATA_ROLE})
CONTROL_PROFILES = frozenset(
    {"policy-control", "evidence-control", "release-control"}
)
DATA_PROFILES = frozenset(
    {
        "durable-state",
        "durable-worker",
        "library",
        "product-client",
        "provider-edge",
        "realtime-transport",
        "request-service",
    }
)
DATA_TO_CONTROL_OPERATIONS = (
    "admission.request",
    "evidence.report",
    "policy.query",
)
CONTROL_TO_DATA_OPERATIONS = (
    "authority.decision",
    "configuration.reference",
    "execution.permit",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ControlDataIsolationError(RuntimeError):
    """Control/data plane isolation contract is malformed or violated."""


def _text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ControlDataIsolationError(
            f"{field} must be canonical non-empty text"
        )
    if len(value) > maximum:
        raise ControlDataIsolationError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ControlDataIsolationError(f"{field} contains control characters")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ControlDataIsolationError(
            f"{field} must be canonical lowercase SHA-256"
        )
    return value


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ControlDataIsolationError(
            "plane isolation payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sorted_text_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ControlDataIsolationError(f"{field} must be a list")
    result = tuple(sorted({_text(item, field) for item in value}))
    if list(result) != value:
        raise ControlDataIsolationError(
            f"{field} must be sorted and duplicate-free"
        )
    return result


@dataclass(frozen=True, slots=True)
class PlaneExpectation:
    plane: str
    owner: str
    zone: str
    profile: str
    role: str

    @classmethod
    def from_mapping(
        cls,
        plane: str,
        raw: Mapping[str, Any],
    ) -> "PlaneExpectation":
        required = {"owner", "zone", "profile", "role"}
        if set(raw) != required:
            raise ControlDataIsolationError(
                f"{plane} expectation schema drift"
            )
        role = _text(raw["role"], f"{plane}.role")
        if role not in ROLES:
            raise ControlDataIsolationError(f"{plane} has invalid role")
        return cls(
            plane=_text(plane, "plane"),
            owner=_text(raw["owner"], f"{plane}.owner"),
            zone=_text(raw["zone"], f"{plane}.zone"),
            profile=_text(raw["profile"], f"{plane}.profile"),
            role=role,
        )

    def payload(self) -> dict[str, str]:
        return {
            "plane": self.plane,
            "owner": self.owner,
            "zone": self.zone,
            "profile": self.profile,
            "role": self.role,
        }


@dataclass(frozen=True, slots=True)
class IsolationContractReport:
    valid: bool
    errors: tuple[str, ...]
    plane_count: int
    control_planes: tuple[str, ...]
    data_planes: tuple[str, ...]
    contract_digest: str

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": "skeleton.ai.control_data_plane_report.v1",
            "valid": self.valid,
            "errors": list(self.errors),
            "plane_count": self.plane_count,
            "control_planes": list(self.control_planes),
            "data_planes": list(self.data_planes),
            "contract_digest": self.contract_digest,
        }


@dataclass(frozen=True, slots=True)
class CrossPlaneEnvelope:
    source_plane: str
    target_plane: str
    operation: str
    tenant_id: str
    resource_ref: str
    request_digest: str
    authority_receipt_digest: str | None = None
    raw_payload_present: bool = False

    def __post_init__(self) -> None:
        for field in (
            "source_plane",
            "target_plane",
            "operation",
            "tenant_id",
            "resource_ref",
        ):
            object.__setattr__(
                self,
                field,
                _text(getattr(self, field), field, maximum=2048),
            )
        object.__setattr__(
            self,
            "request_digest",
            _sha(self.request_digest, "request_digest"),
        )
        if self.authority_receipt_digest is not None:
            object.__setattr__(
                self,
                "authority_receipt_digest",
                _sha(
                    self.authority_receipt_digest,
                    "authority_receipt_digest",
                ),
            )
        if not isinstance(self.raw_payload_present, bool):
            raise ControlDataIsolationError(
                "raw_payload_present must be boolean"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "source_plane": self.source_plane,
            "target_plane": self.target_plane,
            "operation": self.operation,
            "tenant_id": self.tenant_id,
            "resource_ref": self.resource_ref,
            "request_digest": self.request_digest,
            "authority_receipt_digest": self.authority_receipt_digest,
            "raw_payload_present": self.raw_payload_present,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class BoundaryDecision:
    allowed: bool
    reason_code: str
    source_plane: str
    target_plane: str
    source_role: str | None
    target_role: str | None
    envelope_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise ControlDataIsolationError("allowed must be boolean")
        for field in (
            "reason_code",
            "source_plane",
            "target_plane",
            "envelope_digest",
        ):
            object.__setattr__(
                self,
                field,
                _text(getattr(self, field), field),
            )
        for field in ("source_role", "target_role"):
            value = getattr(self, field)
            if value is not None and value not in ROLES:
                raise ControlDataIsolationError(f"{field} invalid")

    def payload(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "source_plane": self.source_plane,
            "target_plane": self.target_plane,
            "source_role": self.source_role,
            "target_role": self.target_role,
            "envelope_digest": self.envelope_digest,
            "raw_payload_present": False,
        }


def validate_control_data_plane_contract(
    *,
    architecture: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> IsolationContractReport:
    errors: list[str] = []

    if contract.get("schema_version") != SCHEMA:
        errors.append("control/data plane schema drift")
    if contract.get("status") != "active":
        errors.append("control/data plane contract must be active")
    if contract.get("gap_id") != "G013":
        errors.append("control/data plane gap identity drift")
    if contract.get("architecture_contract") != "machine/architecture.json":
        errors.append("control/data plane architecture path drift")

    try:
        control_profiles = _sorted_text_list(
            contract.get("control_profiles"),
            "control_profiles",
        )
        data_profiles = _sorted_text_list(
            contract.get("data_profiles"),
            "data_profiles",
        )
    except ControlDataIsolationError as exc:
        errors.append(str(exc))
        control_profiles = ()
        data_profiles = ()

    if set(control_profiles) != CONTROL_PROFILES:
        errors.append("control profile classification drift")
    if set(data_profiles) != DATA_PROFILES:
        errors.append("data profile classification drift")
    if set(control_profiles) & set(data_profiles):
        errors.append("control/data profiles overlap")

    blueprint = architecture.get("structural_blueprint")
    if not isinstance(blueprint, Mapping):
        raise ControlDataIsolationError(
            "architecture structural_blueprint must be an object"
        )
    placements = blueprint.get("plane_placements")
    executions = blueprint.get("plane_execution")
    if not isinstance(placements, list) or not isinstance(executions, list):
        raise ControlDataIsolationError(
            "architecture plane placement/execution must be lists"
        )

    placement_by: dict[str, Mapping[str, Any]] = {}
    for raw in placements:
        if not isinstance(raw, Mapping):
            raise ControlDataIsolationError("plane placement must be object")
        plane = _text(raw.get("plane"), "placement.plane")
        if plane in placement_by:
            raise ControlDataIsolationError(
                f"duplicate architecture placement {plane}"
            )
        placement_by[plane] = raw

    execution_by: dict[str, Mapping[str, Any]] = {}
    for raw in executions:
        if not isinstance(raw, Mapping):
            raise ControlDataIsolationError("plane execution must be object")
        plane = _text(raw.get("plane"), "execution.plane")
        if plane in execution_by:
            raise ControlDataIsolationError(
                f"duplicate architecture execution {plane}"
            )
        execution_by[plane] = raw

    architecture_planes = set(placement_by)
    if architecture_planes != set(execution_by):
        errors.append("architecture placement/execution plane sets diverge")

    raw_expectations = contract.get("plane_expectations")
    if not isinstance(raw_expectations, Mapping):
        errors.append("plane_expectations must be an object")
        raw_expectations = {}

    expected_planes = set(raw_expectations)
    for missing in sorted(architecture_planes - expected_planes):
        errors.append(f"plane expectation missing: {missing}")
    for extra in sorted(expected_planes - architecture_planes):
        errors.append(f"unknown plane expectation: {extra}")

    parsed: dict[str, PlaneExpectation] = {}
    for plane in sorted(architecture_planes & expected_planes):
        raw = raw_expectations[plane]
        if not isinstance(raw, Mapping):
            errors.append(f"{plane} expectation must be an object")
            continue
        try:
            expectation = PlaneExpectation.from_mapping(plane, raw)
        except ControlDataIsolationError as exc:
            errors.append(str(exc))
            continue
        parsed[plane] = expectation
        placement = placement_by[plane]
        execution = execution_by.get(plane, {})
        actual_owner = placement.get("owner")
        actual_zone = placement.get("zone")
        actual_profile = execution.get("profile")
        for field, expected, actual in (
            ("owner", expectation.owner, actual_owner),
            ("zone", expectation.zone, actual_zone),
            ("profile", expectation.profile, actual_profile),
        ):
            if expected != actual:
                errors.append(
                    f"{plane} {field} drift: expected {expected}, got {actual}"
                )
        derived_role = (
            CONTROL_ROLE
            if expectation.profile in CONTROL_PROFILES
            else DATA_ROLE
            if expectation.profile in DATA_PROFILES
            else None
        )
        if derived_role is None:
            errors.append(
                f"{plane} execution profile is unclassified: "
                f"{expectation.profile}"
            )
        elif expectation.role != derived_role:
            errors.append(
                f"{plane} role drift: expected {derived_role}, "
                f"got {expectation.role}"
            )

    policy = contract.get("cross_role_policy")
    if not isinstance(policy, Mapping):
        errors.append("cross_role_policy must be an object")
    else:
        if policy.get("raw_payload_into_control_forbidden") is not True:
            errors.append("raw payload into control must be forbidden")
        if policy.get("cross_role_reference_only") is not True:
            errors.append("cross-role boundaries must be reference-only")
        if policy.get("control_to_data_requires_authority_receipt") is not True:
            errors.append(
                "control-to-data boundary must require authority receipt"
            )
        if policy.get("unknown_plane_fails_closed") is not True:
            errors.append("unknown planes must fail closed")
        try:
            d2c = _sorted_text_list(
                policy.get("data_to_control_operations"),
                "data_to_control_operations",
            )
            c2d = _sorted_text_list(
                policy.get("control_to_data_operations"),
                "control_to_data_operations",
            )
            if d2c != DATA_TO_CONTROL_OPERATIONS:
                errors.append("data-to-control operation set drift")
            if c2d != CONTROL_TO_DATA_OPERATIONS:
                errors.append("control-to-data operation set drift")
        except ControlDataIsolationError as exc:
            errors.append(str(exc))

    control_planes = tuple(
        sorted(
            plane
            for plane, expectation in parsed.items()
            if expectation.role == CONTROL_ROLE
        )
    )
    data_planes = tuple(
        sorted(
            plane
            for plane, expectation in parsed.items()
            if expectation.role == DATA_ROLE
        )
    )
    return IsolationContractReport(
        valid=not errors,
        errors=tuple(sorted(set(errors))),
        plane_count=len(architecture_planes),
        control_planes=control_planes,
        data_planes=data_planes,
        contract_digest=_canonical_digest(contract),
    )


class ControlDataIsolationPolicy:
    """Validated runtime view of the canonical plane-role boundary."""

    def __init__(self, contract: Mapping[str, Any]) -> None:
        raw = contract.get("plane_expectations")
        if not isinstance(raw, Mapping):
            raise ControlDataIsolationError(
                "plane_expectations must be an object"
            )
        self._roles: dict[str, str] = {}
        for plane, item in raw.items():
            if not isinstance(item, Mapping):
                raise ControlDataIsolationError(
                    "plane expectation must be an object"
                )
            expectation = PlaneExpectation.from_mapping(str(plane), item)
            self._roles[expectation.plane] = expectation.role

    def role(self, plane: str) -> str | None:
        return self._roles.get(_text(plane, "plane"))

    def evaluate(self, envelope: CrossPlaneEnvelope) -> BoundaryDecision:
        if not isinstance(envelope, CrossPlaneEnvelope):
            raise TypeError("envelope must be CrossPlaneEnvelope")
        source_role = self._roles.get(envelope.source_plane)
        target_role = self._roles.get(envelope.target_plane)
        if source_role is None or target_role is None:
            return BoundaryDecision(
                allowed=False,
                reason_code="unknown-plane",
                source_plane=envelope.source_plane,
                target_plane=envelope.target_plane,
                source_role=source_role,
                target_role=target_role,
                envelope_digest=envelope.digest,
            )

        if envelope.raw_payload_present and target_role == CONTROL_ROLE:
            return self._decision(
                envelope, source_role, target_role, False,
                "raw-payload-into-control",
            )

        if source_role != target_role and envelope.raw_payload_present:
            return self._decision(
                envelope, source_role, target_role, False,
                "cross-role-reference-only",
            )

        if source_role == target_role:
            return self._decision(
                envelope, source_role, target_role, True,
                "same-role-boundary",
            )

        if source_role == DATA_ROLE and target_role == CONTROL_ROLE:
            if envelope.operation not in DATA_TO_CONTROL_OPERATIONS:
                return self._decision(
                    envelope, source_role, target_role, False,
                    "data-to-control-operation-denied",
                )
            return self._decision(
                envelope, source_role, target_role, True,
                "bounded-data-to-control",
            )

        if source_role == CONTROL_ROLE and target_role == DATA_ROLE:
            if envelope.operation not in CONTROL_TO_DATA_OPERATIONS:
                return self._decision(
                    envelope, source_role, target_role, False,
                    "control-to-data-operation-denied",
                )
            if envelope.authority_receipt_digest is None:
                return self._decision(
                    envelope, source_role, target_role, False,
                    "authority-receipt-required",
                )
            return self._decision(
                envelope, source_role, target_role, True,
                "receipt-bound-control-to-data",
            )

        return self._decision(
            envelope, source_role, target_role, False,
            "role-transition-denied",
        )

    @staticmethod
    def _decision(
        envelope: CrossPlaneEnvelope,
        source_role: str,
        target_role: str,
        allowed: bool,
        reason: str,
    ) -> BoundaryDecision:
        return BoundaryDecision(
            allowed=allowed,
            reason_code=reason,
            source_plane=envelope.source_plane,
            target_plane=envelope.target_plane,
            source_role=source_role,
            target_role=target_role,
            envelope_digest=envelope.digest,
        )


def validate_repository_control_data_isolation(
    root: str | Path,
) -> IsolationContractReport:
    repository_root = Path(root)
    try:
        architecture = json.loads(
            (repository_root / "machine/architecture.json").read_text(
                encoding="utf-8"
            )
        )
        contract = json.loads(
            (
                repository_root
                / "machine/control_data_plane_contract.json"
            ).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlDataIsolationError(
            "cannot load control/data isolation machine contracts"
        ) from exc
    if not isinstance(architecture, Mapping) or not isinstance(contract, Mapping):
        raise ControlDataIsolationError(
            "control/data isolation machine contracts must be objects"
        )
    return validate_control_data_plane_contract(
        architecture=architecture,
        contract=contract,
    )


__all__ = [
    "BoundaryDecision",
    "CONTROL_PROFILES",
    "CONTROL_ROLE",
    "CONTROL_TO_DATA_OPERATIONS",
    "ControlDataIsolationError",
    "ControlDataIsolationPolicy",
    "CrossPlaneEnvelope",
    "DATA_PROFILES",
    "DATA_ROLE",
    "DATA_TO_CONTROL_OPERATIONS",
    "IsolationContractReport",
    "PlaneExpectation",
    "SCHEMA",
    "validate_control_data_plane_contract",
    "validate_repository_control_data_isolation",
]
