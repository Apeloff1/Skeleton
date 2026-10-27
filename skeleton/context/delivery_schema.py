"""Fail-closed bounded JSON output validation for the local delivery gate.

The accepted schema dialect is deliberately small and deterministic. Unknown
keywords fail admission, rather than becoming silently unenforced constraints.
This checks delivered data AFTER sampling; a native constrained sampler must
separately attest enforcement before inference.
"""

from __future__ import annotations

import json
import math
from typing import Any, Mapping

from skeleton.context.sealed_sandwich import SealedContextError, SealedContextLimitError

MAX_JSON_BYTES = 256 * 1024
MAX_SCHEMA_BYTES = 64 * 1024
MAX_DEPTH = 16
MAX_NODES = 4096
_TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean", "null"})
_KEYS = frozenset({
    "type", "properties", "required", "additionalProperties", "items", "enum", "const",
    "minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum",
})


def _error(message: str) -> None:
    raise SealedContextError("delivery JSON schema: " + message)


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            _error("duplicate object keys are forbidden")
        result[key] = value
    return result


def _finite(number: str) -> Any:
    value = float(number)
    if not math.isfinite(value):
        _error("non-finite numeric value")
    return value


def _reject_constant(value: str) -> None:
    _error("non-JSON numeric constant")


def _bounded_tree(value: Any, *, depth: int = 0, budget: list[int]) -> None:
    budget[0] += 1
    if budget[0] > MAX_NODES or depth > MAX_DEPTH:
        raise SealedContextLimitError("delivery JSON nesting or node budget exceeded")
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            _error("invalid surrogate Unicode scalar")
    elif isinstance(value, float):
        if not math.isfinite(value):
            _error("non-finite numeric value")
    elif isinstance(value, list):
        for child in value:
            _bounded_tree(child, depth=depth + 1, budget=budget)
    elif isinstance(value, dict):
        for key, child in value.items():
            _bounded_tree(key, depth=depth + 1, budget=budget)
            _bounded_tree(child, depth=depth + 1, budget=budget)


def _schema_node(schema: Any, *, depth: int, budget: list[int]) -> None:
    budget[0] += 1
    if budget[0] > MAX_NODES or depth > MAX_DEPTH:
        raise SealedContextLimitError("delivery schema nesting or node budget exceeded")
    if type(schema) is not dict or not schema or any(k not in _KEYS for k in schema):
        _error("unsupported or empty schema")
    kind = schema.get("type")
    if kind not in _TYPES:
        _error("schema type is required and must be supported")
    permitted = {
        "object": {"type", "properties", "required", "additionalProperties", "enum", "const"},
        "array": {"type", "items", "minItems", "maxItems", "enum", "const"},
        "string": {"type", "minLength", "maxLength", "enum", "const"},
        "integer": {"type", "minimum", "maximum", "enum", "const"},
        "number": {"type", "minimum", "maximum", "enum", "const"},
        "boolean": {"type", "enum", "const"},
        "null": {"type", "enum", "const"},
    }[kind]
    if any(key not in permitted for key in schema):
        _error("schema keyword cannot apply to declared type")
    if kind == "object":
        props = schema.get("properties", {})
        required = schema.get("required", [])
        additional = schema.get("additionalProperties", True)
        if (type(props) is not dict or type(required) is not list
                or any(type(k) is not str or not k or len(k) > 256 for k in props)
                or any(type(k) is not str or (additional is False and k not in props)
                       for k in required)
                or len(set(required)) != len(required) or type(additional) is not bool):
            _error("invalid object schema")
        for child in props.values():
            _schema_node(child, depth=depth + 1, budget=budget)
    if kind == "array":
        if "items" in schema:
            _schema_node(schema["items"], depth=depth + 1, budget=budget)
    for low, high in (("minItems", "maxItems"), ("minLength", "maxLength")):
        for key in (low, high):
            if key in schema and (type(schema[key]) is not int or not 0 <= schema[key] <= MAX_NODES):
                _error("invalid bounded length keyword")
        if low in schema and high in schema and schema[low] > schema[high]:
            _error("inverted length constraint")
    for key in ("minimum", "maximum"):
        if key in schema and (type(schema[key]) not in (int, float)
                              or not math.isfinite(schema[key])):
            _error("invalid numeric constraint")
    if "minimum" in schema and "maximum" in schema and schema["minimum"] > schema["maximum"]:
        _error("inverted numeric constraints")
    if "enum" in schema and (type(schema["enum"]) is not list
                             or not 1 <= len(schema["enum"]) <= 256):
        _error("enum must have a bounded nonempty list")
    if "enum" in schema:
        for val in schema["enum"]:
            _bounded_tree(val, budget=[0])
    if "const" in schema:
        _bounded_tree(schema["const"], budget=[0])


