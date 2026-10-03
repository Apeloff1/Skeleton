"""Minimal, dependency-free JSON-Schema subset validator for tool arguments.

Supported keywords: ``type`` (incl. lists), ``enum``, ``const``,
``properties``, ``required``, ``additionalProperties`` (bool or schema),
``items``, ``minItems``, ``maxItems``, ``uniqueItems``, ``minLength``,
``maxLength``, ``pattern``, ``minimum``, ``maximum``, ``exclusiveMinimum``,
``exclusiveMaximum``, ``multipleOf``, ``anyOf``, ``oneOf``, ``allOf``,
``not`` and ``default`` (applied by :func:`apply_defaults`).  Unknown
keywords are ignored, matching JSON-Schema semantics.  Depth is bounded so
hostile schemas or payloads cannot exhaust the stack.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from .errors import SchemaValidationError

__all__ = ["validate", "is_valid", "apply_defaults", "check_schema"]

_MAX_DEPTH = 64
_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list, tuple),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}
_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _type_matches(value: Any, name: str) -> bool:
    if name not in _TYPES:
        raise SchemaValidationError(f"unknown schema type {name!r}")
    if name in ("integer", "number") and isinstance(value, bool):
        return False
    if name == "integer" and isinstance(value, float):
        return value.is_integer()
    return isinstance(value, _TYPES[name])


def _pattern(expr: str) -> re.Pattern[str]:
    compiled = _PATTERN_CACHE.get(expr)
    if compiled is None:
        if len(expr) > 512:
            raise SchemaValidationError("schema pattern too long")
        compiled = re.compile(expr)
        if len(_PATTERN_CACHE) < 256:
            _PATTERN_CACHE[expr] = compiled
    return compiled


def _fail(path: str, message: str) -> SchemaValidationError:
    return SchemaValidationError(f"{path}: {message}", path=path)


def validate(value: Any, schema: Mapping[str, Any] | bool, path: str = "$", _depth: int = 0) -> None:
    """Raise :class:`SchemaValidationError` if ``value`` violates ``schema``."""

    if _depth > _MAX_DEPTH:
        raise _fail(path, "maximum nesting depth exceeded")
    if schema is True or schema == {}:
        return
    if schema is False:
        raise _fail(path, "no value is allowed here")
    if not isinstance(schema, Mapping):
        raise _fail(path, "schema must be an object or boolean")

    expected = schema.get("type")
    if expected is not None:
        names = [expected] if isinstance(expected, str) else list(expected)
        if not any(_type_matches(value, n) for n in names):
            raise _fail(path, f"expected {'/'.join(names)}, got {type(value).__name__}")

    if "const" in schema and value != schema["const"]:
        raise _fail(path, f"must equal {schema['const']!r}")
    if "enum" in schema and value not in list(schema["enum"]):
        raise _fail(path, f"must be one of {list(schema['enum'])!r}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise _fail(path, f"shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise _fail(path, f"longer than {schema['maxLength']}")
        if "pattern" in schema and not _pattern(str(schema["pattern"])).search(value):
            raise _fail(path, f"does not match pattern {schema['pattern']!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise _fail(path, f"below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise _fail(path, f"above maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise _fail(path, f"must be > {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            raise _fail(path, f"must be < {schema['exclusiveMaximum']}")
        if "multipleOf" in schema:
            step = schema["multipleOf"]
            if step <= 0:
                raise _fail(path, "multipleOf must be positive")
            quotient = value / step
            if abs(quotient - round(quotient)) > 1e-9:
                raise _fail(path, f"not a multiple of {step}")

    if isinstance(value, dict):
        props: Mapping[str, Any] = schema.get("properties", {}) or {}
        for key in schema.get("required", ()) or ():
            if key not in value:
                raise _fail(path, f"missing required property {key!r}")
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if not isinstance(key, str):
                raise _fail(path, "object keys must be strings")
            child = f"{path}.{key}"
            if key in props:
                validate(item, props[key], child, _depth + 1)
            elif additional is False:
                raise _fail(path, f"unexpected property {key!r}")
            elif isinstance(additional, Mapping):
                validate(item, additional, child, _depth + 1)
        if "minProperties" in schema and len(value) < int(schema["minProperties"]):
            raise _fail(path, f"fewer than {schema['minProperties']} properties")
        if "maxProperties" in schema and len(value) > int(schema["maxProperties"]):
            raise _fail(path, f"more than {schema['maxProperties']} properties")

    if isinstance(value, (list, tuple)):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise _fail(path, f"fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise _fail(path, f"more than {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            seen: list[Any] = []
            for item in value:
                if item in seen:
                    raise _fail(path, "items must be unique")
                seen.append(item)
        items = schema.get("items")
        if isinstance(items, (Mapping, bool)):
            for idx, item in enumerate(value):
                validate(item, items, f"{path}[{idx}]", _depth + 1)

    for sub in schema.get("allOf", ()) or ():
        validate(value, sub, path, _depth + 1)
    if "anyOf" in schema:
        if not any(is_valid(value, sub, _depth + 1) for sub in schema["anyOf"]):
            raise _fail(path, "does not match any allowed schema")
    if "oneOf" in schema:
        matches = sum(1 for sub in schema["oneOf"] if is_valid(value, sub, _depth + 1))
        if matches != 1:
            raise _fail(path, f"must match exactly one schema (matched {matches})")
    if "not" in schema and is_valid(value, schema["not"], _depth + 1):
        raise _fail(path, "matches a forbidden schema")


def is_valid(value: Any, schema: Mapping[str, Any] | bool, _depth: int = 0) -> bool:
    try:
        validate(value, schema, "$", _depth)
    except SchemaValidationError:
        return False
    return True


def apply_defaults(value: Any, schema: Mapping[str, Any] | bool, _depth: int = 0) -> Any:
    """Return a copy of ``value`` with ``default`` filled for absent properties."""

    if _depth > _MAX_DEPTH or not isinstance(schema, Mapping):
        return value
    if isinstance(value, dict):
        result = dict(value)
        for key, sub in (schema.get("properties") or {}).items():
            if key not in result and isinstance(sub, Mapping) and "default" in sub:
                result[key] = copy.deepcopy(sub["default"])
            elif key in result:
                result[key] = apply_defaults(result[key], sub, _depth + 1)
        return result
    if isinstance(value, list) and isinstance(schema.get("items"), Mapping):
        return [apply_defaults(item, schema["items"], _depth + 1) for item in value]
    return value


def check_schema(schema: Any, _depth: int = 0, path: str = "$") -> None:
    """Structural sanity check of a schema (types known, patterns compile)."""

    if _depth > _MAX_DEPTH:
        raise _fail(path, "schema nesting too deep")
    if isinstance(schema, bool):
        return
    if not isinstance(schema, Mapping):
        raise _fail(path, "schema must be an object or boolean")
    expected = schema.get("type")
    if expected is not None:
        names = [expected] if isinstance(expected, str) else list(expected)
        for name in names:
            if name not in _TYPES:
                raise _fail(path, f"unknown type {name!r}")
    if "pattern" in schema:
        try:
            _pattern(str(schema["pattern"]))
        except re.error as exc:
            raise _fail(path, f"invalid pattern: {exc}") from exc
    if "required" in schema and not all(isinstance(k, str) for k in schema["required"]):
        raise _fail(path, "required must list strings")
    for key, sub in (schema.get("properties") or {}).items():
        check_schema(sub, _depth + 1, f"{path}.properties.{key}")
    for kw in ("items", "additionalProperties", "not"):
        if isinstance(schema.get(kw), Mapping):
            check_schema(schema[kw], _depth + 1, f"{path}.{kw}")
    for kw in ("allOf", "anyOf", "oneOf"):
        for idx, sub in enumerate(schema.get(kw, ()) or ()):
            check_schema(sub, _depth + 1, f"{path}.{kw}[{idx}]")
