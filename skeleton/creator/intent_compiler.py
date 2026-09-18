"""Engine-neutral creator intent-to-design-plan compiler.

Turns a structured creator request into a deterministic design graph with
explicit assumptions, constraints, editable nodes, dependencies, and
validation requirements.

This module is the versioned ``creator.intent.v1`` surface. It produces data,
not execution: there is no path that runs code, talks to a network, or mutates
an engine. Materialisation stays in ``skeleton.forge``; this compiler only
decides the design graph a later planner or adapter may consume.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, NoReturn

from skeleton.kernel.errors import SkeletonError

INTENT_SCHEMA: Final = "creator.intent.v1"
DESIGN_PLAN_SCHEMA: Final = "creator.design_plan.v1"
EDIT_SCHEMA: Final = "creator.intent.edit.v1"
INTENT_VERSION: Final = 1

MAX_ID_CHARS: Final = 64
MAX_TITLE_CHARS: Final = 120
MAX_TEXT_CHARS: Final = 4_096
MAX_NODES: Final = 256
MAX_EDGES: Final = 1_024
MAX_ASSUMPTIONS: Final = 64
MAX_CONSTRAINTS: Final = 64
MAX_VALIDATIONS: Final = 64
MAX_DEPENDENCIES_PER_NODE: Final = 32
MAX_EDIT_LOG: Final = 32
MAX_CANONICAL_BYTES: Final = 256 * 1_024
MAX_LIST_ITEMS: Final = 1_024

_ID_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_REQUEST_KEYS: Final = frozenset(
    {
        "schema",
        "schema_version",
        "kind",
        "request_id",
        "title",
        "goal",
        "assumptions",
        "constraints",
        "validations",
        "nodes",
    }
)
_ASSUMPTION_KEYS: Final = frozenset({"id", "statement"})
_CONSTRAINT_KEYS: Final = frozenset({"id", "field", "op", "value"})
_VALIDATION_KEYS: Final = frozenset({"id", "requirement", "applies_to"})
_NODE_KEYS: Final = frozenset(
    {
        "id",
        "kind",
        "title",
        "summary",
        "depends_on",
        "editable",
        "assumption_ids",
        "constraint_ids",
        "validation_ids",
    }
)
_PLAN_KEYS: Final = frozenset(
    {
        "schema",
        "schema_version",
        "request_id",
        "title",
        "goal",
        "assumptions",
        "constraints",
        "validations",
        "nodes",
        "waves",
        "provenance",
        "revision",
        "edit_log",
        "digest",
    }
)
_EDIT_KEYS: Final = frozenset(
    {"schema", "schema_version", "edit_id", "op", "node_id", "field", "value"}
)
_NODE_KINDS: Final = frozenset(
    {"concept", "system", "mechanic", "content", "world", "interface", "validation"}
)
_CONSTRAINT_OPS: Final = frozenset({"require", "forbid", "equals", "min", "max"})
_EDIT_OPS: Final = frozenset({"set_field", "add_dependency", "remove_dependency"})
_EDITABLE_FIELDS: Final = frozenset({"title", "summary"})
_EXECUTION_KEYS: Final = frozenset(
    {
        "code",
        "script",
        "exec",
        "eval",
        "compile",
        "bytecode",
        "subprocess",
        "import",
        "gdscript",
    }
)
_ENGINE_MUTATION_KEYS: Final = frozenset(
    {
        "engine",
        "godot",
        "mutate",
        "runtime",
        "scene_tree",
        "autoload",
        "autoloads",
        "singleton",
        "singletons",
        "Engine",
        "engine_global",
        "network",
        "socket",
        "http",
    }
)


class IntentCompilerError(SkeletonError):
    """Malformed, ambiguous, or out-of-contract creator intent."""

    code = "CRE.INTENT"
    http_status = 422


class IntentVersionError(IntentCompilerError):
    """Intent or design-plan schema version is not this boundary."""

    code = "CRE.INTENT_VERSION"


def _fail(message: str, *, reason: str, **context: Any) -> NoReturn:
    raise IntentCompilerError(message, context={"reason": reason, **context})


def _strict_int(name: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{name} must be an integer", reason="malformed", field=name)
    if not minimum <= value <= maximum:
        _fail(
            f"{name} is outside the accepted range",
            reason="bound",
            field=name,
            minimum=minimum,
            maximum=maximum,
        )
    return value


def _strict_bool(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        _fail(f"{name} must be a boolean", reason="malformed", field=name)
    return value


def _token(name: str, value: object, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{name} must be a non-empty string", reason="malformed", field=name)
    token = value.strip()
    if len(token) > maximum:
        _fail(
            f"{name} exceeds {maximum} characters",
            reason="bound",
            field=name,
            max_chars=maximum,
        )
    return token


def _identifier(name: str, value: object) -> str:
    token = _token(name, value, maximum=MAX_ID_CHARS)
    if not _ID_PATTERN.fullmatch(token):
        _fail(
            f"{name} is not a canonical identifier",
            reason="malformed",
            field=name,
            value=token,
        )
    return token


def _mapping(name: str, value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{name} must be a mapping", reason="malformed", field=name)
    return value


def _sequence(name: str, value: object) -> Sequence[Any]:
    if isinstance(value, (str, bytes, bytearray, Mapping)) or not isinstance(value, Sequence):
        _fail(f"{name} must be a list", reason="malformed", field=name)
    if len(value) > MAX_LIST_ITEMS:
        _fail(
            f"{name} exceeds {MAX_LIST_ITEMS} items",
            reason="bound",
            field=name,
            max_items=MAX_LIST_ITEMS,
        )
    return value


def _json_scalar(name: str, value: object) -> object:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail(f"{name} must be finite", reason="malformed", field=name)
        return float(value)
    _fail(f"{name} must be a JSON scalar", reason="malformed", field=name)


def _reject_unknown(name: str, payload: Mapping[str, Any], allowed: frozenset[str]) -> None:
    extra = tuple(sorted(str(key) for key in payload if key not in allowed))
    if extra:
        _fail(
            f"{name} has unsupported fields",
            reason="schema_drift",
            field=name,
            fields=extra,
        )


def _reject_execution_and_engine_keys(name: str, payload: Mapping[str, Any]) -> None:
    present_exec = tuple(sorted(key for key in payload if key in _EXECUTION_KEYS))
    if present_exec:
        _fail(
            f"{name} requests direct code execution",
            reason="execution",
            field=name,
            fields=present_exec,
        )
    present_engine = tuple(sorted(key for key in payload if key in _ENGINE_MUTATION_KEYS))
    if present_engine:
        _fail(
            f"{name} requests engine mutation",
            reason="engine_mutation",
            field=name,
            fields=present_engine,
        )


def _unique_ids(name: str, items: Sequence[str]) -> tuple[str, ...]:
    seen: list[str] = []
    duplicates: list[str] = []
    for item in items:
        if item in seen:
            duplicates.append(item)
        else:
            seen.append(item)
    if duplicates:
        _fail(
            f"{name} contains duplicate ids",
            reason="ambiguous",
            field=name,
            duplicates=tuple(duplicates),
        )
    return tuple(seen)


def _id_list(name: str, value: object) -> tuple[str, ...]:
    return _unique_ids(name, [_identifier(f"{name} item", item) for item in _sequence(name, value)])


def canonical_dumps(payload: Mapping[str, Any]) -> str:
    """Byte-stable JSON for identical design graphs."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = canonical_dumps(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_known(name: str, ids: Sequence[str], known: Mapping[str, Any]) -> None:
    missing = tuple(item for item in ids if item not in known)
    if missing:
        _fail(
            f"{name} references unknown ids",
            reason="malformed",
            field=name,
            missing=missing,
        )


