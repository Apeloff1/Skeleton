"""Control-plane/data-plane isolation contract for hostile gap G013.

The contract makes plane ownership explicit at the point where work crosses
from policy/configuration authority into tenant data execution, or where the
data plane reports observations back to the control plane.  It does not trust
network placement as an authority boundary.

Core laws
---------
* every principal belongs to exactly one plane and tenant;
* every action is registered in exactly one authority class;
* data-plane principals cannot mutate control-plane state;
* control-plane principals cannot read tenant payloads merely because they can
  dispatch work;
* cross-plane calls require explicit capabilities and an exact control-policy
  generation;
* permits are content-addressed, short-lived and bound to request/principal
  identity, payload/config digests and policy generation;
* observation ingress is append-only/non-mutating and cannot smuggle a control
  mutation under a telemetry action.

This module is transport agnostic.  RPC, queue and in-process adapters can all
use the same permit envelope before executing an effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
import time
from typing import Iterable


_SCHEMA = "skeleton.control_data_plane_isolation.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_NS = (1 << 63) - 1
_MAX_TTL_NS = 60 * 1_000_000_000


class PlaneIsolationError(RuntimeError):
    """Base control/data plane isolation failure."""


class PlaneIsolationDenied(PlaneIsolationError):
    """A requested cross-plane operation is not authorized."""


class PlanePermitStale(PlaneIsolationError):
    """A permit no longer matches current policy or time."""


class Plane(str, Enum):
    CONTROL = "control"
    DATA = "data"


class ActionClass(str, Enum):
    CONTROL_MUTATION = "control_mutation"
    DATA_OPERATION = "data_operation"
    DATA_OBSERVATION = "data_observation"


def _text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PlaneIsolationError(f"{field} must be canonical non-empty text")
    if len(value) > maximum:
        raise PlaneIsolationError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PlaneIsolationError(f"{field} contains control characters")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > _MAX_NS
    ):
        raise PlaneIsolationError(
            f"{field} must be an integer in [{minimum}, {_MAX_NS}]"
        )
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PlaneIsolationError(f"{field} must be canonical lowercase SHA-256")
    return value


def _canonical_digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PlaneIsolationError("permit payload must be canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _capabilities(values: Iterable[str]) -> tuple[str, ...]:
    try:
        normalized = tuple(sorted({_text(v, "capability") for v in values}))
    except TypeError as exc:
        raise PlaneIsolationError("capabilities must be iterable text") from exc
    if not normalized:
        raise PlaneIsolationError("principal requires at least one capability")
    return normalized


@dataclass(frozen=True, slots=True)
class PlanePrincipal:
    tenant_id: str
    principal_id: str
    plane: Plane
    capabilities: tuple[str, ...]
    authority_generation: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self, "principal_id", _text(self.principal_id, "principal_id")
        )
        try:
            plane = Plane(self.plane)
        except ValueError as exc:
            raise PlaneIsolationError("principal plane is invalid") from exc
        object.__setattr__(self, "plane", plane)
        canonical = _capabilities(self.capabilities)
        if canonical != self.capabilities:
            raise PlaneIsolationError(
                "principal capabilities must be sorted and duplicate-free"
            )
        object.__setattr__(
            self,
            "authority_generation",
            _integer(self.authority_generation, "authority_generation", minimum=1),
        )

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "schema": _SCHEMA,
                "tenant_id": self.tenant_id,
                "principal_id": self.principal_id,
                "plane": self.plane.value,
                "capabilities": list(self.capabilities),
                "authority_generation": self.authority_generation,
            }
        )


@dataclass(frozen=True, slots=True)
class PlaneRequest:
    request_id: str
    tenant_id: str
    source_plane: Plane
    target_plane: Plane
    action: str
    payload_digest: str
    config_digest: str
    control_generation: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))
        object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "action", _text(self.action, "action"))
        try:
            object.__setattr__(self, "source_plane", Plane(self.source_plane))
            object.__setattr__(self, "target_plane", Plane(self.target_plane))
        except ValueError as exc:
            raise PlaneIsolationError("request plane is invalid") from exc
        object.__setattr__(
            self, "payload_digest", _digest(self.payload_digest, "payload_digest")
        )
        object.__setattr__(
            self, "config_digest", _digest(self.config_digest, "config_digest")
        )
        object.__setattr__(
            self,
            "control_generation",
            _integer(self.control_generation, "control_generation", minimum=1),
        )


@dataclass(frozen=True, slots=True)
class PlanePermit:
    request_id: str
    tenant_id: str
    principal_digest: str
    source_plane: Plane
    target_plane: Plane
    action: str
    action_class: ActionClass
    payload_digest: str
    config_digest: str
    control_generation: int
    issued_at_ns: int
    expires_at_ns: int
    mutation_allowed: bool
    permit_digest: str

    def payload(self) -> dict[str, object]:
        return {
            "schema": _SCHEMA,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "principal_digest": self.principal_digest,
            "source_plane": self.source_plane.value,
            "target_plane": self.target_plane.value,
            "action": self.action,
            "action_class": self.action_class.value,
            "payload_digest": self.payload_digest,
            "config_digest": self.config_digest,
            "control_generation": self.control_generation,
            "issued_at_ns": self.issued_at_ns,
            "expires_at_ns": self.expires_at_ns,
            "mutation_allowed": self.mutation_allowed,
        }


class PlaneIsolationPolicy:
    """Exact-generation policy for control/data-plane crossings."""

    def __init__(
        self,
        *,
        control_generation: int,
        control_mutations: Iterable[str],
        data_operations: Iterable[str],
        data_observations: Iterable[str],
    ) -> None:
        self.control_generation = _integer(
            control_generation, "control_generation", minimum=1
        )
        self._control_mutations = self._actions(control_mutations, "control_mutations")
        self._data_operations = self._actions(data_operations, "data_operations")
        self._data_observations = self._actions(data_observations, "data_observations")
        overlap = (
            (self._control_mutations & self._data_operations)
            | (self._control_mutations & self._data_observations)
            | (self._data_operations & self._data_observations)
        )
        if overlap:
            raise PlaneIsolationError(
                f"actions must belong to exactly one class: {sorted(overlap)}"
            )

    @staticmethod
    def _actions(values: Iterable[str], field: str) -> frozenset[str]:
        try:
            result = frozenset(_text(v, field) for v in values)
        except TypeError as exc:
            raise PlaneIsolationError(f"{field} must be iterable text") from exc
        if not result:
            raise PlaneIsolationError(f"{field} must be non-empty")
        return result

    def _classify(self, action: str) -> ActionClass:
        if action in self._control_mutations:
            return ActionClass.CONTROL_MUTATION
        if action in self._data_operations:
            return ActionClass.DATA_OPERATION
        if action in self._data_observations:
            return ActionClass.DATA_OBSERVATION
        raise PlaneIsolationDenied(f"unregistered action: {action}")

    @staticmethod
    def _required_capability(action_class: ActionClass, action: str) -> str:
        if action_class is ActionClass.CONTROL_MUTATION:
            return f"control:mutate:{action}"
        if action_class is ActionClass.DATA_OPERATION:
            return f"data:execute:{action}"
        return f"control:observe:{action}"

    def authorize(
        self,
        principal: PlanePrincipal,
        request: PlaneRequest,
        *,
        now_ns: int | None = None,
        ttl_ns: int = 30 * 1_000_000_000,
    ) -> PlanePermit:
        if not isinstance(principal, PlanePrincipal):
            raise TypeError("principal must be PlanePrincipal")
        if not isinstance(request, PlaneRequest):
            raise TypeError("request must be PlaneRequest")
        now = _integer(time.time_ns() if now_ns is None else now_ns, "now_ns", minimum=1)
        ttl = _integer(ttl_ns, "ttl_ns", minimum=1)
        if ttl > _MAX_TTL_NS:
            raise PlaneIsolationDenied("permit TTL exceeds bounded maximum")
        if principal.tenant_id != request.tenant_id:
            raise PlaneIsolationDenied("cross-tenant plane request denied")
        if principal.plane is not request.source_plane:
            raise PlaneIsolationDenied("principal plane does not own request source plane")
        if principal.authority_generation != self.control_generation:
            raise PlaneIsolationDenied("principal authority generation is stale")
        if request.control_generation != self.control_generation:
            raise PlaneIsolationDenied("request control generation is stale")

        action_class = self._classify(request.action)
        mutation_allowed = action_class is not ActionClass.DATA_OBSERVATION

        if action_class is ActionClass.CONTROL_MUTATION:
            if request.source_plane is not Plane.CONTROL or request.target_plane is not Plane.CONTROL:
                raise PlaneIsolationDenied(
                    "control mutations must remain entirely in the control plane"
                )
        elif action_class is ActionClass.DATA_OPERATION:
            if request.target_plane is not Plane.DATA:
                raise PlaneIsolationDenied("data operation must target the data plane")
            if request.source_plane not in {Plane.CONTROL, Plane.DATA}:
                raise PlaneIsolationDenied("invalid data-operation source plane")
        else:
            if request.source_plane is not Plane.DATA or request.target_plane is not Plane.CONTROL:
                raise PlaneIsolationDenied(
                    "data observation must flow data plane to control plane"
                )
            mutation_allowed = False

        capability = self._required_capability(action_class, request.action)
        if capability not in principal.capabilities:
            raise PlaneIsolationDenied(f"missing exact plane capability: {capability}")

        expires = now + ttl
        payload = {
            "schema": _SCHEMA,
            "request_id": request.request_id,
            "tenant_id": request.tenant_id,
            "principal_digest": principal.digest,
            "source_plane": request.source_plane.value,
            "target_plane": request.target_plane.value,
            "action": request.action,
            "action_class": action_class.value,
            "payload_digest": request.payload_digest,
            "config_digest": request.config_digest,
            "control_generation": request.control_generation,
            "issued_at_ns": now,
            "expires_at_ns": expires,
            "mutation_allowed": mutation_allowed,
        }
        return PlanePermit(
            request_id=request.request_id,
            tenant_id=request.tenant_id,
            principal_digest=principal.digest,
            source_plane=request.source_plane,
            target_plane=request.target_plane,
            action=request.action,
            action_class=action_class,
            payload_digest=request.payload_digest,
            config_digest=request.config_digest,
            control_generation=request.control_generation,
            issued_at_ns=now,
            expires_at_ns=expires,
            mutation_allowed=mutation_allowed,
            permit_digest=_canonical_digest(payload),
        )

    def verify_permit(
        self,
        permit: PlanePermit,
        principal: PlanePrincipal,
        request: PlaneRequest,
        *,
        now_ns: int | None = None,
    ) -> PlanePermit:
        if not isinstance(permit, PlanePermit):
            raise TypeError("permit must be PlanePermit")
        now = _integer(time.time_ns() if now_ns is None else now_ns, "now_ns", minimum=1)
        if now >= permit.expires_at_ns:
            raise PlanePermitStale("plane permit is expired")
        if permit.control_generation != self.control_generation:
            raise PlanePermitStale("plane permit policy generation is stale")
        if permit.principal_digest != principal.digest:
            raise PlanePermitStale("plane permit principal binding mismatch")
        fields = (
            (permit.request_id, request.request_id, "request_id"),
            (permit.tenant_id, request.tenant_id, "tenant_id"),
            (permit.source_plane, request.source_plane, "source_plane"),
            (permit.target_plane, request.target_plane, "target_plane"),
            (permit.action, request.action, "action"),
            (permit.payload_digest, request.payload_digest, "payload_digest"),
            (permit.config_digest, request.config_digest, "config_digest"),
            (permit.control_generation, request.control_generation, "control_generation"),
        )
        for actual, expected, field in fields:
            if actual != expected:
                raise PlanePermitStale(f"plane permit {field} binding mismatch")
        expected_class = self._classify(request.action)
        if permit.action_class is not expected_class:
            raise PlanePermitStale("plane permit action class drift")
        if permit.mutation_allowed != (expected_class is not ActionClass.DATA_OBSERVATION):
            raise PlanePermitStale("plane permit mutation authority drift")
        if _canonical_digest(permit.payload()) != permit.permit_digest:
            raise PlanePermitStale("plane permit digest mismatch")
        return permit

    def advance_generation(self, expected_generation: int) -> int:
        expected = _integer(expected_generation, "expected_generation", minimum=1)
        if expected != self.control_generation:
            raise PlaneIsolationDenied("stale control-generation advance")
        if self.control_generation >= _MAX_NS:
            raise PlaneIsolationError("control generation exhausted")
        self.control_generation += 1
        return self.control_generation
