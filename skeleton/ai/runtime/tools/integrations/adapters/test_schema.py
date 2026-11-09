"""Tests for the JSON-Schema subset validator."""

from __future__ import annotations

import pytest

from .errors import SchemaValidationError
from .schema import apply_defaults, check_schema, is_valid, validate

OBJ = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1, "maxLength": 5, "pattern": "^[a-z]+$"},
        "count": {"type": "integer", "minimum": 0, "maximum": 10, "default": 1},
        "ratio": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1},
        "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3, "uniqueItems": True},
        "mode": {"enum": ["fast", "safe"]},
        "nested": {"type": "object", "properties": {"flag": {"type": "boolean", "default": False}}},
    },
    "required": ["name"],
    "additionalProperties": False,
}


def test_valid_document():
    validate({"name": "abc", "count": 3, "ratio": 0.5, "tags": ["x", "y"], "mode": "fast"}, OBJ)


@pytest.mark.parametrize(
    "doc,fragment",
    [
        ({}, "missing required property 'name'"),
        ({"name": ""}, "shorter than"),
        ({"name": "abcdef"}, "longer than"),
        ({"name": "ABC"}, "does not match pattern"),
        ({"name": "a", "count": -1}, "below minimum"),
        ({"name": "a", "count": 11}, "above maximum"),
        ({"name": "a", "count": 1.5}, "expected integer"),
        ({"name": "a", "count": True}, "expected integer"),
        ({"name": "a", "ratio": 0}, "must be > 0"),
        ({"name": "a", "ratio": 1}, "must be < 1"),
        ({"name": "a", "tags": []}, "fewer than 1 items"),
        ({"name": "a", "tags": ["a", "b", "c", "d"]}, "more than 3 items"),
        ({"name": "a", "tags": ["a", "a"]}, "items must be unique"),
        ({"name": "a", "tags": [1]}, "$.tags[0]: expected string"),
        ({"name": "a", "mode": "slow"}, "must be one of"),
        ({"name": "a", "extra": 1}, "unexpected property 'extra'"),
        ({"name": "a", "nested": {"flag": "yes"}}, "$.nested.flag"),
    ],
)
def test_invalid_documents(doc, fragment):
    with pytest.raises(SchemaValidationError) as info:
        validate(doc, OBJ)
    assert fragment in info.value.message


def test_integer_accepts_integral_float_and_number_rejects_bool():
    assert is_valid(2.0, {"type": "integer"})
    assert not is_valid(True, {"type": "number"})
    assert is_valid(None, {"type": ["string", "null"]})


def test_boolean_schemas_and_empty():
    assert is_valid(123, True)
    assert is_valid(123, {})
    assert not is_valid(123, False)


def test_combinators():
    assert is_valid(5, {"anyOf": [{"type": "string"}, {"type": "integer"}]})
    assert not is_valid(5.5, {"anyOf": [{"type": "string"}, {"type": "integer"}]})
    assert not is_valid(5, {"oneOf": [{"type": "integer"}, {"type": "number"}]})
    assert is_valid("x", {"oneOf": [{"type": "integer"}, {"type": "string"}]})
    assert not is_valid(3, {"allOf": [{"type": "integer"}, {"minimum": 5}]})
    assert not is_valid("x", {"not": {"type": "string"}})
    assert is_valid({"a": 1}, {"type": "object", "additionalProperties": {"type": "integer"}})
    assert not is_valid({"a": "1"}, {"type": "object", "additionalProperties": {"type": "integer"}})


def test_const_multiple_of_and_property_counts():
    assert is_valid("v1", {"const": "v1"})
    assert not is_valid("v2", {"const": "v1"})
    assert is_valid(0.3, {"multipleOf": 0.1})
    assert not is_valid(7, {"multipleOf": 2})
    with pytest.raises(SchemaValidationError):
        validate(1, {"multipleOf": 0})
    assert not is_valid({}, {"minProperties": 1})
    assert not is_valid({"a": 1, "b": 2}, {"maxProperties": 1})


def test_depth_limit_protects_against_deep_payloads():
    schema: dict = {"type": "array", "items": {}}
    inner = schema
    for _ in range(80):
        nxt: dict = {"type": "array", "items": {}}
        inner["items"] = nxt
        inner = nxt
    doc: list = []
    cursor = doc
    for _ in range(80):
        new: list = []
        cursor.append(new)
        cursor = new
    with pytest.raises(SchemaValidationError, match="depth"):
        validate(doc, schema)


def test_apply_defaults_is_non_mutating_and_recursive():
    doc = {"name": "a", "nested": {}}
    filled = apply_defaults(doc, OBJ)
    assert filled["count"] == 1 and filled["nested"] == {"flag": False}
    assert doc == {"name": "a", "nested": {}}
    assert apply_defaults([{}], {"type": "array", "items": {"properties": {"x": {"default": 1}}}}) == [{"x": 1}]
    assert apply_defaults(5, OBJ) == 5


def test_check_schema_catches_structural_errors():
    check_schema(OBJ)
    with pytest.raises(SchemaValidationError):
        check_schema({"type": "strnig"})
    with pytest.raises(SchemaValidationError):
        check_schema({"pattern": "("})
    with pytest.raises(SchemaValidationError):
        check_schema({"required": [1]})
    with pytest.raises(SchemaValidationError):
        check_schema({"properties": {"a": 5}})
    with pytest.raises(SchemaValidationError):
        check_schema(["not", "a", "schema"])
    with pytest.raises(SchemaValidationError):
        check_schema({"anyOf": [{"type": "bogus"}]})


def test_unknown_type_in_validate_is_error():
    with pytest.raises(SchemaValidationError):
        validate(1, {"type": "decimal"})