@dataclass(frozen=True, slots=True)
class Assumption:
    assumption_id: str
    statement: str
    source_path: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.assumption_id,
            "source_path": self.source_path,
            "statement": self.statement,
        }


@dataclass(frozen=True, slots=True)
class Constraint:
    constraint_id: str
    field: str
    op: str
    value: object
    source_path: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "id": self.constraint_id,
            "op": self.op,
            "source_path": self.source_path,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class ValidationRequirement:
    validation_id: str
    requirement: str
    applies_to: tuple[str, ...]
    source_path: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "applies_to": list(self.applies_to),
            "id": self.validation_id,
            "requirement": self.requirement,
            "source_path": self.source_path,
        }


@dataclass(frozen=True, slots=True)
class ProvenanceLink:
    target_id: str
    target_kind: str
    source_path: str
    request_field: str
    request_id: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "request_field": self.request_field,
            "request_id": self.request_id,
            "source_path": self.source_path,
            "target_id": self.target_id,
            "target_kind": self.target_kind,
        }


@dataclass(frozen=True, slots=True)
class DesignNode:
    node_id: str
    kind: str
    title: str
    summary: str
    depends_on: tuple[str, ...]
    editable: bool
    assumption_ids: tuple[str, ...]
    constraint_ids: tuple[str, ...]
    validation_ids: tuple[str, ...]
    source_path: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "assumption_ids": list(self.assumption_ids),
            "constraint_ids": list(self.constraint_ids),
            "depends_on": list(self.depends_on),
            "editable": self.editable,
            "id": self.node_id,
            "kind": self.kind,
            "source_path": self.source_path,
            "summary": self.summary,
            "title": self.title,
            "validation_ids": list(self.validation_ids),
        }