def validate_delivery_schema(schema: Mapping[str, Any] | None) -> None:
    """Validate a restricted JSON schema before allowing an inference run."""
    if schema is None:
        return
    if not isinstance(schema, Mapping):
        _error("schema must be an object")
    try:
        normalized = json.dumps(dict(schema), ensure_ascii=False, allow_nan=False,
                                sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise SealedContextError("delivery schema cannot be encoded") from exc
    if len(normalized) > MAX_SCHEMA_BYTES:
        raise SealedContextLimitError("delivery schema exceeds size budget")
    try:
        parsed = json.loads(normalized)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SealedContextError("delivery schema cannot be decoded") from exc
    _schema_node(parsed, depth=0, budget=[0])


def _type_ok(kind: str, data: Any) -> bool:
    return {
        "object": lambda: type(data) is dict,
        "array": lambda: type(data) is list,
        "string": lambda: type(data) is str,
        "integer": lambda: type(data) is int,
        "number": lambda: type(data) in (int, float),
        "boolean": lambda: type(data) is bool,
        "null": lambda: data is None,
    }[kind]()


def _matches(data: Any, schema: dict[str, Any]) -> None:
    kind = schema["type"]
    if not _type_ok(kind, data):
        _error("delivered value has wrong JSON type")
    # JSON equality must not coerce true == 1, which Python normally allows.
    canonical = lambda obj: json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=True, allow_nan=False)
    if "const" in schema and canonical(data) != canonical(schema["const"]):
        _error("delivered value violates const")
    if "enum" in schema and canonical(data) not in {canonical(item) for item in schema["enum"]}:
        _error("delivered value violates enum")
    if kind == "object":
        props = schema.get("properties", {})
        if any(key not in data for key in schema.get("required", [])):
            _error("required delivered property is missing")
        if schema.get("additionalProperties") is False and any(key not in props for key in data):
            _error("delivered object includes additional properties")
        for key, value in data.items():
            if key in props:
                _matches(value, props[key])
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(data) <= schema.get("maxItems", MAX_NODES):
            _error("delivered array violates item limits")
        if "items" in schema:
            for item in data:
                _matches(item, schema["items"])
    elif kind == "string":
        if not schema.get("minLength", 0) <= len(data) <= schema.get("maxLength", MAX_NODES):
            _error("delivered string violates length limits")
    elif kind in {"integer", "number"}:
        if data < schema.get("minimum", -math.inf) or data > schema.get("maximum", math.inf):
            _error("delivered number violates numeric limits")


def parse_and_validate_delivery_json(text: str, schema: Mapping[str, Any] | None = None) -> Any:
    """Reject malformed and over-budget outputs rather than releasing raw text."""
    validate_delivery_schema(schema)
    if not isinstance(text, str):
        _error("model output must be text")
    try:
        encoded = text.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise SealedContextError("delivery contains invalid Unicode") from exc
    if len(encoded) > MAX_JSON_BYTES:
        raise SealedContextLimitError("delivery JSON exceeds size budget")
    try:
        parsed = json.loads(text, object_pairs_hook=_pairs, parse_float=_finite,
                            parse_constant=_reject_constant)
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise SealedContextError("delivery JSON is invalid or exceeds structural bounds") from exc
    _bounded_tree(parsed, budget=[0])
    if schema is not None:
        normalized = json.loads(json.dumps(dict(schema), allow_nan=False))
        _matches(parsed, normalized)
    return parsed
