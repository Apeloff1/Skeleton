"""Catalog recipes as cards. No coin. No uuid."""

from __future__ import annotations

from typing import Any, Mapping


MAX_RECIPES = 32
MAX_IO = 8


class CatalogError(ValueError):
    """Catalog contract violation."""


def _token(name: str) -> str:
    text = str(name or "").strip()
    if not text or len(text) > 64:
        raise CatalogError("recipe token invalid")
    if text.lower() in {"coin", "token"}:
        raise CatalogError("coin is forbidden")
    return text


def validate_recipe(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise CatalogError("recipe must be an object")
    recipe_id = _token(str(raw.get("id", "")))
    inputs = raw.get("inputs")
    outputs = raw.get("outputs")
    if not isinstance(inputs, Mapping) or not isinstance(outputs, Mapping):
        raise CatalogError("inputs and outputs must be objects")
    if not inputs or not outputs:
        raise CatalogError("recipe needs inputs and outputs")
    if len(inputs) > MAX_IO or len(outputs) > MAX_IO:
        raise CatalogError("recipe io exceeds cap")
    clean_in = {_token(k): int(v) for k, v in inputs.items()}
    clean_out = {_token(k): int(v) for k, v in outputs.items()}
    if any(v < 1 for v in list(clean_in.values()) + list(clean_out.values())):
        raise CatalogError("recipe quantities must be >= 1")
    return {
        "id": recipe_id,
        "inputs": dict(sorted(clean_in.items())),
        "outputs": dict(sorted(clean_out.items())),
        "stored_prose": 0,
    }


def catalog(recipes: list[Mapping[str, Any]] | None) -> dict[str, Any]:
    rows = [validate_recipe(item) for item in (recipes or [])]
    if len(rows) > MAX_RECIPES:
        raise CatalogError("too many recipes")
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise CatalogError("recipe ids must be unique")
    return {"kind": "catalog", "n": len(rows), "recipes": rows, "stored_prose": 0}