@dataclass(frozen=True, slots=True)
class DesignEdit:
    edit_id: str
    op: str
    node_id: str
    field: str | None
    value: object
    inverse: Mapping[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "edit_id": self.edit_id,
            "field": self.field,
            "inverse": None if self.inverse is None else dict(self.inverse),
            "node_id": self.node_id,
            "op": self.op,
            "schema": EDIT_SCHEMA,
            "schema_version": INTENT_VERSION,
            "value": self.value,
        }
        return payload


@dataclass(frozen=True, slots=True)
class DesignPlan:
    """Deterministic, reversible design graph compiled from a creator request."""

    schema: str
    schema_version: int
    request_id: str
    title: str
    goal: str
    assumptions: tuple[Assumption, ...]
    constraints: tuple[Constraint, ...]
    validations: tuple[ValidationRequirement, ...]
    nodes: tuple[DesignNode, ...]
    waves: tuple[tuple[str, ...], ...]
    provenance: tuple[ProvenanceLink, ...]
    revision: int
    edit_log: tuple[DesignEdit, ...]

    def graph_payload(self) -> dict[str, Any]:
        """Stable design-graph document, excluding reversible edit history."""

        return {
            "assumptions": [item.to_payload() for item in self.assumptions],
            "constraints": [item.to_payload() for item in self.constraints],
            "goal": self.goal,
            "nodes": [item.to_payload() for item in self.nodes],
            "provenance": [item.to_payload() for item in self.provenance],
            "request_id": self.request_id,
            "schema": self.schema,
            "schema_version": self.schema_version,
            "title": self.title,
            "validations": [item.to_payload() for item in self.validations],
            "waves": [list(wave) for wave in self.waves],
        }

    def to_payload(self) -> dict[str, Any]:
        payload = self.graph_payload()
        payload["digest"] = _digest(payload)
        payload["edit_log"] = [item.to_payload() for item in self.edit_log]
        payload["revision"] = self.revision
        return payload

    def canonical_json(self) -> str:
        return canonical_dumps(self.to_payload())

    def digest(self) -> str:
        return str(self.to_payload()["digest"])

    def node_map(self) -> dict[str, DesignNode]:
        return {node.node_id: node for node in self.nodes}


def _parse_assumptions(raw: object) -> tuple[Assumption, ...]:
    items = [_mapping("assumptions item", item) for item in _sequence("assumptions", raw)]
    if len(items) > MAX_ASSUMPTIONS:
        _fail("too many assumptions", reason="bound", max_items=MAX_ASSUMPTIONS)
    parsed: list[Assumption] = []
    for item in items:
        _reject_unknown("assumption", item, _ASSUMPTION_KEYS)
        assumption_id = _identifier("assumption.id", item.get("id"))
        parsed.append(
            Assumption(
                assumption_id=assumption_id,
                statement=_token("assumption.statement", item.get("statement"), maximum=MAX_TEXT_CHARS),
                source_path=f"assumptions.{assumption_id}",
            )
        )
    ordered = tuple(sorted(parsed, key=lambda item: item.assumption_id))
    _unique_ids("assumptions", [item.assumption_id for item in ordered])
    return ordered


def _parse_constraints(raw: object) -> tuple[Constraint, ...]:
    items = [_mapping("constraints item", item) for item in _sequence("constraints", raw)]
    if len(items) > MAX_CONSTRAINTS:
        _fail("too many constraints", reason="bound", max_items=MAX_CONSTRAINTS)
    parsed: list[Constraint] = []
    for item in items:
        _reject_unknown("constraint", item, _CONSTRAINT_KEYS)
        constraint_id = _identifier("constraint.id", item.get("id"))
        op = _token("constraint.op", item.get("op"), maximum=16)
        if op not in _CONSTRAINT_OPS:
            _fail("constraint.op is not supported", reason="malformed", op=op)
        if "value" not in item:
            _fail("constraint.value is required", reason="malformed", field="constraint.value")
        parsed.append(
            Constraint(
                constraint_id=constraint_id,
                field=_identifier("constraint.field", item.get("field")),
                op=op,
                value=_json_scalar("constraint.value", item.get("value")),
                source_path=f"constraints.{constraint_id}",
            )
        )
    ordered = tuple(sorted(parsed, key=lambda item: item.constraint_id))
    _unique_ids("constraints", [item.constraint_id for item in ordered])
    _reject_constraint_conflicts(ordered)
    return ordered


