"""Control-plane / data-plane isolation authority for hostile gap G013.

This module provides a small fail-closed reference contract for separating
control-plane work from data-plane work inside one process. It is intentionally
backend-agnostic: a production deployment may put the same contract behind
separate services, queues, or schedulers.

The important semantics are:

* every operation is statically bound to exactly one plane;
* data-plane work can never borrow reserved control-plane capacity;
* control-plane routes may not depend on data-plane services;
* privileged control operations require an explicit capability;
* a data-plane circuit break does not disable the control plane;
* admission retries are identity-bound and cannot mutate a prior request;
* permits are authenticated and cannot be forged by callers.

This is implementation evidence for G013. It does not promote any masterplan
completion, verification, or production-authority state.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import secrets
import threading
from typing import Any, Iterable


_CONTROL = "control"
_DATA = "data"
_PLANES = frozenset({_CONTROL, _DATA})
_MAX_TEXT = 256
_MAX_CAPABILITIES = 128
_MAX_RULES = 4096
_MAX_CAPACITY = 1_000_000_000


class PlaneIsolationError(RuntimeError):
    """Base failure for the control/data isolation contract."""


class PolicyError(PlaneIsolationError):
    """The isolation policy is malformed or unsafe."""


class AdmissionRejected(PlaneIsolationError):
    """A request is not eligible for admission."""


class PlaneMismatch(AdmissionRejected):
    """The caller declared a different plane from the operation binding."""


class CapacityExhausted(AdmissionRejected):
    """The request's own plane has exhausted its independent reserve."""


class CapabilityDenied(AdmissionRejected):
    """The request lacks the exact capability required by the route."""


class DataPlaneUnavailable(AdmissionRejected):
    """The data plane is administratively isolated."""


class PermitRejected(PlaneIsolationError):
    """A permit is forged, stale, unknown, or identity-inconsistent."""


def _text(value: object, field: str, *, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PolicyError(f"{field} must be canonical non-empty text")
    if len(value) > maximum:
        raise PolicyError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PolicyError(f"{field} contains control characters")
    return value


def _positive(value: object, field: str, *, maximum: int = _MAX_CAPACITY) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
        or value > maximum
    ):
        raise PolicyError(f"{field} must be an integer in [1, {maximum}]")
    return value


def _plane(value: object, field: str = "plane") -> str:
    plane = _text(value, field, maximum=16)
    if plane not in _PLANES:
        raise PolicyError(f"{field} must be 'control' or 'data'")
    return plane


def _capability_tuple(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise PolicyError(f"{field} must be an iterable of capability strings")
    result = tuple(_text(value, field) for value in values)
    if len(result) > _MAX_CAPABILITIES:
        raise PolicyError(f"{field} exceeds capability limit")
    if len(set(result)) != len(result):
        raise PolicyError(f"{field} contains duplicate capabilities")
    return tuple(sorted(result))


@dataclass(frozen=True, slots=True)
class DependencyBinding:
    """A statically declared service dependency and the plane it belongs to."""

    service: str
    plane: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "service", _text(self.service, "dependency.service"))
        object.__setattr__(self, "plane", _plane(self.plane, "dependency.plane"))


@dataclass(frozen=True, slots=True)
class EndpointRule:
    """Immutable binding from an operation to its required execution plane."""

    operation: str
    plane: str
    required_capability: str
    dependencies: tuple[DependencyBinding, ...] = ()

    def __post_init__(self) -> None:
        operation = _text(self.operation, "operation")
        plane = _plane(self.plane)
        capability = _text(self.required_capability, "required_capability")
        deps = tuple(self.dependencies)
        if len(deps) > 128:
            raise PolicyError("endpoint dependency list exceeds limit")
        names = [dep.service for dep in deps]
        if len(set(names)) != len(names):
            raise PolicyError("endpoint contains duplicate dependency services")
        if plane == _CONTROL:
            unsafe = [dep.service for dep in deps if dep.plane == _DATA]
            if unsafe:
                raise PolicyError(
                    "control-plane endpoint depends on data-plane service: "
                    + ", ".join(sorted(unsafe))
                )
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "plane", plane)
        object.__setattr__(self, "required_capability", capability)
        object.__setattr__(self, "dependencies", tuple(sorted(
            deps, key=lambda dep: (dep.service, dep.plane)
        )))


