"""Deterministic bounded scenario-tree runtime for VOL-073.

This module is the higher-level planning/exploration boundary above the existing
engine-neutral environment/world-model substrate. It makes state identity,
simulation-only action authority, uncertainty propagation, branching, depth,
node count and cost budgets explicit.

The central law is intentionally strict: a simulated action or successful
scenario may inform planning, but it can never authorize a real side effect or
satisfy a real-world postcondition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import math
import re
from types import MappingProxyType
from typing import Callable, Iterable, Mapping, Sequence

from skeleton.contracts.canonical import CanonicalContractError, canonical_json_bytes

SCENARIO_SCHEMA = "skeleton.simulation.scenario-runtime.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")

_MAX_STATE_FIELDS = 512
_MAX_ACTION_PARAMETER_FIELDS = 128
_MAX_TEXT = 2048
_MAX_BUDGET = 1_000_000_000


class ScenarioRuntimeError(RuntimeError):
    """Scenario input, expansion or evidence violates the simulation contract."""


class ScenarioStopReason(str, Enum):
    TERMINAL = "terminal"
    DEPTH_LIMIT = "depth_limit"
    NO_ACTIONS = "no_actions"


@dataclass(frozen=True, slots=True)
class SimulationRule:
    """Content-bound declarative rule metadata for one simulation."""

    rule_id: str
    description: str
    parameters: Mapping[str, object]
    version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _token(self.rule_id, "rule_id"))
        object.__setattr__(
            self,
            "description",
            _token(self.description, "description", maximum=_MAX_TEXT),
        )
        object.__setattr__(
            self,
            "parameters",
            _state_payload(self.parameters, "rule parameters"),
        )
        object.__setattr__(
            self,
            "version",
            _positive_int(self.version, "rule version", maximum=1_000_000),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCENARIO_SCHEMA,
                "kind": "rule",
                "rule_id": self.rule_id,
                "description": self.description,
                "parameters": dict(self.parameters),
                "version": self.version,
            }
        )


@dataclass(frozen=True, slots=True)
class SimulationRuleSet:
    """Canonical non-empty rule set bound into every scenario tree."""

    rules: tuple[SimulationRule, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.rules, tuple) or not self.rules:
            raise ScenarioRuntimeError("rules must be a non-empty tuple")
        by_id: dict[str, SimulationRule] = {}
        for rule in self.rules:
            if not isinstance(rule, SimulationRule):
                raise ScenarioRuntimeError("rules must contain SimulationRule")
            if rule.rule_id in by_id:
                raise ScenarioRuntimeError("duplicate simulation rule_id")
            by_id[rule.rule_id] = rule
        object.__setattr__(
            self,
            "rules",
            tuple(by_id[key] for key in sorted(by_id)),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCENARIO_SCHEMA,
                "kind": "rule-set",
                "rules": [
                    {"rule_id": rule.rule_id, "digest": rule.digest}
                    for rule in self.rules
                ],
            }
        )


def _token(value: object, field: str, *, maximum: int = 128) -> str:
    if not isinstance(value, str):
        raise ScenarioRuntimeError(f"{field} must be text")
    if value != value.strip() or not value or len(value) > maximum:
        raise ScenarioRuntimeError(f"{field} must be canonical non-empty text")
    if maximum <= 128 and not _TOKEN_RE.fullmatch(value):
        raise ScenarioRuntimeError(f"{field} must be a canonical token")
    return value


def _positive_int(value: object, field: str, *, maximum: int = _MAX_BUDGET) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScenarioRuntimeError(f"{field} must be an integer")
    if not 1 <= value <= maximum:
        raise ScenarioRuntimeError(f"{field} must be within [1, {maximum}]")
    return value


def _nonnegative_int(
    value: object,
    field: str,
    *,
    maximum: int = _MAX_BUDGET,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScenarioRuntimeError(f"{field} must be an integer")
    if not 0 <= value <= maximum:
        raise ScenarioRuntimeError(f"{field} must be within [0, {maximum}]")
    return value


def _unit(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioRuntimeError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ScenarioRuntimeError(f"{field} must be finite within [0, 1]")
    return result


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioRuntimeError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ScenarioRuntimeError(f"{field} must be finite")
    return result


def _jsonable(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: _jsonable(child)
            for key, child in value.items()
        }
    if isinstance(value, tuple):
        return [_jsonable(child) for child in value]
    return value


def _freeze_json(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, child in value.items():
            canonical_key = _token(key, f"{field} key", maximum=128)
            if canonical_key in frozen:
                raise ScenarioRuntimeError(f"{field} contains duplicate key")
            frozen[canonical_key] = _freeze_json(child, field)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(child, field) for child in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ScenarioRuntimeError(f"{field} contains non-finite numeric value")
        return value
    raise ScenarioRuntimeError(
        f"{field} contains unsupported deterministic JSON value "
        f"{type(value).__name__}"
    )


def _canonical_json(value: object, field: str) -> bytes:
    try:
        return canonical_json_bytes(_jsonable(value))
    except CanonicalContractError as exc:
        raise ScenarioRuntimeError(f"{field} must be deterministic JSON") from exc


def _digest(value: object, field: str = "payload") -> str:
    return sha256(_canonical_json(value, field)).hexdigest()


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ScenarioRuntimeError(f"{field} must be lowercase sha256")
    return value


def _state_payload(
    value: Mapping[str, object],
    field: str = "state",
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ScenarioRuntimeError(f"{field} must be a mapping")
    if len(value) > _MAX_STATE_FIELDS:
        raise ScenarioRuntimeError(f"{field} exceeds {_MAX_STATE_FIELDS} fields")
    frozen = _freeze_json(value, field)
    if not isinstance(frozen, Mapping):
        raise ScenarioRuntimeError(f"{field} must freeze to a mapping")
    _canonical_json(frozen, field)
    return frozen


def _parameters(value: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ScenarioRuntimeError("action parameters must be a mapping")
    if len(value) > _MAX_ACTION_PARAMETER_FIELDS:
        raise ScenarioRuntimeError(
            f"action parameters exceed {_MAX_ACTION_PARAMETER_FIELDS} fields"
        )
    frozen = _freeze_json(value, "action parameters")
    if not isinstance(frozen, Mapping):
        raise ScenarioRuntimeError("action parameters must freeze to a mapping")
    _canonical_json(frozen, "action parameters")
    return frozen


def _conservative_union(prior: float, local: float) -> float:
    left = _unit(prior, "prior_uncertainty")
    right = _unit(local, "local_uncertainty")
    combined = 1.0 - ((1.0 - left) * (1.0 - right))
    if combined + 1e-15 < left or combined + 1e-15 < right:
        raise ScenarioRuntimeError("uncertainty propagation regressed")
    return min(1.0, max(0.0, combined))


@dataclass(frozen=True, slots=True)
class SimulationBudget:
    """Hard deterministic limits for one scenario exploration."""

    max_depth: int
    max_branches_per_node: int
    max_nodes: int
    max_cost_units: int
    max_total_actions: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_depth",
            _positive_int(self.max_depth, "max_depth", maximum=100_000),
        )
        object.__setattr__(
            self,
            "max_branches_per_node",
            _positive_int(
                self.max_branches_per_node,
                "max_branches_per_node",
                maximum=100_000,
            ),
        )
        object.__setattr__(
            self,
            "max_nodes",
            _positive_int(self.max_nodes, "max_nodes"),
        )
        object.__setattr__(
            self,
            "max_cost_units",
            _positive_int(self.max_cost_units, "max_cost_units"),
        )
        object.__setattr__(
            self,
            "max_total_actions",
            _positive_int(self.max_total_actions, "max_total_actions"),
        )
        if self.max_nodes < 1 + self.max_branches_per_node:
            # Not an error: a small node budget can intentionally constrain the
            # first frontier. The runtime simply fails closed before publication.
            pass

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCENARIO_SCHEMA,
                "kind": "budget",
                "max_depth": self.max_depth,
                "max_branches_per_node": self.max_branches_per_node,
                "max_nodes": self.max_nodes,
                "max_cost_units": self.max_cost_units,
                "max_total_actions": self.max_total_actions,
            }
        )


@dataclass(frozen=True, slots=True)
class SimulationAuthority:
    """Capability allowlist that can never represent real-effect authority."""

    authority_id: str
    simulation_id: str
    allowed_capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "authority_id",
            _token(self.authority_id, "authority_id"),
        )
        object.__setattr__(
            self,
            "simulation_id",
            _token(self.simulation_id, "simulation_id"),
        )
        if not isinstance(self.allowed_capabilities, tuple):
            raise ScenarioRuntimeError("allowed_capabilities must be a tuple")
        normalized: list[str] = []
        for raw in self.allowed_capabilities:
            capability = _token(raw, "capability")
            if capability in normalized:
                raise ScenarioRuntimeError("duplicate simulation capability")
            normalized.append(capability)
        if not normalized:
            raise ScenarioRuntimeError("simulation authority requires capabilities")
        object.__setattr__(
            self,
            "allowed_capabilities",
            tuple(sorted(normalized)),
        )

    def require(self, capability: str) -> None:
        normalized = _token(capability, "capability")
        if normalized not in self.allowed_capabilities:
            raise ScenarioRuntimeError(
                f"simulation capability {normalized!r} is not authorized"
            )

    def require_real_effect_authority(self) -> None:
        raise ScenarioRuntimeError(
            "simulation authority can never authorize a real-world side effect"
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCENARIO_SCHEMA,
                "kind": "authority",
                "authority_id": self.authority_id,
                "simulation_id": self.simulation_id,
                "allowed_capabilities": list(self.allowed_capabilities),
                "effect_scope": "simulation_only",
            }
        )


@dataclass(frozen=True, slots=True)
class SimulationAction:
    """Typed action proposal with simulation-only effect scope."""

    action_id: str
    simulation_id: str
    capability: str
    operation: str
    parameters: Mapping[str, object]
    cost_units: int = 1
    effect_scope: str = "simulation_only"

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_id", _token(self.action_id, "action_id"))
        object.__setattr__(
            self,
            "simulation_id",
            _token(self.simulation_id, "simulation_id"),
        )
        object.__setattr__(
            self,
            "capability",
            _token(self.capability, "capability"),
        )
        object.__setattr__(
            self,
            "operation",
            _token(self.operation, "operation"),
        )
        object.__setattr__(
            self,
            "parameters",
            _parameters(self.parameters),
        )
        object.__setattr__(
            self,
            "cost_units",
            _positive_int(self.cost_units, "cost_units"),
        )
        if self.effect_scope != "simulation_only":
            raise ScenarioRuntimeError(
                "simulation action effect_scope must remain simulation_only"
            )

    def authorize(self, authority: SimulationAuthority) -> None:
        if not isinstance(authority, SimulationAuthority):
            raise TypeError("authority must be SimulationAuthority")
        if authority.simulation_id != self.simulation_id:
            raise ScenarioRuntimeError("action/authority simulation identity mismatch")
        authority.require(self.capability)

    def require_real_effect_authority(self) -> None:
        raise ScenarioRuntimeError(
            "simulation action cannot be promoted into real-effect authority"
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCENARIO_SCHEMA,
                "kind": "action",
                "action_id": self.action_id,
                "simulation_id": self.simulation_id,
                "capability": self.capability,
                "operation": self.operation,
                "parameters": dict(self.parameters),
                "cost_units": self.cost_units,
                "effect_scope": self.effect_scope,
            }
        )


@dataclass(frozen=True, slots=True)
class ScenarioTransition:
    """One deterministic candidate transition returned by an expander."""

    action: SimulationAction
    next_state: Mapping[str, object]
    local_uncertainty: float
    reward: float = 0.0
    terminal: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.action, SimulationAction):
            raise TypeError("action must be SimulationAction")
        object.__setattr__(
            self,
            "next_state",
            _state_payload(self.next_state, "next_state"),
        )
        object.__setattr__(
            self,
            "local_uncertainty",
            _unit(self.local_uncertainty, "local_uncertainty"),
        )
        object.__setattr__(self, "reward", _finite(self.reward, "reward"))
        if not isinstance(self.terminal, bool):
            raise ScenarioRuntimeError("terminal must be boolean")

    @property
    def next_state_digest(self) -> str:
        return _digest(dict(self.next_state), "next_state")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCENARIO_SCHEMA,
                "kind": "transition",
                "action_digest": self.action.digest,
                "next_state_digest": self.next_state_digest,
                "local_uncertainty": self.local_uncertainty,
                "reward": self.reward,
                "terminal": self.terminal,
            }
        )


@dataclass(frozen=True, slots=True)
class ScenarioNode:
    node_id: str
    parent_id: str | None
    depth: int
    state_digest: str
    cumulative_uncertainty: float
    cumulative_cost_units: int
    action_count: int
    terminal: bool
    stop_reason: ScenarioStopReason | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _token(self.node_id, "node_id"))
        if self.parent_id is not None:
            object.__setattr__(
                self,
                "parent_id",
                _token(self.parent_id, "parent_id"),
            )
            if self.parent_id == self.node_id:
                raise ScenarioRuntimeError("node cannot parent itself")
        object.__setattr__(
            self,
            "depth",
            _nonnegative_int(self.depth, "depth", maximum=100_000),
        )
        object.__setattr__(
            self,
            "state_digest",
            _sha256(self.state_digest, "state_digest"),
        )
        object.__setattr__(
            self,
            "cumulative_uncertainty",
            _unit(self.cumulative_uncertainty, "cumulative_uncertainty"),
        )
        object.__setattr__(
            self,
            "cumulative_cost_units",
            _nonnegative_int(
                self.cumulative_cost_units,
                "cumulative_cost_units",
            ),
        )
        object.__setattr__(
            self,
            "action_count",
            _nonnegative_int(self.action_count, "action_count"),
        )
        if not isinstance(self.terminal, bool):
            raise ScenarioRuntimeError("terminal must be boolean")
        if self.stop_reason is not None and not isinstance(
            self.stop_reason,
            ScenarioStopReason,
        ):
            raise ScenarioRuntimeError("stop_reason must be ScenarioStopReason")
        if self.parent_id is None and self.depth != 0:
            raise ScenarioRuntimeError("root node depth must be zero")
        if self.parent_id is None and self.action_count != 0:
            raise ScenarioRuntimeError("root node action_count must be zero")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCENARIO_SCHEMA,
                "kind": "node",
                "node_id": self.node_id,
                "parent_id": self.parent_id,
                "depth": self.depth,
                "state_digest": self.state_digest,
                "cumulative_uncertainty": self.cumulative_uncertainty,
                "cumulative_cost_units": self.cumulative_cost_units,
                "action_count": self.action_count,
                "terminal": self.terminal,
                "stop_reason": (
                    None if self.stop_reason is None else self.stop_reason.value
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class ScenarioEdge:
    parent_id: str
    child_id: str
    action_digest: str
    transition_digest: str
    reward: float
    local_uncertainty: float
    cost_units: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parent_id",
            _token(self.parent_id, "parent_id"),
        )
        object.__setattr__(
            self,
            "child_id",
            _token(self.child_id, "child_id"),
        )
        if self.parent_id == self.child_id:
            raise ScenarioRuntimeError("scenario edge cannot self-loop")
        object.__setattr__(
            self,
            "action_digest",
            _sha256(self.action_digest, "action_digest"),
        )
        object.__setattr__(
            self,
            "transition_digest",
            _sha256(self.transition_digest, "transition_digest"),
        )
        object.__setattr__(self, "reward", _finite(self.reward, "reward"))
        object.__setattr__(
            self,
            "local_uncertainty",
            _unit(self.local_uncertainty, "local_uncertainty"),
        )
        object.__setattr__(
            self,
            "cost_units",
            _positive_int(self.cost_units, "cost_units"),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCENARIO_SCHEMA,
                "kind": "edge",
                "parent_id": self.parent_id,
                "child_id": self.child_id,
                "action_digest": self.action_digest,
                "transition_digest": self.transition_digest,
                "reward": self.reward,
                "local_uncertainty": self.local_uncertainty,
                "cost_units": self.cost_units,
            }
        )


@dataclass(frozen=True, slots=True)
class ScenarioResourceUsage:
    nodes: int
    actions: int
    cost_units: int
    max_depth_reached: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "nodes",
            _positive_int(self.nodes, "nodes"),
        )
        object.__setattr__(
            self,
            "actions",
            _nonnegative_int(self.actions, "actions"),
        )
        object.__setattr__(
            self,
            "cost_units",
            _nonnegative_int(self.cost_units, "cost_units"),
        )
        object.__setattr__(
            self,
            "max_depth_reached",
            _nonnegative_int(
                self.max_depth_reached,
                "max_depth_reached",
                maximum=100_000,
            ),
        )


@dataclass(frozen=True, slots=True)
class ScenarioTree:
    simulation_id: str
    authority_digest: str
    budget_digest: str
    rule_set_digest: str
    root_id: str
    nodes: tuple[ScenarioNode, ...]
    edges: tuple[ScenarioEdge, ...]
    usage: ScenarioResourceUsage
    evidence_class: str = "simulation"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "simulation_id",
            _token(self.simulation_id, "simulation_id"),
        )
        object.__setattr__(
            self,
            "authority_digest",
            _sha256(self.authority_digest, "authority_digest"),
        )
        object.__setattr__(
            self,
            "budget_digest",
            _sha256(self.budget_digest, "budget_digest"),
        )
        object.__setattr__(
            self,
            "rule_set_digest",
            _sha256(self.rule_set_digest, "rule_set_digest"),
        )
        object.__setattr__(self, "root_id", _token(self.root_id, "root_id"))
        if not isinstance(self.nodes, tuple) or not self.nodes:
            raise ScenarioRuntimeError("nodes must be a non-empty tuple")
        if not isinstance(self.edges, tuple):
            raise ScenarioRuntimeError("edges must be a tuple")
        if not isinstance(self.usage, ScenarioResourceUsage):
            raise TypeError("usage must be ScenarioResourceUsage")
        if self.evidence_class != "simulation":
            raise ScenarioRuntimeError(
                "scenario trees must remain simulation evidence"
            )

        by_id: dict[str, ScenarioNode] = {}
        for node in self.nodes:
            if not isinstance(node, ScenarioNode):
                raise ScenarioRuntimeError("nodes must contain ScenarioNode")
            if node.node_id in by_id:
                raise ScenarioRuntimeError("duplicate scenario node identity")
            by_id[node.node_id] = node
        root = by_id.get(self.root_id)
        if root is None or root.parent_id is not None or root.depth != 0:
            raise ScenarioRuntimeError("root_id must identify the root node")

        child_ids: set[str] = set()
        for edge in self.edges:
            if not isinstance(edge, ScenarioEdge):
                raise ScenarioRuntimeError("edges must contain ScenarioEdge")
            parent = by_id.get(edge.parent_id)
            child = by_id.get(edge.child_id)
            if parent is None or child is None:
                raise ScenarioRuntimeError("edge references unknown node")
            if child.parent_id != parent.node_id:
                raise ScenarioRuntimeError("edge disagrees with child parent_id")
            if child.depth != parent.depth + 1:
                raise ScenarioRuntimeError("child depth must equal parent depth + 1")
            if child.node_id in child_ids:
                raise ScenarioRuntimeError("child node has multiple parents")
            child_ids.add(child.node_id)

        expected_non_root = set(by_id) - {self.root_id}
        if child_ids != expected_non_root:
            raise ScenarioRuntimeError("scenario tree contains unreachable nodes")
        if self.usage.nodes != len(self.nodes):
            raise ScenarioRuntimeError("usage.nodes does not match tree")
        if self.usage.actions != len(self.edges):
            raise ScenarioRuntimeError("usage.actions does not match tree")
        if self.usage.cost_units != sum(edge.cost_units for edge in self.edges):
            raise ScenarioRuntimeError("usage.cost_units does not match tree")
        if self.usage.max_depth_reached != max(node.depth for node in self.nodes):
            raise ScenarioRuntimeError("usage.max_depth_reached does not match tree")

    @property
    def can_support_real_world_fact(self) -> bool:
        return False

    @property
    def can_satisfy_real_postcondition(self) -> bool:
        return False

    def require_real_world_postcondition_authority(self) -> None:
        raise ScenarioRuntimeError(
            "scenario simulation cannot satisfy a real-world postcondition"
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCENARIO_SCHEMA,
                "kind": "scenario-tree",
                "simulation_id": self.simulation_id,
                "authority_digest": self.authority_digest,
                "budget_digest": self.budget_digest,
                "rule_set_digest": self.rule_set_digest,
                "root_id": self.root_id,
                "nodes": [node.digest for node in self.nodes],
                "edges": [edge.digest for edge in self.edges],
                "usage": {
                    "nodes": self.usage.nodes,
                    "actions": self.usage.actions,
                    "cost_units": self.usage.cost_units,
                    "max_depth_reached": self.usage.max_depth_reached,
                },
                "evidence_class": self.evidence_class,
            }
        )


Expander = Callable[
    [Mapping[str, object], ScenarioNode],
    Sequence[ScenarioTransition],
]


class ScenarioRuntime:
    """Breadth-first deterministic scenario exploration with atomic publication."""

    def __init__(
        self,
        *,
        simulation_id: str,
        authority: SimulationAuthority,
        budget: SimulationBudget,
        rules: SimulationRuleSet,
    ) -> None:
        self.simulation_id = _token(simulation_id, "simulation_id")
        if not isinstance(authority, SimulationAuthority):
            raise TypeError("authority must be SimulationAuthority")
        if not isinstance(budget, SimulationBudget):
            raise TypeError("budget must be SimulationBudget")
        if not isinstance(rules, SimulationRuleSet):
            raise TypeError("rules must be SimulationRuleSet")
        if authority.simulation_id != self.simulation_id:
            raise ScenarioRuntimeError(
                "runtime/authority simulation identity mismatch"
            )
        self.authority = authority
        self.budget = budget
        self.rules = rules

    @staticmethod
    def _root_id(
        *,
        simulation_id: str,
        initial_state_digest: str,
        authority_digest: str,
        budget_digest: str,
        rule_set_digest: str,
    ) -> str:
        return "root-" + _digest(
            {
                "schema": SCENARIO_SCHEMA,
                "simulation_id": simulation_id,
                "initial_state_digest": initial_state_digest,
                "authority_digest": authority_digest,
                "budget_digest": budget_digest,
                "rule_set_digest": rule_set_digest,
            }
        )[:32]

    @staticmethod
    def _child_id(
        parent: ScenarioNode,
        transition: ScenarioTransition,
    ) -> str:
        return "node-" + _digest(
            {
                "schema": SCENARIO_SCHEMA,
                "parent_id": parent.node_id,
                "parent_state_digest": parent.state_digest,
                "action_digest": transition.action.digest,
                "transition_digest": transition.digest,
            }
        )[:32]

    def explore(
        self,
        initial_state: Mapping[str, object],
        expander: Expander,
        *,
        initial_uncertainty: float = 0.0,
    ) -> ScenarioTree:
        """Build a complete bounded tree or publish nothing.

        Branching/node/cost violations raise before a ScenarioTree is returned.
        The caller never receives a partially authoritative result.
        """

        if not callable(expander):
            raise TypeError("expander must be callable")
        root_state = _state_payload(initial_state, "initial_state")
        root_state_digest = _digest(root_state, "initial_state")
        root_uncertainty = _unit(
            initial_uncertainty,
            "initial_uncertainty",
        )
        root_id = self._root_id(
            simulation_id=self.simulation_id,
            initial_state_digest=root_state_digest,
            authority_digest=self.authority.digest,
            budget_digest=self.budget.digest,
            rule_set_digest=self.rules.digest,
        )
        root = ScenarioNode(
            node_id=root_id,
            parent_id=None,
            depth=0,
            state_digest=root_state_digest,
            cumulative_uncertainty=root_uncertainty,
            cumulative_cost_units=0,
            action_count=0,
            terminal=False,
            stop_reason=None,
        )

        nodes: list[ScenarioNode] = [root]
        edges: list[ScenarioEdge] = []
        states: dict[str, dict[str, object]] = {root.node_id: root_state}
        frontier: list[ScenarioNode] = [root]
        total_cost = 0
        total_actions = 0

        while frontier:
            parent = frontier.pop(0)
            parent_state = states[parent.node_id]

            if parent.terminal:
                continue
            if parent.depth >= self.budget.max_depth:
                self._replace_stop_reason(
                    nodes,
                    parent.node_id,
                    ScenarioStopReason.DEPTH_LIMIT,
                )
                continue

            raw_transitions = expander(dict(parent_state), parent)
            if isinstance(raw_transitions, (str, bytes)) or not isinstance(
                raw_transitions,
                Sequence,
            ):
                raise ScenarioRuntimeError(
                    "expander must return a finite sequence of ScenarioTransition"
                )
            transitions = tuple(raw_transitions)
            if len(transitions) > self.budget.max_branches_per_node:
                raise ScenarioRuntimeError(
                    "scenario branching exceeds max_branches_per_node"
                )
            if not transitions:
                self._replace_stop_reason(
                    nodes,
                    parent.node_id,
                    ScenarioStopReason.NO_ACTIONS,
                )
                continue

            prepared: list[tuple[str, ScenarioTransition]] = []
            action_ids: set[str] = set()
            child_ids: set[str] = set()
            for transition in transitions:
                if not isinstance(transition, ScenarioTransition):
                    raise ScenarioRuntimeError(
                        "expander sequence must contain ScenarioTransition"
                    )
                action = transition.action
                action.authorize(self.authority)
                if action.simulation_id != self.simulation_id:
                    raise ScenarioRuntimeError(
                        "transition action belongs to another simulation"
                    )
                if action.action_id in action_ids:
                    raise ScenarioRuntimeError(
                        "duplicate action_id under one scenario node"
                    )
                action_ids.add(action.action_id)
                child_id = self._child_id(parent, transition)
                if child_id in child_ids:
                    raise ScenarioRuntimeError(
                        "duplicate child identity under one scenario node"
                    )
                child_ids.add(child_id)
                prepared.append((child_id, transition))

            prepared.sort(
                key=lambda item: (
                    item[1].action.action_id,
                    item[1].action.digest,
                    item[1].next_state_digest,
                )
            )

            projected_actions = total_actions + len(prepared)
            if projected_actions > self.budget.max_total_actions:
                raise ScenarioRuntimeError(
                    "scenario action count exceeds max_total_actions"
                )
            projected_nodes = len(nodes) + len(prepared)
            if projected_nodes > self.budget.max_nodes:
                raise ScenarioRuntimeError(
                    "scenario node count exceeds max_nodes"
                )
            branch_cost = sum(
                transition.action.cost_units
                for _, transition in prepared
            )
            projected_cost = total_cost + branch_cost
            if projected_cost > self.budget.max_cost_units:
                raise ScenarioRuntimeError(
                    "scenario cost exceeds max_cost_units"
                )

            for child_id, transition in prepared:
                cumulative_uncertainty = _conservative_union(
                    parent.cumulative_uncertainty,
                    transition.local_uncertainty,
                )
                cumulative_cost = (
                    parent.cumulative_cost_units
                    + transition.action.cost_units
                )
                terminal = transition.terminal
                stop_reason = (
                    ScenarioStopReason.TERMINAL if terminal else None
                )
                child = ScenarioNode(
                    node_id=child_id,
                    parent_id=parent.node_id,
                    depth=parent.depth + 1,
                    state_digest=transition.next_state_digest,
                    cumulative_uncertainty=cumulative_uncertainty,
                    cumulative_cost_units=cumulative_cost,
                    action_count=parent.action_count + 1,
                    terminal=terminal,
                    stop_reason=stop_reason,
                )
                edge = ScenarioEdge(
                    parent_id=parent.node_id,
                    child_id=child.node_id,
                    action_digest=transition.action.digest,
                    transition_digest=transition.digest,
                    reward=transition.reward,
                    local_uncertainty=transition.local_uncertainty,
                    cost_units=transition.action.cost_units,
                )
                nodes.append(child)
                edges.append(edge)
                states[child.node_id] = dict(transition.next_state)
                if not terminal:
                    frontier.append(child)

            total_actions = projected_actions
            total_cost = projected_cost

        canonical_nodes = tuple(
            sorted(
                nodes,
                key=lambda item: (item.depth, item.node_id),
            )
        )
        canonical_edges = tuple(
            sorted(
                edges,
                key=lambda item: (
                    item.parent_id,
                    item.child_id,
                    item.action_digest,
                ),
            )
        )
        usage = ScenarioResourceUsage(
            nodes=len(canonical_nodes),
            actions=len(canonical_edges),
            cost_units=total_cost,
            max_depth_reached=max(node.depth for node in canonical_nodes),
        )
        tree = ScenarioTree(
            simulation_id=self.simulation_id,
            authority_digest=self.authority.digest,
            budget_digest=self.budget.digest,
            rule_set_digest=self.rules.digest,
            root_id=root.node_id,
            nodes=canonical_nodes,
            edges=canonical_edges,
            usage=usage,
        )
        self.verify(tree)
        return tree

    @staticmethod
    def _replace_stop_reason(
        nodes: list[ScenarioNode],
        node_id: str,
        reason: ScenarioStopReason,
    ) -> None:
        for index, node in enumerate(nodes):
            if node.node_id != node_id:
                continue
            nodes[index] = ScenarioNode(
                node_id=node.node_id,
                parent_id=node.parent_id,
                depth=node.depth,
                state_digest=node.state_digest,
                cumulative_uncertainty=node.cumulative_uncertainty,
                cumulative_cost_units=node.cumulative_cost_units,
                action_count=node.action_count,
                terminal=node.terminal,
                stop_reason=reason,
            )
            return
        raise ScenarioRuntimeError("internal node replacement failed")

    def verify(self, tree: ScenarioTree) -> None:
        """Verify a returned tree against this runtime's exact authority/budget."""

        if not isinstance(tree, ScenarioTree):
            raise TypeError("tree must be ScenarioTree")
        if tree.simulation_id != self.simulation_id:
            raise ScenarioRuntimeError("tree simulation identity mismatch")
        if tree.authority_digest != self.authority.digest:
            raise ScenarioRuntimeError("tree authority identity mismatch")
        if tree.budget_digest != self.budget.digest:
            raise ScenarioRuntimeError("tree budget identity mismatch")
        if tree.rule_set_digest != self.rules.digest:
            raise ScenarioRuntimeError("tree rule-set identity mismatch")
        if tree.usage.nodes > self.budget.max_nodes:
            raise ScenarioRuntimeError("tree exceeds max_nodes")
        if tree.usage.actions > self.budget.max_total_actions:
            raise ScenarioRuntimeError("tree exceeds max_total_actions")
        if tree.usage.cost_units > self.budget.max_cost_units:
            raise ScenarioRuntimeError("tree exceeds max_cost_units")
        if tree.usage.max_depth_reached > self.budget.max_depth:
            raise ScenarioRuntimeError("tree exceeds max_depth")

        branches: dict[str, int] = {}
        by_id = {node.node_id: node for node in tree.nodes}
        for edge in tree.edges:
            branches[edge.parent_id] = branches.get(edge.parent_id, 0) + 1
            parent = by_id[edge.parent_id]
            child = by_id[edge.child_id]
            expected_uncertainty = _conservative_union(
                parent.cumulative_uncertainty,
                edge.local_uncertainty,
            )
            if abs(child.cumulative_uncertainty - expected_uncertainty) > 1e-12:
                raise ScenarioRuntimeError(
                    "tree cumulative uncertainty does not match edge uncertainty"
                )
            if (
                child.cumulative_cost_units
                != parent.cumulative_cost_units + edge.cost_units
            ):
                raise ScenarioRuntimeError(
                    "tree cumulative cost does not match edge cost"
                )
            if child.action_count != parent.action_count + 1:
                raise ScenarioRuntimeError(
                    "tree action_count is not path-monotonic"
                )
        if branches and max(branches.values()) > self.budget.max_branches_per_node:
            raise ScenarioRuntimeError("tree exceeds max_branches_per_node")


__all__ = [
    "SCENARIO_SCHEMA",
    "ScenarioEdge",
    "ScenarioNode",
    "ScenarioResourceUsage",
    "ScenarioRuntime",
    "ScenarioRuntimeError",
    "ScenarioStopReason",
    "ScenarioTransition",
    "ScenarioTree",
    "SimulationAction",
    "SimulationAuthority",
    "SimulationBudget",
    "SimulationRule",
    "SimulationRuleSet",
]