def _reject_constraint_conflicts(constraints: Sequence[Constraint]) -> None:
    by_field: dict[str, list[Constraint]] = {}
    for constraint in constraints:
        by_field.setdefault(constraint.field, []).append(constraint)
    for field, group in by_field.items():
        equals = [item for item in group if item.op == "equals"]
        unique_equals = {canonical_dumps({"v": item.value}) for item in equals}
        if len(unique_equals) > 1:
            _fail(
                "constraints disagree on an equals value",
                reason="ambiguous",
                field=field,
            )
        required = {canonical_dumps({"v": item.value}) for item in group if item.op == "require"}
        forbidden = {canonical_dumps({"v": item.value}) for item in group if item.op == "forbid"}
        overlap = tuple(sorted(required & forbidden))
        if overlap:
            _fail(
                "constraints both require and forbid the same value",
                reason="ambiguous",
                field=field,
                values=overlap,
            )
        if unique_equals and unique_equals & forbidden:
            _fail(
                "equals constraint is also forbidden",
                reason="ambiguous",
                field=field,
            )
        mins = [_finite_constraint("min", item.value) for item in group if item.op == "min"]
        maxes = [_finite_constraint("max", item.value) for item in group if item.op == "max"]
        if mins and maxes and max(mins) > min(maxes):
            _fail("min constraint exceeds max constraint", reason="ambiguous", field=field)
        if unique_equals and (mins or maxes):
            equals_value = next(item.value for item in equals)
            number = _finite_constraint("equals", equals_value)
            if mins and number < max(mins):
                _fail("equals constraint is below min", reason="ambiguous", field=field)
            if maxes and number > min(maxes):
                _fail("equals constraint is above max", reason="ambiguous", field=field)


def _finite_constraint(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"constraint.{name} must be numeric", reason="malformed", field=name)
    number = float(value)
    if not math.isfinite(number):
        _fail(f"constraint.{name} must be finite", reason="malformed", field=name)
    return number


def _parse_validations(raw: object, *, known_nodes: set[str] | None = None) -> tuple[ValidationRequirement, ...]:
    items = [_mapping("validations item", item) for item in _sequence("validations", raw)]
    if len(items) > MAX_VALIDATIONS:
        _fail("too many validations", reason="bound", max_items=MAX_VALIDATIONS)
    parsed: list[ValidationRequirement] = []
    for item in items:
        _reject_unknown("validation", item, _VALIDATION_KEYS)
        validation_id = _identifier("validation.id", item.get("id"))
        applies_to = _id_list("validation.applies_to", item.get("applies_to", []))
        if known_nodes is not None:
            _require_known("validation.applies_to", applies_to, {node: None for node in known_nodes})
        parsed.append(
            ValidationRequirement(
                validation_id=validation_id,
                requirement=_token(
                    "validation.requirement", item.get("requirement"), maximum=MAX_TEXT_CHARS
                ),
                applies_to=tuple(sorted(applies_to)),
                source_path=f"validations.{validation_id}",
            )
        )
    ordered = tuple(sorted(parsed, key=lambda item: item.validation_id))
    _unique_ids("validations", [item.validation_id for item in ordered])
    return ordered