@dataclass(frozen=True, slots=True)
class IsolationPolicy:
    """Immutable policy snapshot with physically separate plane reserves."""

    version: int
    control_concurrency: int
    data_concurrency: int
    control_cost_capacity: int
    data_cost_capacity: int
    max_request_cost: int
    rules: tuple[EndpointRule, ...]
    admin_capability: str = "control:isolation_admin"

    def __post_init__(self) -> None:
        version = _positive(self.version, "version")
        control_concurrency = _positive(
            self.control_concurrency, "control_concurrency"
        )
        data_concurrency = _positive(self.data_concurrency, "data_concurrency")
        control_cost = _positive(
            self.control_cost_capacity, "control_cost_capacity"
        )
        data_cost = _positive(self.data_cost_capacity, "data_cost_capacity")
        max_request = _positive(self.max_request_cost, "max_request_cost")
        rules = tuple(self.rules)
        if not rules or len(rules) > _MAX_RULES:
            raise PolicyError("rules must contain between 1 and 4096 entries")
        operations = [rule.operation for rule in rules]
        if len(set(operations)) != len(operations):
            raise PolicyError("policy contains duplicate operation bindings")
        if max_request > max(control_cost, data_cost):
            raise PolicyError("max_request_cost exceeds every plane cost reserve")
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "control_concurrency", control_concurrency)
        object.__setattr__(self, "data_concurrency", data_concurrency)
        object.__setattr__(self, "control_cost_capacity", control_cost)
        object.__setattr__(self, "data_cost_capacity", data_cost)
        object.__setattr__(self, "max_request_cost", max_request)
        object.__setattr__(self, "admin_capability", _text(
            self.admin_capability, "admin_capability"
        ))
        object.__setattr__(self, "rules", tuple(sorted(
            rules, key=lambda rule: rule.operation
        )))

    @property
    def digest(self) -> str:
        payload = {
            "version": self.version,
            "control_concurrency": self.control_concurrency,
            "data_concurrency": self.data_concurrency,
            "control_cost_capacity": self.control_cost_capacity,
            "data_cost_capacity": self.data_cost_capacity,
            "max_request_cost": self.max_request_cost,
            "admin_capability": self.admin_capability,
            "rules": [
                {
                    "operation": rule.operation,
                    "plane": rule.plane,
                    "required_capability": rule.required_capability,
                    "dependencies": [
                        {"service": dep.service, "plane": dep.plane}
                        for dep in rule.dependencies
                    ],
                }
                for rule in self.rules
            ],
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class AdmissionRequest:
    request_id: str
    tenant_id: str
    principal_id: str
    operation: str
    declared_plane: str
    cost_units: int
    capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))
        object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self, "principal_id", _text(self.principal_id, "principal_id")
        )
        object.__setattr__(self, "operation", _text(self.operation, "operation"))
        object.__setattr__(self, "declared_plane", _plane(self.declared_plane))
        object.__setattr__(self, "cost_units", _positive(
            self.cost_units, "cost_units"
        ))
        object.__setattr__(self, "capabilities", _capability_tuple(
            self.capabilities, "capabilities"
        ))

    @property
    def identity_digest(self) -> str:
        payload = {
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "principal_id": self.principal_id,
            "operation": self.operation,
            "declared_plane": self.declared_plane,
            "cost_units": self.cost_units,
            "capabilities": list(self.capabilities),
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class AdmissionPermit:
    permit_id: str
    request_id: str
    tenant_id: str
    principal_id: str
    operation: str
    plane: str
    cost_units: int
    policy_version: int
    policy_digest: str
    sequence: int
    request_digest: str
    signature: str

    def public_dict(self) -> dict[str, Any]:
        return {
            "permit_id": self.permit_id,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "principal_id": self.principal_id,
            "operation": self.operation,
            "plane": self.plane,
            "cost_units": self.cost_units,
            "policy_version": self.policy_version,
            "policy_digest": self.policy_digest,
            "sequence": self.sequence,
            "request_digest": self.request_digest,
        }


class ControlDataPlaneIsolator:
    """Fail-closed admission authority with non-borrowable plane reserves."""

    def __init__(
        self,
        policy: IsolationPolicy,
        *,
        signing_key: bytes | None = None,
    ) -> None:
        if not isinstance(policy, IsolationPolicy):
            raise PolicyError("policy must be an IsolationPolicy")
        key = secrets.token_bytes(32) if signing_key is None else signing_key
        if not isinstance(key, bytes) or len(key) < 32:
            raise PolicyError("signing_key must contain at least 32 bytes")
        self._policy = policy
        self._key = bytes(key)
        self._rules = {rule.operation: rule for rule in policy.rules}
        self._lock = threading.RLock()
        self._active: dict[str, AdmissionPermit] = {}
        self._request_index: dict[tuple[str, str], str] = {}
        self._active_count = {_CONTROL: 0, _DATA: 0}
        self._active_cost = {_CONTROL: 0, _DATA: 0}
        self._sequence = 0
        self._data_plane_open = True

    @property
    def policy(self) -> IsolationPolicy:
        return self._policy

    def admit(self, request: AdmissionRequest) -> AdmissionPermit:
        if not isinstance(request, AdmissionRequest):
            raise AdmissionRejected("request must be an AdmissionRequest")
        rule = self._rules.get(request.operation)
        if rule is None:
            raise AdmissionRejected("operation is not bound by isolation policy")
        if request.declared_plane != rule.plane:
            raise PlaneMismatch(
                f"operation {request.operation!r} is bound to {rule.plane} plane"
            )
        if rule.required_capability not in request.capabilities:
            raise CapabilityDenied(
                f"operation requires capability {rule.required_capability!r}"
            )
        if request.cost_units > self._policy.max_request_cost:
            raise AdmissionRejected("request cost exceeds max_request_cost")

        with self._lock:
            key = (request.tenant_id, request.request_id)
            prior_id = self._request_index.get(key)
            if prior_id is not None:
                prior = self._active.get(prior_id)
                if prior is None:
                    raise PermitRejected("request index references missing permit")
                if prior.request_digest != request.identity_digest:
                    raise AdmissionRejected(
                        "request replay changed identity or authority"
                    )
                return prior

            if rule.plane == _DATA and not self._data_plane_open:
                raise DataPlaneUnavailable("data plane is isolated")

            max_count, max_cost = self._capacity_for(rule.plane)
            if self._active_count[rule.plane] >= max_count:
                raise CapacityExhausted(
                    f"{rule.plane} plane concurrency reserve exhausted"
                )
            projected_cost = self._active_cost[rule.plane] + request.cost_units
            if projected_cost > max_cost:
                raise CapacityExhausted(
                    f"{rule.plane} plane cost reserve exhausted"
                )

            self._sequence += 1
            permit = self._make_permit(request, rule, self._sequence)
            self._active[permit.permit_id] = permit
            self._request_index[key] = permit.permit_id
            self._active_count[rule.plane] += 1
            self._active_cost[rule.plane] = projected_cost
            self._assert_state()
            return permit

    def authorize(self, permit: AdmissionPermit) -> AdmissionPermit:
        """Revalidate a permit immediately before crossing an execution boundary."""
        self._validate_permit_shape(permit)
        with self._lock:
            active = self._active.get(permit.permit_id)
            if active is None or active != permit:
                raise PermitRejected("permit is not active")
            if permit.plane == _DATA and not self._data_plane_open:
                raise DataPlaneUnavailable(
                    "data-plane permit is fenced by isolation state"
                )
            return active

    def complete(self, permit: AdmissionPermit) -> None:
        self._validate_permit_shape(permit)
        with self._lock:
            active = self._active.get(permit.permit_id)
            if active is None:
                raise PermitRejected("permit is not active")
            if active != permit:
                raise PermitRejected("permit fields do not match active authority")
            self._active.pop(permit.permit_id)
            self._request_index.pop((permit.tenant_id, permit.request_id), None)
            self._active_count[permit.plane] -= 1
            self._active_cost[permit.plane] -= permit.cost_units
            self._assert_state()

    def set_data_plane_open(
        self,
        is_open: bool,
        *,
        capabilities: Iterable[str],
    ) -> None:
        if not isinstance(is_open, bool):
            raise PolicyError("is_open must be boolean")
        normalized = _capability_tuple(capabilities, "capabilities")
        if self._policy.admin_capability not in normalized:
            raise CapabilityDenied(
                f"data-plane isolation requires capability "
                f"{self._policy.admin_capability!r}"
            )
        with self._lock:
            self._data_plane_open = is_open

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "kind": "control_data_plane_isolation",
                "gap": "G013",
                "policy_version": self._policy.version,
                "policy_digest": self._policy.digest,
                "data_plane_open": self._data_plane_open,
                "active": dict(self._active_count),
                "active_cost": dict(self._active_cost),
                "sequence": self._sequence,
                "completion_checkbox": False,
                "implementation_signature": False,
                "verification_signature": False,
            }

    def _capacity_for(self, plane: str) -> tuple[int, int]:
        if plane == _CONTROL:
            return (
                self._policy.control_concurrency,
                self._policy.control_cost_capacity,
            )
        return (
            self._policy.data_concurrency,
            self._policy.data_cost_capacity,
        )

    def _make_permit(
        self,
        request: AdmissionRequest,
        rule: EndpointRule,
        sequence: int,
    ) -> AdmissionPermit:
        request_digest = request.identity_digest
        base = {
            "request_id": request.request_id,
            "tenant_id": request.tenant_id,
            "principal_id": request.principal_id,
            "operation": request.operation,
            "plane": rule.plane,
            "cost_units": request.cost_units,
            "policy_version": self._policy.version,
            "policy_digest": self._policy.digest,
            "sequence": sequence,
            "request_digest": request_digest,
        }
        material = json.dumps(
            base, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        permit_hash = hashlib.sha256(material).hexdigest()[:24]
        permit_id = f"{rule.plane}:{sequence}:{permit_hash}"
        signature = hmac.new(
            self._key,
            permit_id.encode("utf-8") + b"\0" + material,
            hashlib.sha256,
        ).hexdigest()
        return AdmissionPermit(
            permit_id=permit_id,
            signature=signature,
            **base,
        )

    def _validate_permit_shape(self, permit: AdmissionPermit) -> None:
        if not isinstance(permit, AdmissionPermit):
            raise PermitRejected("permit must be an AdmissionPermit")
        try:
            plane = _plane(permit.plane)
            _text(permit.permit_id, "permit_id", maximum=512)
            _text(permit.request_id, "request_id")
            _text(permit.tenant_id, "tenant_id")
            _text(permit.principal_id, "principal_id")
            _text(permit.operation, "operation")
            _positive(permit.cost_units, "cost_units")
            _positive(permit.policy_version, "policy_version")
            _positive(permit.sequence, "sequence")
            if len(permit.policy_digest) != 64 or len(permit.request_digest) != 64:
                raise PolicyError("permit digest length is invalid")
            int(permit.policy_digest, 16)
            int(permit.request_digest, 16)
            if len(permit.signature) != 64:
                raise PolicyError("permit signature length is invalid")
            int(permit.signature, 16)
        except (PolicyError, ValueError) as exc:
            raise PermitRejected("permit encoding is invalid") from exc
        if plane != permit.plane:
            raise PermitRejected("permit plane is not canonical")
        if permit.policy_version != self._policy.version:
            raise PermitRejected("permit policy version is stale")
        if permit.policy_digest != self._policy.digest:
            raise PermitRejected("permit policy digest is stale")

        base = permit.public_dict()
        material = json.dumps(
            {
                key: value
                for key, value in base.items()
                if key != "permit_id"
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        expected = hmac.new(
            self._key,
            permit.permit_id.encode("utf-8") + b"\0" + material,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, permit.signature):
            raise PermitRejected("permit authentication failed")

    def _assert_state(self) -> None:
        counts = {_CONTROL: 0, _DATA: 0}
        costs = {_CONTROL: 0, _DATA: 0}
        for permit in self._active.values():
            counts[permit.plane] += 1
            costs[permit.plane] += permit.cost_units
        if counts != self._active_count or costs != self._active_cost:
            raise PermitRejected("internal isolation accounting diverged")
        for key, permit_id in self._request_index.items():
            permit = self._active.get(permit_id)
            if permit is None:
                raise PermitRejected("request index references missing permit")
            if key != (permit.tenant_id, permit.request_id):
                raise PermitRejected("request index identity diverged")
        for plane in _PLANES:
            max_count, max_cost = self._capacity_for(plane)
            if counts[plane] > max_count or costs[plane] > max_cost:
                raise PermitRejected("plane reserve exceeded")
