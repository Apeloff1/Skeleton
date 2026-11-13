"""The JSON shape a model may propose, and a strict parser for it."""
from __future__ import annotations

import json
from typing import Any

PLAN_SCHEMA = "skeleton.forge.ai_builder.plan_proposal.v1"
# Fields the model may refine. Everything else is the compiler's.
MUTABLE_FIELDS = ("title", "fantasy", "core_loop", "systems")
FIELD_LIMITS = {"title": 80, "fantasy": 180, "core_loop": 180}

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema": {"const": PLAN_SCHEMA},
        "title": {"type": "string", "maxLength": FIELD_LIMITS["title"]},
        "fantasy": {"type": "string", "maxLength": FIELD_LIMITS["fantasy"]},
        "core_loop": {"type": "string", "maxLength": FIELD_LIMITS["core_loop"]},
        "systems": {"type": "array", "items": {"type": "string"}},
    },
}


class PlanParseError(ValueError):
    """Model output is not a usable plan proposal."""


def parse_model_plan(raw: object) -> dict[str, Any]:
    """Accept a mapping or JSON text (optionally ```-fenced); return a proposal."""
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):] if "{" in text else text
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PlanParseError(f"not json: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise PlanParseError("proposal must be an object")
    if raw.get("schema", PLAN_SCHEMA) != PLAN_SCHEMA:
        raise PlanParseError("wrong proposal schema")
    return {k: v for k, v in raw.items() if k != "schema"}
