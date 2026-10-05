"""Canonical simulation-state contract for VOL-073.

The contract is intentionally engine-neutral. State, rules, uncertainty, and
lineage are explicit and content-addressed. Simulation state can be used for
planning and comparison, but never as authority for real-world facts or
postconditions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
import re
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

WORLD_STATE_SCHEMA = "skeleton.simulation.world_state.v1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_STATE_FIELDS = 512
_MAX_RULES = 256
_MAX_CANONICAL_BYTES = 1_048_576
_MAX_LINEAGE = 128


class WorldStateError(ValueError):
    """Simulation world-state material violates the canonical contract."""


def _identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise WorldStateError(f"{field_name} must be a canonical identifier")
    return value


def _digest(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise WorldStateError(f"{field_name} must be lowercase canonical sha256")
    return value


def _unit(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorldStateError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise WorldStateError(f"{field_name} must be finite and within [0, 1]")
    return result


def _canonical_json(value: object, field_name: str) -> bytes:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise WorldStateError(f"{field_name} must be deterministic JSON") from exc
    if len(raw) > _MAX_CANONICAL_BYTES:
        raise WorldStateError(f"{field_name} exceeds canonical byte budget")
    return raw


def _content_digest(value: object, field_name: str) -> str:
    return sha256(_canonical_json(value, field_name)).hexdigest()


def _freeze(value: object, field_name: str) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise WorldStateError(f"{field_name} contains non-finite float")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise WorldStateError(f"{field_name} mapping keys must be non-empty strings")
            if key in normalized:
                raise WorldStateError(f"{field_name} contains duplicate mapping key")
            normalized[key] = _freeze(item, field_name)
        return MappingProxyType(dict(sorted(normalized.items())))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze(item, field_name) for item in value)
    raise WorldStateError(f"{field_name} contains unsupported value type")


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _canonical_mapping(
    value: Mapping[str, object],
    field_name: str,
    *,
    max_fields: int,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise WorldStateError(f"{field_name} must be a mapping")
    if len(value) > max_fields:
        raise WorldStateError(f"{field_name} exceeds field limit")
    frozen = _freeze(value, field_name)
    if not isinstance(frozen, Mapping):
        raise AssertionError("mapping freeze contract violated")
    _canonical_json(_thaw(frozen), field_name)
    return frozen


@dataclass(frozen=True, slots=True)
class WorldRule:
    """One deterministic rule declared by the simulated world."""

    rule_id: str
    statement: str
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _identifier(self.rule_id, "rule_id"))
        if not isinstance(self.statement, str):
            raise WorldStateError("statement must be a string")
        statement = self.statement.strip()
        if not statement or statement != self.statement or len(statement) > 4096:
            raise WorldStateError("statement must be canonical bounded text")
        object.__setattr__(
            self,
            "parameters",
            _canonical_mapping(self.parameters, "rule parameters", max_fields=128),
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "statement": self.statement,
            "parameters": _thaw(self.parameters),
        }

    @property
    def digest(self) -> str:
        return _content_digest(
            {
                "schema": WORLD_STATE_SCHEMA,
                "kind": "world-rule",
                **self.to_wire(),
            },
            "world rule",
        )


@dataclass(frozen=True, slots=True)
class WorldRules:
    """Canonical rule set bound into each world-state digest."""

    rules_id: str
    rules: tuple[WorldRule, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rules_id", _identifier(self.rules_id, "rules_id"))
        if not isinstance(self.rules, tuple):
            raise WorldStateError("rules must be a tuple")
        if len(self.rules) > _MAX_RULES:
            raise WorldStateError("rule set exceeds cardinality limit")
        by_id: dict[str, WorldRule] = {}
        for rule in self.rules:
            if not isinstance(rule, WorldRule):
                raise WorldStateError("rules must contain WorldRule")
            if rule.rule_id in by_id:
                raise WorldStateError("duplicate rule_id")
            by_id[rule.rule_id] = rule
        object.__setattr__(self, "rules", tuple(by_id[key] for key in sorted(by_id)))

    def to_wire(self) -> dict[str, object]:
        return {
            "rules_id": self.rules_id,
            "rules": [rule.to_wire() for rule in self.rules],
        }

    @property
    def digest(self) -> str:
        return _content_digest(
            {
                "schema": WORLD_STATE_SCHEMA,
                "kind": "world-rules",
                **self.to_wire(),
            },
            "world rules",
        )


@dataclass(frozen=True, slots=True)
class WorldState:
    """Immutable, content-addressed state of one simulated world tick."""

    world_id: str
    tick: int
    rules_digest: str
    values: Mapping[str, object]
    uncertainty: float
    parent_state_digest: str | None = None
    evidence_class: str = "simulation_state"

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_id", _identifier(self.world_id, "world_id"))
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise WorldStateError("tick must be a non-negative integer")
        object.__setattr__(
            self, "rules_digest", _digest(self.rules_digest, "rules_digest")
        )
        object.__setattr__(
            self,
            "values",
            _canonical_mapping(
                self.values,
                "world-state values",
                max_fields=_MAX_STATE_FIELDS,
            ),
        )
        object.__setattr__(
            self, "uncertainty", _unit(self.uncertainty, "uncertainty")
        )
        if self.parent_state_digest is not None:
            object.__setattr__(
                self,
                "parent_state_digest",
                _digest(self.parent_state_digest, "parent_state_digest"),
            )
        if self.evidence_class != "simulation_state":
            raise WorldStateError("world state must remain simulation_state evidence")

    def to_wire(self) -> dict[str, object]:
        return {
            "schema": WORLD_STATE_SCHEMA,
            "world_id": self.world_id,
            "tick": self.tick,
            "rules_digest": self.rules_digest,
            "values": _thaw(self.values),
            "uncertainty": self.uncertainty,
            "parent_state_digest": self.parent_state_digest,
            "evidence_class": self.evidence_class,
        }

    @property
    def digest(self) -> str:
        return _content_digest(self.to_wire(), "world state")

    @property
    def can_support_real_world_fact(self) -> bool:
        return False

    @property
    def can_satisfy_real_postcondition(self) -> bool:
        return False

    def require_real_world_authority(self) -> None:
        raise WorldStateError(
            "simulation world state cannot authorize a real-world fact or postcondition"
        )

    def evolve(
        self,
        *,
        values: Mapping[str, object],
        uncertainty: float,
        rules: WorldRules | None = None,
    ) -> "WorldState":
        rules_digest = self.rules_digest if rules is None else rules.digest
        return WorldState(
            world_id=self.world_id,
            tick=self.tick + 1,
            rules_digest=rules_digest,
            values=values,
            uncertainty=uncertainty,
            parent_state_digest=self.digest,
        )


@dataclass(frozen=True, slots=True)
class SimulationAction:
    """Typed action that is valid only inside a simulation authority boundary."""

    action_id: str
    actor_id: str
    intent: str
    parameters: Mapping[str, object]
    requested_capabilities: tuple[str, ...] = ()
    authority_scope: str = "simulation"

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_id", _identifier(self.action_id, "action_id"))
        object.__setattr__(self, "actor_id", _identifier(self.actor_id, "actor_id"))
        if not isinstance(self.intent, str):
            raise WorldStateError("intent must be a string")
        intent = self.intent.strip()
        if not intent or intent != self.intent or len(intent) > 2048:
            raise WorldStateError("intent must be canonical bounded text")
        object.__setattr__(
            self,
            "parameters",
            _canonical_mapping(
                self.parameters,
                "action parameters",
                max_fields=128,
            ),
        )
        if not isinstance(self.requested_capabilities, tuple):
            raise WorldStateError("requested_capabilities must be a tuple")
        if len(self.requested_capabilities) > 64:
            raise WorldStateError("requested_capabilities exceeds cardinality limit")
        normalized = tuple(
            sorted(
                _identifier(item, "requested_capability")
                for item in self.requested_capabilities
            )
        )
        if len(normalized) != len(set(normalized)):
            raise WorldStateError("requested_capabilities contains duplicates")
        object.__setattr__(self, "requested_capabilities", normalized)
        if self.authority_scope != "simulation":
            raise WorldStateError("simulation actions cannot request real authority")

    def to_wire(self) -> dict[str, object]:
        return {
            "schema": WORLD_STATE_SCHEMA,
            "action_id": self.action_id,
            "actor_id": self.actor_id,
            "intent": self.intent,
            "parameters": _thaw(self.parameters),
            "requested_capabilities": list(self.requested_capabilities),
            "authority_scope": self.authority_scope,
        }

    @property
    def digest(self) -> str:
        return _content_digest(self.to_wire(), "simulation action")

    @property
    def can_execute_real_side_effect(self) -> bool:
        return False

    def require_real_execution_authority(self) -> None:
        raise WorldStateError(
            "simulation action cannot be promoted to real execution authority"
        )


@dataclass(frozen=True, slots=True)
class SimulationEvidence:
    """Evidence envelope binding state/action/result inside simulation class."""

    simulation_id: str
    state_digest: str
    action_digest: str
    result_state_digest: str
    uncertainty: float
    lineage: tuple[str, ...] = ()
    evidence_class: str = "simulation"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "simulation_id", _identifier(self.simulation_id, "simulation_id")
        )
        for name in ("state_digest", "action_digest", "result_state_digest"):
            object.__setattr__(self, name, _digest(getattr(self, name), name))
        object.__setattr__(
            self, "uncertainty", _unit(self.uncertainty, "uncertainty")
        )
        if not isinstance(self.lineage, tuple):
            raise WorldStateError("lineage must be a tuple")
        if len(self.lineage) > _MAX_LINEAGE:
            raise WorldStateError("lineage exceeds cardinality limit")
        normalized = tuple(_digest(item, "lineage digest") for item in self.lineage)
        if len(normalized) != len(set(normalized)):
            raise WorldStateError("lineage contains duplicate digests")
        object.__setattr__(self, "lineage", normalized)
        if self.evidence_class != "simulation":
            raise WorldStateError("simulation evidence cannot escape simulation class")

    def to_wire(self) -> dict[str, object]:
        return {
            "schema": WORLD_STATE_SCHEMA,
            "simulation_id": self.simulation_id,
            "state_digest": self.state_digest,
            "action_digest": self.action_digest,
            "result_state_digest": self.result_state_digest,
            "uncertainty": self.uncertainty,
            "lineage": list(self.lineage),
            "evidence_class": self.evidence_class,
        }

    @property
    def digest(self) -> str:
        return _content_digest(self.to_wire(), "simulation evidence")

    @property
    def can_support_real_world_fact(self) -> bool:
        return False

    @property
    def can_satisfy_real_postcondition(self) -> bool:
        return False

    def require_real_world_authority(self) -> None:
        raise WorldStateError(
            "simulation evidence cannot authorize real-world facts or postconditions"
        )


def verify_transition(
    *,
    prior: WorldState,
    action: SimulationAction,
    result: WorldState,
    rules: WorldRules,
    simulation_id: str,
) -> SimulationEvidence:
    """Validate one state transition and emit typed simulation-only evidence."""

    if prior.world_id != result.world_id:
        raise WorldStateError("world_id changed across simulation transition")
    if result.tick != prior.tick + 1:
        raise WorldStateError("simulation state tick must advance exactly once")
    if prior.rules_digest != rules.digest or result.rules_digest != rules.digest:
        raise WorldStateError("state/rule digest disagreement")
    if result.parent_state_digest != prior.digest:
        raise WorldStateError("result state does not bind prior-state lineage")
    if result.uncertainty + 1e-15 < prior.uncertainty:
        raise WorldStateError("simulation uncertainty cannot decrease across transition")
    return SimulationEvidence(
        simulation_id=_identifier(simulation_id, "simulation_id"),
        state_digest=prior.digest,
        action_digest=action.digest,
        result_state_digest=result.digest,
        uncertainty=result.uncertainty,
        lineage=(prior.digest,),
    )


__all__ = [
    "WORLD_STATE_SCHEMA",
    "SimulationAction",
    "SimulationEvidence",
    "WorldRule",
    "WorldRules",
    "WorldState",
    "WorldStateError",
    "verify_transition",
]
