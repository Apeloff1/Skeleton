"""Resource and authority guard for VOL-073 simulation intelligence.

This module is deliberately independent from engine/runtime packages. It
authorizes only bounded simulation work and emits a deterministic permit. It
never converts simulation actions, states, or evidence into real-world side
effect authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
from typing import Iterable, Mapping, Protocol, runtime_checkable

SIMULATION_AUTHORITY_SCHEMA = "skeleton.simulation.authority.v1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_WIRE_BYTES = 4_194_304
_MAX_CAPABILITIES = 128


class SimulationAuthorityError(RuntimeError):
    """A rollout attempted to exceed resource or authority boundaries."""


def _identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise SimulationAuthorityError(
            f"{field_name} must be a canonical identifier"
        )
    return value


def _digest(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise SimulationAuthorityError(
            f"{field_name} must be lowercase canonical sha256"
        )
    return value


def _positive_int(value: object, field_name: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SimulationAuthorityError(f"{field_name} must be an integer")
    if not 1 <= value <= maximum:
        raise SimulationAuthorityError(
            f"{field_name} must be between 1 and {maximum}"
        )
    return value


def _nonnegative_int(value: object, field_name: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SimulationAuthorityError(f"{field_name} must be an integer")
    if not 0 <= value <= maximum:
        raise SimulationAuthorityError(
            f"{field_name} must be between 0 and {maximum}"
        )
    return value


def _unit(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SimulationAuthorityError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise SimulationAuthorityError(
            f"{field_name} must be finite and within [0, 1]"
        )
    return result


def _canonical_bytes(value: object, field_name: str) -> bytes:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SimulationAuthorityError(
            f"{field_name} must be deterministic JSON"
        ) from exc
    if len(payload) > _MAX_WIRE_BYTES:
        raise SimulationAuthorityError(f"{field_name} exceeds hard wire limit")
    return payload


def _payload_digest(value: object, field_name: str) -> str:
    return sha256(_canonical_bytes(value, field_name)).hexdigest()


def _canonical_capabilities(values: Iterable[str]) -> tuple[str, ...]:
    items = tuple(values)
    if len(items) > _MAX_CAPABILITIES:
        raise SimulationAuthorityError("capability set exceeds cardinality limit")
    normalized = tuple(sorted(_identifier(item, "capability") for item in items))
    if len(normalized) != len(set(normalized)):
        raise SimulationAuthorityError("capability set contains duplicates")
    return normalized


@runtime_checkable
class SimulationStateLike(Protocol):
    world_id: str
    tick: int
    uncertainty: float
    evidence_class: str

    @property
    def digest(self) -> str:
        ...

    def to_wire(self) -> Mapping[str, object]:
        ...


@runtime_checkable
class SimulationActionLike(Protocol):
    action_id: str
    authority_scope: str
    requested_capabilities: tuple[str, ...]

    @property
    def digest(self) -> str:
        ...

    def to_wire(self) -> Mapping[str, object]:
        ...


@dataclass(frozen=True, slots=True)
class SimulationResourceBudget:
    """Hard upper bounds for one authorized simulation rollout."""

    max_depth: int
    max_branching_factor: int
    max_total_nodes: int
    max_state_bytes: int
    max_action_bytes: int
    max_compute_units: int
    max_uncertainty: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "max_depth", _positive_int(self.max_depth, "max_depth", maximum=100_000)
        )
        object.__setattr__(
            self,
            "max_branching_factor",
            _positive_int(
                self.max_branching_factor,
                "max_branching_factor",
                maximum=10_000,
            ),
        )
        object.__setattr__(
            self,
            "max_total_nodes",
            _positive_int(
                self.max_total_nodes,
                "max_total_nodes",
                maximum=100_000_000,
            ),
        )
        object.__setattr__(
            self,
            "max_state_bytes",
            _positive_int(
                self.max_state_bytes,
                "max_state_bytes",
                maximum=_MAX_WIRE_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "max_action_bytes",
            _positive_int(
                self.max_action_bytes,
                "max_action_bytes",
                maximum=_MAX_WIRE_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "max_compute_units",
            _positive_int(
                self.max_compute_units,
                "max_compute_units",
                maximum=1_000_000_000,
            ),
        )
        object.__setattr__(
            self,
            "max_uncertainty",
            _unit(self.max_uncertainty, "max_uncertainty"),
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "max_depth": self.max_depth,
            "max_branching_factor": self.max_branching_factor,
            "max_total_nodes": self.max_total_nodes,
            "max_state_bytes": self.max_state_bytes,
            "max_action_bytes": self.max_action_bytes,
            "max_compute_units": self.max_compute_units,
            "max_uncertainty": self.max_uncertainty,
        }

    @property
    def digest(self) -> str:
        return _payload_digest(
            {
                "schema": SIMULATION_AUTHORITY_SCHEMA,
                "kind": "resource-budget",
                **self.to_wire(),
            },
            "simulation resource budget",
        )


@dataclass(frozen=True, slots=True)
class RolloutRequest:
    """Declared work shape to authorize before a rollout starts."""

    request_id: str
    depth: int
    branching_factor: int
    planned_nodes: int
    compute_units: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", _identifier(self.request_id, "request_id")
        )
        object.__setattr__(
            self, "depth", _positive_int(self.depth, "depth", maximum=100_000)
        )
        object.__setattr__(
            self,
            "branching_factor",
            _positive_int(
                self.branching_factor,
                "branching_factor",
                maximum=10_000,
            ),
        )
        object.__setattr__(
            self,
            "planned_nodes",
            _positive_int(
                self.planned_nodes,
                "planned_nodes",
                maximum=100_000_000,
            ),
        )
        object.__setattr__(
            self,
            "compute_units",
            _positive_int(
                self.compute_units,
                "compute_units",
                maximum=1_000_000_000,
            ),
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "depth": self.depth,
            "branching_factor": self.branching_factor,
            "planned_nodes": self.planned_nodes,
            "compute_units": self.compute_units,
        }

    @property
    def digest(self) -> str:
        return _payload_digest(
            {
                "schema": SIMULATION_AUTHORITY_SCHEMA,
                "kind": "rollout-request",
                **self.to_wire(),
            },
            "rollout request",
        )


@dataclass(frozen=True, slots=True)
class SimulationPermit:
    """Deterministic proof that one rollout request passed the guard."""

    permit_id: str
    request_digest: str
    state_digest: str
    action_digest: str
    budget_digest: str
    state_bytes: int
    action_bytes: int
    allowed_capabilities: tuple[str, ...]
    authority_scope: str
    receipt_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "permit_id", _identifier(self.permit_id, "permit_id"))
        for field_name in (
            "request_digest",
            "state_digest",
            "action_digest",
            "budget_digest",
            "receipt_digest",
        ):
            object.__setattr__(
                self, field_name, _digest(getattr(self, field_name), field_name)
            )
        object.__setattr__(
            self,
            "state_bytes",
            _nonnegative_int(
                self.state_bytes,
                "state_bytes",
                maximum=_MAX_WIRE_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "action_bytes",
            _nonnegative_int(
                self.action_bytes,
                "action_bytes",
                maximum=_MAX_WIRE_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "allowed_capabilities",
            _canonical_capabilities(self.allowed_capabilities),
        )
        if self.authority_scope != "simulation":
            raise SimulationAuthorityError(
                "simulation permit cannot carry real authority scope"
            )

    @property
    def can_execute_real_side_effect(self) -> bool:
        return False

    def require_real_execution_authority(self) -> None:
        raise SimulationAuthorityError(
            "simulation permit cannot authorize real-world side effects"
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "permit_id": self.permit_id,
            "request_digest": self.request_digest,
            "state_digest": self.state_digest,
            "action_digest": self.action_digest,
            "budget_digest": self.budget_digest,
            "state_bytes": self.state_bytes,
            "action_bytes": self.action_bytes,
            "allowed_capabilities": list(self.allowed_capabilities),
            "authority_scope": self.authority_scope,
            "receipt_digest": self.receipt_digest,
        }


class SimulationAuthorityGuard:
    """Authorize bounded simulation work without granting real authority."""

    def __init__(
        self,
        *,
        guard_id: str,
        budget: SimulationResourceBudget,
        allowed_capabilities: Iterable[str],
    ) -> None:
        self.guard_id = _identifier(guard_id, "guard_id")
        if not isinstance(budget, SimulationResourceBudget):
            raise TypeError("budget must be SimulationResourceBudget")
        self.budget = budget
        self.allowed_capabilities = _canonical_capabilities(allowed_capabilities)

    @property
    def policy_digest(self) -> str:
        return _payload_digest(
            {
                "schema": SIMULATION_AUTHORITY_SCHEMA,
                "kind": "authority-policy",
                "guard_id": self.guard_id,
                "budget_digest": self.budget.digest,
                "allowed_capabilities": list(self.allowed_capabilities),
                "authority_scope": "simulation",
            },
            "simulation authority policy",
        )

    def authorize(
        self,
        *,
        state: SimulationStateLike,
        action: SimulationActionLike,
        request: RolloutRequest,
    ) -> SimulationPermit:
        self._validate_state(state)
        self._validate_action(action)
        if not isinstance(request, RolloutRequest):
            raise TypeError("request must be RolloutRequest")

        if request.depth > self.budget.max_depth:
            raise SimulationAuthorityError("rollout depth exceeds budget")
        if request.branching_factor > self.budget.max_branching_factor:
            raise SimulationAuthorityError("rollout branching factor exceeds budget")
        if request.planned_nodes > self.budget.max_total_nodes:
            raise SimulationAuthorityError("rollout node count exceeds budget")
        if request.compute_units > self.budget.max_compute_units:
            raise SimulationAuthorityError("rollout compute units exceed budget")
        if float(state.uncertainty) > self.budget.max_uncertainty:
            raise SimulationAuthorityError("state uncertainty exceeds rollout budget")

        state_bytes = len(_canonical_bytes(dict(state.to_wire()), "world state"))
        action_bytes = len(_canonical_bytes(dict(action.to_wire()), "simulation action"))
        if state_bytes > self.budget.max_state_bytes:
            raise SimulationAuthorityError("world state exceeds byte budget")
        if action_bytes > self.budget.max_action_bytes:
            raise SimulationAuthorityError("simulation action exceeds byte budget")

        requested = _canonical_capabilities(action.requested_capabilities)
        denied = sorted(set(requested) - set(self.allowed_capabilities))
        if denied:
            raise SimulationAuthorityError(
                f"simulation action requests undeclared capability: {denied[0]}"
            )

        state_digest = _digest(state.digest, "state digest")
        action_digest = _digest(action.digest, "action digest")
        payload = {
            "schema": SIMULATION_AUTHORITY_SCHEMA,
            "kind": "simulation-permit",
            "guard_id": self.guard_id,
            "policy_digest": self.policy_digest,
            "request_digest": request.digest,
            "state_digest": state_digest,
            "action_digest": action_digest,
            "budget_digest": self.budget.digest,
            "state_bytes": state_bytes,
            "action_bytes": action_bytes,
            "allowed_capabilities": list(requested),
            "authority_scope": "simulation",
        }
        receipt = _payload_digest(payload, "simulation permit")
        return SimulationPermit(
            permit_id=f"{self.guard_id}:{request.request_id}",
            request_digest=request.digest,
            state_digest=state_digest,
            action_digest=action_digest,
            budget_digest=self.budget.digest,
            state_bytes=state_bytes,
            action_bytes=action_bytes,
            allowed_capabilities=requested,
            authority_scope="simulation",
            receipt_digest=receipt,
        )

    def verify(
        self,
        permit: SimulationPermit,
        *,
        state: SimulationStateLike,
        action: SimulationActionLike,
        request: RolloutRequest,
    ) -> None:
        if not isinstance(permit, SimulationPermit):
            raise TypeError("permit must be SimulationPermit")
        expected = self.authorize(state=state, action=action, request=request)
        if permit != expected:
            raise SimulationAuthorityError(
                "simulation permit does not match active state/action/request policy"
            )

    @staticmethod
    def _validate_state(state: SimulationStateLike) -> None:
        if not isinstance(state, SimulationStateLike):
            raise SimulationAuthorityError(
                "state does not satisfy simulation-state structural contract"
            )
        _identifier(state.world_id, "world_id")
        if (
            isinstance(state.tick, bool)
            or not isinstance(state.tick, int)
            or state.tick < 0
        ):
            raise SimulationAuthorityError("state tick must be non-negative")
        _unit(state.uncertainty, "state uncertainty")
        if state.evidence_class != "simulation_state":
            raise SimulationAuthorityError(
                "state attempted to escape simulation evidence class"
            )
        _digest(state.digest, "state digest")

    def _validate_action(self, action: SimulationActionLike) -> None:
        if not isinstance(action, SimulationActionLike):
            raise SimulationAuthorityError(
                "action does not satisfy simulation-action structural contract"
            )
        _identifier(action.action_id, "action_id")
        if action.authority_scope != "simulation":
            raise SimulationAuthorityError(
                "action attempted to request non-simulation authority"
            )
        _digest(action.digest, "action digest")


__all__ = [
    "SIMULATION_AUTHORITY_SCHEMA",
    "RolloutRequest",
    "SimulationActionLike",
    "SimulationAuthorityError",
    "SimulationAuthorityGuard",
    "SimulationPermit",
    "SimulationResourceBudget",
    "SimulationStateLike",
]
