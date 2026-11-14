"""The JSON shape a model may propose, and a strict parser for it."""
from __future__ import annotations

import json
from typing import Any

from skeleton.forge.game_design_spec import GAMEPLAY_ENUMS

PLAN_SCHEMA = "skeleton.forge.ai_builder.plan_proposal.v1"
# Fields the model may refine. Everything else is the compiler's.
MUTABLE_FIELDS = ("title", "fantasy", "core_loop", "systems", "gameplay")
FIELD_LIMITS = {"title": 80, "fantasy": 180, "core_loop": 180}
MAX_PROPOSAL_BYTES = 32 * 1024
GAMEPLAY_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "required": ["difficulty", "theme", "objective_label", "player_speed", "encounter_style"],
    "properties": {
        **{key: {"type": "string", "enum": list(values)} for key, values in GAMEPLAY_ENUMS.items()},
        "objective_label": {"type": "string", "minLength": 1, "maxLength": 100},
        "player_speed": {"type": "integer", "minimum": 120, "maximum": 360},
    },
}

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema": {"const": PLAN_SCHEMA},
        "title": {"type": "string", "maxLength": FIELD_LIMITS["title"]},
        "fantasy": {"type": "string", "maxLength": FIELD_LIMITS["fantasy"]},
        "core_loop": {"type": "string", "maxLength": FIELD_LIMITS["core_loop"]},
        "systems": {"type": "array", "items": {"type": "string"}},
        "gameplay": GAMEPLAY_RESPONSE_SCHEMA,
    },
}


class PlanParseError(ValueError):
    """Model output is not a usable plan proposal."""


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PlanParseError("duplicate proposal field")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise PlanParseError("nonfinite proposal value")


def parse_model_plan(raw: object) -> dict[str, Any]:
    """Accept a mapping or JSON text (optionally ```-fenced); return a proposal."""
    if isinstance(raw, str):
        try:
            if len(raw.encode("utf-8", errors="strict")) > MAX_PROPOSAL_BYTES:
                raise PlanParseError("proposal exceeds byte budget")
        except UnicodeError:
            raise PlanParseError("invalid proposal encoding") from None
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):] if "{" in text else text
        try:
            raw = json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=_reject_nonfinite)
        except (json.JSONDecodeError, RecursionError) as exc:
            if isinstance(exc, RecursionError):
                raise PlanParseError("proposal nesting exceeds parser limit") from None
            raise PlanParseError(f"not json: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise PlanParseError("proposal must be an object")
    if raw.get("schema", PLAN_SCHEMA) != PLAN_SCHEMA:
        raise PlanParseError("wrong proposal schema")
    try:
        if len(json.dumps(raw, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_PROPOSAL_BYTES:
            raise PlanParseError("proposal exceeds byte budget")
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise PlanParseError("proposal must contain bounded finite JSON data") from None
    return {k: v for k, v in raw.items() if k != "schema"}
