"""Provider-neutral JSON-schema-like documents for model tool integration."""

from __future__ import annotations

import hashlib
import json


def action_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["action_id", "command", "args"],
        "properties": {
            "action_id": {"type": "string", "minLength": 1, "maxLength": 160},
            "command": {"type": "string", "minLength": 1, "maxLength": 128},
            "args": {
                "type": "array",
                "maxItems": 256,
                "items": {"type": "string"},
            },
            "cwd": {"type": ["string", "null"]},
            "environment_refs": {
                "type": "object",
                "maxProperties": 64,
                "additionalProperties": {"type": "string"},
            },
            "timeout_seconds": {
                "type": ["number", "null"],
                "exclusiveMinimum": 0,
            },
            "depends_on": {
                "type": "array",
                "maxItems": 256,
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "continue_on_failure": {"type": "boolean"},
            "purpose": {"type": "string", "maxLength": 1024},
        },
    }


def model_response_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["protocol_version", "request_id", "proposal"],
        "properties": {
            "protocol_version": {"const": 1},
            "request_id": {"type": "string", "minLength": 1, "maxLength": 160},
            "proposal": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "proposal_id",
                    "intent_id",
                    "actions",
                    "confidence",
                    "uncertainty",
                ],
                "properties": {
                    "proposal_id": {"type": "string", "minLength": 1, "maxLength": 160},
                    "intent_id": {"type": "string", "minLength": 1, "maxLength": 160},
                    "actions": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 256,
                        "items": action_schema(),
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "uncertainty": {"type": "number", "minimum": 0, "maximum": 1},
                    "assumptions": {
                        "type": "array",
                        "maxItems": 64,
                        "items": {"type": "string", "maxLength": 1024},
                    },
                    "rationale_summary": {"type": "string", "maxLength": 4096},
                    "model_id": {"type": "string", "maxLength": 256},
                    "protocol_version": {"const": 1},
                },
            },
            "warnings": {
                "type": "array",
                "maxItems": 64,
                "items": {"type": "string", "maxLength": 1024},
            },
            "metadata": {
                "type": "object",
                "maxProperties": 64,
                "additionalProperties": {"type": "string", "maxLength": 512},
            },
        },
    }


def schema_digest() -> str:
    raw = json.dumps(
        model_response_schema(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()
