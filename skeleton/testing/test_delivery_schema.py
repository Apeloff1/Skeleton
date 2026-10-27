"""Adversarial JSON output contract validation, with no silent schema features."""

import pytest

from skeleton.context.delivery_schema import (
    parse_and_validate_delivery_json, validate_delivery_schema,
)
from skeleton.context.sealed_sandwich import SealedContextError, SealedContextLimitError


SCHEMA = {"type": "object", "properties": {
    "ok": {"type": "boolean"},
    "items": {"type": "array", "items": {"type": "object", "properties": {
        "serial": {"type": "integer", "minimum": 1, "maximum": 2000},
        "note": {"type": "string", "maxLength": 128},
    }, "required": ["serial", "note"], "additionalProperties": False}},
}, "required": ["ok", "items"], "additionalProperties": False}


def test_valid_nested_schema_and_unicode():
    item = parse_and_validate_delivery_json(
        '{"ok":true,"items":[{"serial":1,"note":"🐉"}]}', SCHEMA,
    )
    assert item["items"][0]["note"] == "🐉"


@pytest.mark.parametrize("payload", [
    '{"ok":true,"items":[{"serial":0,"note":"hi"}]}',
    '{"ok":1,"items":[]}',
    '{"ok":true,"items":{},"extra":2}',
    '{"ok":true,"items":[{"serial":true,"note":"hi"}]}',
    '{"ok":true,"items":[{"serial":1,"note":"hi","extra":0}]}',
    '{"ok":true,"items":[{"serial":1,"note":5}]}',
    '{"ok":true,"items":[{"serial":1,"note":"hi"},{"serial":2001,"note":"hi"}]}',
])
def test_nested_type_and_limits_rejected(payload):
    with pytest.raises(SealedContextError):
        parse_and_validate_delivery_json(payload, SCHEMA)


@pytest.mark.parametrize("payload", [
    '{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}',
    '{"x":1e999}', '"\\ud800"',
])
def test_noncanonical_malformed_numeric_and_unicode_rejected(payload):
    with pytest.raises(SealedContextError):
        parse_and_validate_delivery_json(payload)


@pytest.mark.parametrize("schema", [
    {"type":"object", "$ref":"https://example.com/bypass"},
    {"type":"array", "items":{"$ref":"unsupported"}}, {"type":"integer", "format":"ipv4"},
    {"required":["x"]}, {"type":"object", "required":["missing"], "additionalProperties":False},
    {"type":"string", "minLength":10, "maxLength":2},
    {"type":"object", "properties":{"a":{"type":"unknown"}}},
    {"type":"number", "minimum": float("nan")},
])
def test_schema_unknown_or_inconsistent_constraints_rejected(schema):
    with pytest.raises(SealedContextError):
        validate_delivery_schema(schema)


def test_depth_budget_and_token_budget_reject():
    nested = "[]"
    for _ in range(20):
        nested = "[" + nested + "]"
    with pytest.raises(SealedContextLimitError):
        parse_and_validate_delivery_json(nested)
    with pytest.raises(SealedContextLimitError):
        parse_and_validate_delivery_json('"' + 'x'*270000 + '"')


def test_boolean_const_not_matched_by_integer_one():
    with pytest.raises(SealedContextError):
        parse_and_validate_delivery_json('1', {"type":"integer", "const":True})


def test_required_and_enum_enforced():
    with pytest.raises(SealedContextError):
        parse_and_validate_delivery_json('{}', {"type":"object", "properties": {
            "status": {"type":"string", "enum":["passed", "failed"]},
        }, "required":["status"]})
    with pytest.raises(SealedContextError):
        parse_and_validate_delivery_json('{"status":"unknown"}', {"type":"object", "properties": {
            "status": {"type":"string", "enum":["passed", "failed"]},
        }, "required":["status"]})