def _parse_nodes(
    raw: object,
    *,
    assumptions: Mapping[str, Assumption],
    constraints: Mapping[str, Constraint],
    validations: Mapping[str, ValidationRequirement],
) -> tuple[DesignNode, ...]:
    items = [_mapping("nodes item", item) for item in _sequence("nodes", raw)]
    if not items:
        _fail("nodes must not be empty", reason="malformed", field="nodes")
    if len(items) > MAX_NODES:
        _fail("too many nodes", reason="bound", max_items=MAX_NODES)
    parsed: list[DesignNode] = []
    for item in items:
        _reject_execution_and_engine_keys("node", item)
        _reject_unknown("node", item, _NODE_KEYS)
        node_id = _identifier("node.id", item.get("id"))
        kind = _token("node.kind", item.get("kind"), maximum=32)
        if kind not in _NODE_KINDS:
            _fail("node.kind is not supported", reason="malformed", kind=kind, node_id=node_id)
        depends_on = _id_list("node.depends_on", item.get("depends_on", []))
        if len(depends_on) > MAX_DEPENDENCIES_PER_NODE:
            _fail("too many dependencies on one node", reason="bound", node_id=node_id)
        if node_id in depends_on:
            _fail("node depends on itself", reason="cycle", node_id=node_id)
        assumption_ids = _id_list("node.assumption_ids", item.get("assumption_ids", []))
        constraint_ids = _id_list("node.constraint_ids", item.get("constraint_ids", []))
        validation_ids = _id_list("node.validation_ids", item.get("validation_ids", []))
        _require_known("node.assumption_ids", assumption_ids, assumptions)
        _require_known("node.constraint_ids", constraint_ids, constraints)
        _require_known("node.validation_ids", validation_ids, validations)
        if "editable" not in item:
            _fail("node.editable is required", reason="malformed", node_id=node_id)
        raw_summary = item.get("summary", "")
        if raw_summary in ("", None):
            summary = ""
        else:
            summary = _token("node.summary", raw_summary, maximum=MAX_TEXT_CHARS)
        parsed.append(
            DesignNode(
                node_id=node_id,
                kind=kind,
                title=_token("node.title", item.get("title"), maximum=MAX_TITLE_CHARS),
                summary=summary,
                depends_on=tuple(sorted(depends_on)),
                editable=_strict_bool("node.editable", item.get("editable")),
                assumption_ids=tuple(sorted(assumption_ids)),
                constraint_ids=tuple(sorted(constraint_ids)),
                validation_ids=tuple(sorted(validation_ids)),
                source_path=f"nodes.{node_id}",
            )
        )
    ordered = tuple(sorted(parsed, key=lambda item: item.node_id))
    _unique_ids("nodes", [item.node_id for item in ordered])
    _reject_ambiguous_titles(ordered)
    known = {node.node_id: node for node in ordered}
    edge_count = 0
    for node in ordered:
        _require_known("node.depends_on", node.depends_on, known)
        edge_count += len(node.depends_on)
    if edge_count > MAX_EDGES:
        _fail("too many dependency edges", reason="bound", max_items=MAX_EDGES)
    return ordered


def _reject_ambiguous_titles(nodes: Sequence[DesignNode]) -> None:
    titles: dict[tuple[str, str], str] = {}
    for node in nodes:
        key = (node.kind, node.title)
        existing = titles.get(key)
        if existing is not None:
            _fail(
                "nodes share an ambiguous kind and title",
                reason="ambiguous",
                kind=node.kind,
                title=node.title,
                nodes=(existing, node.node_id),
            )
        titles[key] = node.node_id


def _clone_node(
    node: DesignNode,
    *,
    title: str | None = None,
    summary: str | None = None,
    depends_on: tuple[str, ...] | None = None,
    editable: bool | None = None,
) -> DesignNode:
    return DesignNode(
        node_id=node.node_id,
        kind=node.kind,
        title=node.title if title is None else title,
        summary=node.summary if summary is None else summary,
        depends_on=node.depends_on if depends_on is None else depends_on,
        editable=node.editable if editable is None else editable,
        assumption_ids=node.assumption_ids,
        constraint_ids=node.constraint_ids,
        validation_ids=node.validation_ids,
        source_path=node.source_path,
    )


def _waves(nodes: Sequence[DesignNode]) -> tuple[tuple[str, ...], ...]:
    known = {node.node_id: node for node in nodes}
    wave_of: dict[str, int] = {}

    def wave(node_id: str, seen: frozenset[str] = frozenset()) -> int:
        if node_id in wave_of:
            return wave_of[node_id]
        if node_id in seen:
            _fail("dependency cycle during compile", reason="cycle", node_id=node_id)
        parents = [dep for dep in known[node_id].depends_on if dep in known]
        assigned = 0 if not parents else max(wave(parent, seen | {node_id}) for parent in parents) + 1
        wave_of[node_id] = assigned
        return assigned

    for node in known:
        wave(node)
    count = max(wave_of.values()) + 1
    return tuple(
        tuple(sorted(node_id for node_id, assigned in wave_of.items() if assigned == index))
        for index in range(count)
    )


