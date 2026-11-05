"""Small deterministic JSON-schema subset for model-originated Jeeves answers.

There is deliberately no trust transfer from a model's self-reported schema
conformance. Unknown schema keywords fail closed rather than being silently
ignored. Both schema and model output are bounded before recursive inspection.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Any, Mapping


class NativeSchemaError(ValueError):
    """Structured output failed the host-authoritative contract."""


_SCHEMA_KEYS = frozenset({
    "type", "properties", "required", "items", "additionalProperties",
    "minimum", "maximum", "enum", "minItems", "maxItems",
    "minLength", "maxLength",
})
_TYPES = frozenset({"object", "array", "string", "number", "integer", "boolean", "null"})


def _pairs_unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise NativeSchemaError("duplicate JSON key in generated output")
        output[key] = value
    return output


def _refuse_constant(_: str) -> None:
    raise NativeSchemaError("nonfinite JSON number is forbidden")


def _walk_no_surrogates(item: Any, *, depth: int = 0) -> None:
    if depth > 40:
        raise NativeSchemaError("structured response nesting exceeds bound")
    if isinstance(item, str):
        if any(0xD800 <= ord(ch) <= 0xDFFF for ch in item):
            raise NativeSchemaError("unpaired Unicode surrogate")
    elif isinstance(item, list):
        if len(item) > 2048:
            raise NativeSchemaError("structured response array exceeds limit")
        for value in item:
            _walk_no_surrogates(value, depth=depth + 1)
    elif isinstance(item, dict):
        if len(item) > 2048:
            raise NativeSchemaError("structured response object exceeds limit")
        for key, value in item.items():
            _walk_no_surrogates(key, depth=depth + 1)
            _walk_no_surrogates(value, depth=depth + 1)
    elif isinstance(item, float) and not math.isfinite(item):
        raise NativeSchemaError("nonfinite generated number")


def _types(value: Any) -> frozenset[str]:
    if isinstance(value, str):
        types = (value,)
    elif isinstance(value, list) and value and all(isinstance(x, str) for x in value):
        types = value
    else:
        raise NativeSchemaError("invalid supported JSON type declaration")
    result = frozenset(types)
    if not result <= _TYPES:
        raise NativeSchemaError("unsupported JSON type")
    return result


def _matches_type(value: Any, type_name: str) -> bool:
    return {
        "object": lambda: type(value) is dict,
        "array": lambda: type(value) is list,
        "string": lambda: type(value) is str,
        "number": lambda: type(value) in (int, float) and math.isfinite(value),
        "integer": lambda: type(value) is int,
        "boolean": lambda: type(value) is bool,
        "null": lambda: value is None,
    }[type_name]()


def _validate_schema(schema: Mapping[str, Any], *, depth: int = 0) -> None:
    if type(schema) is not dict or depth > 20:
        raise NativeSchemaError("schema depth or type invalid")
    if not set(schema) <= _SCHEMA_KEYS:
        raise NativeSchemaError("unsupported schema keyword")
    if "type" in schema:
        _types(schema["type"])
    if "properties" in schema:
        props = schema["properties"]
        if type(props) is not dict or len(props) > 256:
            raise NativeSchemaError("invalid schema properties")
        for key, child in props.items():
            if type(key) is not str or not key or len(key) > 128:
                raise NativeSchemaError("invalid property name")
            _validate_schema(child, depth=depth + 1)
    if "items" in schema:
        _validate_schema(schema["items"], depth=depth + 1)
    if "required" in schema:
        required = schema["required"]
        if type(required) is not list or len(required) > 256:
            raise NativeSchemaError("invalid required properties")
        if any(type(name) is not str for name in required) or len(required) != len(set(required)):
            raise NativeSchemaError("duplicate or invalid required property")
    if "additionalProperties" in schema:
        if type(schema["additionalProperties"]) is not bool:
            raise NativeSchemaError("additionalProperties must be boolean")
    if "enum" in schema:
        if type(schema["enum"]) is not list or not 1 <= len(schema["enum"]) <= 256:
            raise NativeSchemaError("invalid schema enum")
    for key in ("minItems", "maxItems", "minLength", "maxLength"):
        if key in schema and (type(schema[key]) is not int or not 0 <= schema[key] <= 100_000):
            raise NativeSchemaError("invalid schema length limit")
    for key in ("minimum", "maximum"):
        if key in schema and (type(schema[key]) not in (int, float) or not math.isfinite(schema[key])):
            raise NativeSchemaError("invalid schema numeric limit")


def _assert_shape(value: Any, schema: Mapping[str, Any], *, depth: int = 0) -> None:
    if depth > 20:
        raise NativeSchemaError("model output exceeds schema nesting")
    types = _types(schema["type"]) if "type" in schema else _TYPES
    if not any(_matches_type(value, name) for name in types):
        raise NativeSchemaError("model output violates required JSON type")
    if "enum" in schema and value not in schema["enum"]:
        raise NativeSchemaError("model output not in permitted enum")
    if type(value) is dict:
        required = schema.get("required", [])
        if not all(key in value for key in required):
            raise NativeSchemaError("model output lacks required property")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False and not set(value) <= set(props):
            raise NativeSchemaError("model output has forbidden property")
        for key, child in props.items():
            if key in value:
                _assert_shape(value[key], child, depth=depth + 1)
    if type(value) is list:
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 2048):
            raise NativeSchemaError("model array violates item count")
        if "items" in schema:
            for item in value:
                _assert_shape(item, schema["items"], depth=depth + 1)
    if type(value) is str:
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 262144):
            raise NativeSchemaError("model string violates length")
    if type(value) in (int, float):
        if value < schema.get("minimum", float("-inf")) or value > schema.get("maximum", float("inf")):
            raise NativeSchemaError("model number violates range")


def verify_structured_native_output(
    text: str,
    schema: Mapping[str, Any] | None,
    *,
    maximum_bytes: int = 262144,
) -> str:
    """Validate an entire raw generation; no regex repair, truncation or retry."""
    if type(text) is not str:
        raise NativeSchemaError("model output must be text")
    try:
        raw = text.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise NativeSchemaError("model output is not UTF-8") from exc
    if not raw or len(raw) > maximum_bytes:
        raise NativeSchemaError("model output exceeds byte bounds or is empty")
    if schema is None:
        _walk_no_surrogates(text)
        return text
    try:
        encoded_schema = json.dumps(schema, allow_nan=False, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise NativeSchemaError("invalid declared schema") from exc
    if len(encoded_schema) > 8192:
        raise NativeSchemaError("schema exceeds validation budget")
    _validate_schema(dict(schema))
    try:
        value = json.loads(
            text, object_pairs_hook=_pairs_unique, parse_constant=_refuse_constant,
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise NativeSchemaError("native response is not strict JSON") from exc
    _walk_no_surrogates(value)
    _assert_shape(value, schema)
    return text


__all__ = ["NativeSchemaError", "verify_structured_native_output"]