def _provenance(
    *,
    request_id: str,
    title: str,
    goal: str,
    assumptions: Sequence[Assumption],
    constraints: Sequence[Constraint],
    validations: Sequence[ValidationRequirement],
    nodes: Sequence[DesignNode],
) -> tuple[ProvenanceLink, ...]:
    links = [
        ProvenanceLink(request_id, "request", "request_id", "request_id", request_id),
        ProvenanceLink(request_id, "request", "title", "title", request_id),
        ProvenanceLink(request_id, "request", "goal", "goal", request_id),
    ]
    for assumption in assumptions:
        links.append(
            ProvenanceLink(
                assumption.assumption_id,
                "assumption",
                f"{assumption.source_path}.statement",
                "statement",
                request_id,
            )
        )
    for constraint in constraints:
        links.append(
            ProvenanceLink(
                constraint.constraint_id,
                "constraint",
                constraint.source_path,
                "constraint",
                request_id,
            )
        )
    for validation in validations:
        links.append(
            ProvenanceLink(
                validation.validation_id,
                "validation",
                f"{validation.source_path}.requirement",
                "requirement",
                request_id,
            )
        )
    for node in nodes:
        links.append(
            ProvenanceLink(node.node_id, "node", f"{node.source_path}.title", "title", request_id)
        )
        links.append(
            ProvenanceLink(node.node_id, "node", f"{node.source_path}.kind", "kind", request_id)
        )
        if node.summary:
            links.append(
                ProvenanceLink(
                    node.node_id, "node", f"{node.source_path}.summary", "summary", request_id
                )
            )
        for dep in node.depends_on:
            links.append(
                ProvenanceLink(
                    node.node_id, "node", f"{node.source_path}.depends_on.{dep}", "depends_on", request_id
                )
            )
    return tuple(
        sorted(links, key=lambda item: (item.target_kind, item.target_id, item.source_path))
    )


def _bound_canonical(plan: DesignPlan) -> DesignPlan:
    encoded = plan.canonical_json().encode("utf-8")
    if len(encoded) > MAX_CANONICAL_BYTES:
        _fail(
            "canonical design plan exceeds the size bound",
            reason="bound",
            size_bytes=len(encoded),
            max_bytes=MAX_CANONICAL_BYTES,
        )
    return plan


def _rebuild(
    plan: DesignPlan,
    *,
    nodes: tuple[DesignNode, ...] | None = None,
    revision: int | None = None,
    edit_log: tuple[DesignEdit, ...] | None = None,
) -> DesignPlan:
    next_nodes = nodes if nodes is not None else plan.nodes
    ordered = tuple(sorted(next_nodes, key=lambda item: item.node_id))
    _reject_ambiguous_titles(ordered)
    rebuilt = DesignPlan(
        schema=DESIGN_PLAN_SCHEMA,
        schema_version=INTENT_VERSION,
        request_id=plan.request_id,
        title=plan.title,
        goal=plan.goal,
        assumptions=plan.assumptions,
        constraints=plan.constraints,
        validations=plan.validations,
        nodes=ordered,
        waves=_waves(ordered),
        provenance=plan.provenance,
        revision=plan.revision if revision is None else revision,
        edit_log=plan.edit_log if edit_log is None else edit_log,
    )
    return _bound_canonical(rebuilt)


def _parse_edit(raw: Mapping[str, Any] | DesignEdit) -> DesignEdit:
    if isinstance(raw, DesignEdit):
        payload = raw.to_payload()
    else:
        payload = dict(_mapping("edit", raw))
    _reject_execution_and_engine_keys("edit", payload)
    _reject_unknown("edit", payload, _EDIT_KEYS | frozenset({"inverse"}))
    schema = _token("edit.schema", payload.get("schema", EDIT_SCHEMA), maximum=64)
    version = _strict_int("edit.schema_version", payload.get("schema_version", INTENT_VERSION), minimum=1, maximum=1)
    if schema != EDIT_SCHEMA or version != INTENT_VERSION:
        raise IntentVersionError(
            "edit schema is not this boundary",
            context={"reason": "schema_drift", "schema": schema, "schema_version": version},
        )
    op = _token("edit.op", payload.get("op"), maximum=32)
    if op not in _EDIT_OPS:
        _fail("edit.op is not supported", reason="invalid_edit", op=op)
    field = payload.get("field")
    parsed_field = None if field is None else _token("edit.field", field, maximum=32)
    if op == "set_field":
        if parsed_field not in _EDITABLE_FIELDS:
            _fail("edit.field is not editable", reason="invalid_edit", field=parsed_field)
        if parsed_field == "title":
            value: object = _token("edit.value", payload.get("value"), maximum=MAX_TITLE_CHARS)
        else:
            value = _token("edit.value", payload.get("value"), maximum=MAX_TEXT_CHARS)
    else:
        if parsed_field not in (None, "depends_on"):
            _fail("dependency edits cannot set another field", reason="invalid_edit", field=parsed_field)
        parsed_field = "depends_on"
        value = _identifier("edit.value", payload.get("value"))
    inverse_raw = payload.get("inverse")
    inverse = None if inverse_raw is None else dict(_mapping("edit.inverse", inverse_raw))
    return DesignEdit(
        edit_id=_identifier("edit.edit_id", payload.get("edit_id")),
        op=op,
        node_id=_identifier("edit.node_id", payload.get("node_id")),
        field=parsed_field,
        value=value,
        inverse=inverse,
    )


def _replace_node(plan: DesignPlan, node: DesignNode) -> tuple[DesignNode, ...]:
    return tuple(node if item.node_id == node.node_id else item for item in plan.nodes)


def _inverse_payload(edit: DesignEdit) -> dict[str, Any]:
    return {
        "edit_id": edit.edit_id,
        "field": edit.field,
        "node_id": edit.node_id,
        "op": edit.op,
        "schema": EDIT_SCHEMA,
        "schema_version": INTENT_VERSION,
        "value": edit.value,
    }


def _apply_node_mutation(
    plan: DesignPlan,
    node: DesignNode,
    parsed: DesignEdit,
    *,
    require_editable: bool = True,
) -> tuple[DesignNode, DesignEdit]:
    if require_editable and not node.editable:
        _fail("node is not editable", reason="invalid_edit", node_id=parsed.node_id)
    nodes = plan.node_map()
    if parsed.op == "set_field":
        current = getattr(node, parsed.field or "")
        if current == parsed.value:
            _fail("edit does not change the node", reason="invalid_edit", node_id=parsed.node_id)
        updated = _clone_node(
            node,
            title=str(parsed.value) if parsed.field == "title" else None,
            summary=str(parsed.value) if parsed.field == "summary" else None,
        )
        inverse = DesignEdit(
            edit_id=f"{parsed.edit_id}_undo",
            op="set_field",
            node_id=node.node_id,
            field=parsed.field,
            value=current,
        )
        return updated, inverse
    dep = str(parsed.value)
    if dep not in nodes:
        _fail("dependency target is unknown", reason="invalid_edit", node_id=dep)
    current_deps = list(node.depends_on)
    if parsed.op == "add_dependency":
        if dep in current_deps:
            _fail("dependency already exists", reason="invalid_edit", node_id=parsed.node_id)
        current_deps.append(dep)
        inverse_op = "remove_dependency"
    else:
        if dep not in current_deps:
            _fail("dependency is not present", reason="invalid_edit", node_id=parsed.node_id)
        current_deps.remove(dep)
        inverse_op = "add_dependency"
    updated = _clone_node(node, depends_on=tuple(sorted(current_deps)))
    inverse = DesignEdit(
        edit_id=f"{parsed.edit_id}_undo",
        op=inverse_op,
        node_id=node.node_id,
        field="depends_on",
        value=dep,
    )
    return updated, inverse


@dataclass(frozen=True, slots=True)
class IntentCompiler:
    """Stateless intent compiler. Construct per call; no engine or model state."""

    schema: str = INTENT_SCHEMA
    schema_version: int = INTENT_VERSION

    def __post_init__(self) -> None:
        version = self.schema_version
        if isinstance(version, bool) or not isinstance(version, int) or version != INTENT_VERSION:
            raise IntentVersionError(
                "compiler instance version is not this boundary",
                context={
                    "reason": "schema_drift",
                    "schema": self.schema,
                    "schema_version": version,
                },
            )
        if self.schema != INTENT_SCHEMA:
            raise IntentVersionError(
                "compiler instance version is not this boundary",
                context={"reason": "schema_drift", "schema": self.schema, "schema_version": version},
            )

    def compile(self, request: Mapping[str, Any]) -> DesignPlan:
        payload = _mapping("request", request)
        _reject_execution_and_engine_keys("request", payload)
        _reject_unknown("request", payload, _REQUEST_KEYS)
        schema = _token("schema", payload.get("schema"), maximum=64)
        raw_version = payload.get("schema_version")
        if isinstance(raw_version, bool) or not isinstance(raw_version, int):
            raise IntentVersionError(
                "schema_version must be an integer",
                context={
                    "reason": "schema_drift",
                    "schema": schema,
                    "schema_version": raw_version,
                },
            )
        if schema != INTENT_SCHEMA or raw_version != INTENT_VERSION:
            raise IntentVersionError(
                "intent schema is not this boundary",
                context={
                    "reason": "schema_drift",
                    "schema": schema,
                    "schema_version": raw_version,
                },
            )
        kind = payload.get("kind")
        if kind is not None and _token("kind", kind, maximum=64) != INTENT_SCHEMA:
            _fail("kind does not match schema", reason="schema_drift", kind=kind)
        request_id = _identifier("request_id", payload.get("request_id"))
        title = _token("title", payload.get("title"), maximum=MAX_TITLE_CHARS)
        goal = _token("goal", payload.get("goal"), maximum=MAX_TEXT_CHARS)
        assumptions = _parse_assumptions(payload.get("assumptions", []))
        constraints = _parse_constraints(payload.get("constraints", []))
        assumption_map = {item.assumption_id: item for item in assumptions}
        constraint_map = {item.constraint_id: item for item in constraints}
        node_ids = {
            _identifier("node.id", _mapping("nodes item", item).get("id"))
            for item in _sequence("nodes", payload.get("nodes"))
        }
        validations = _parse_validations(payload.get("validations", []), known_nodes=node_ids)
        validation_map = {item.validation_id: item for item in validations}
        nodes = _parse_nodes(
            payload.get("nodes"),
            assumptions=assumption_map,
            constraints=constraint_map,
            validations=validation_map,
        )
        for validation in validations:
            _require_known(
                "validation.applies_to",
                validation.applies_to,
                {node.node_id: node for node in nodes},
            )
        plan = DesignPlan(
            schema=DESIGN_PLAN_SCHEMA,
            schema_version=INTENT_VERSION,
            request_id=request_id,
            title=title,
            goal=goal,
            assumptions=assumptions,
            constraints=constraints,
            validations=validations,
            nodes=nodes,
            waves=_waves(nodes),
            provenance=_provenance(
                request_id=request_id,
                title=title,
                goal=goal,
                assumptions=assumptions,
                constraints=constraints,
                validations=validations,
                nodes=nodes,
            ),
            revision=0,
            edit_log=(),
        )
        return _bound_canonical(plan)

    def apply_edit(
        self, plan: DesignPlan, edit: Mapping[str, Any] | DesignEdit
    ) -> tuple[DesignPlan, DesignEdit]:
        if plan.schema != DESIGN_PLAN_SCHEMA or plan.schema_version != INTENT_VERSION:
            raise IntentVersionError(
                "design plan schema is not this boundary",
                context={
                    "reason": "schema_drift",
                    "schema": plan.schema,
                    "schema_version": plan.schema_version,
                },
            )
        parsed = _parse_edit(edit)
        if any(existing.edit_id == parsed.edit_id for existing in plan.edit_log):
            _fail("edit_id already applied", reason="invalid_edit", edit_id=parsed.edit_id)
        if len(plan.edit_log) >= MAX_EDIT_LOG:
            _fail("edit log is exhausted", reason="bound", max_items=MAX_EDIT_LOG)
        nodes = plan.node_map()
        node = nodes.get(parsed.node_id)
        if node is None:
            _fail("edit targets an unknown node", reason="invalid_edit", node_id=parsed.node_id)
        if not node.editable:
            _fail("node is not editable", reason="invalid_edit", node_id=parsed.node_id)
        updated, inverse = _apply_node_mutation(plan, node, parsed)
        recorded = DesignEdit(
            edit_id=parsed.edit_id,
            op=parsed.op,
            node_id=parsed.node_id,
            field=parsed.field,
            value=parsed.value,
            inverse=_inverse_payload(inverse),
        )
        next_plan = _rebuild(
            plan,
            nodes=_replace_node(plan, updated),
            revision=plan.revision + 1,
            edit_log=plan.edit_log + (recorded,),
        )
        return next_plan, recorded

    def revert(self, plan: DesignPlan, inverse: Mapping[str, Any] | DesignEdit | None = None) -> DesignPlan:
        if not plan.edit_log:
            _fail("no reversible edit is available", reason="invalid_edit")
        latest = plan.edit_log[-1]
        if latest.inverse is None:
            _fail("latest edit is missing an inverse", reason="invalid_edit", edit_id=latest.edit_id)
        expected = _parse_edit(dict(latest.inverse))
        if inverse is not None:
            provided = _parse_edit(inverse)
            if (
                provided.op != expected.op
                or provided.node_id != expected.node_id
                or provided.field != expected.field
                or provided.value != expected.value
            ):
                _fail("inverse does not match the latest edit", reason="invalid_edit")
        nodes = plan.node_map()
        node = nodes.get(expected.node_id)
        if node is None:
            _fail("revert targets an unknown node", reason="invalid_edit", node_id=expected.node_id)
        updated, _ignored = _apply_node_mutation(plan, node, expected, require_editable=False)
        return _rebuild(
            plan,
            nodes=_replace_node(plan, _clone_node(updated, editable=node.editable)),
            revision=plan.revision + 1,
            edit_log=plan.edit_log[:-1],
        )


def compile_intent(request: Mapping[str, Any]) -> DesignPlan:
    return IntentCompiler().compile(request)


def apply_edit(plan: DesignPlan, edit: Mapping[str, Any] | DesignEdit) -> tuple[DesignPlan, DesignEdit]:
    return IntentCompiler().apply_edit(plan, edit)


def revert_edit(
    plan: DesignPlan, inverse: Mapping[str, Any] | DesignEdit | None = None
) -> DesignPlan:
    return IntentCompiler().revert(plan, inverse)
