"""Transactional equipment recipe and stage-drop authoring with combat preview.

All changes apply to a private source copy. A completed batch is validated
and planned through the canonical forge runtime; no partial edit is published.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.arena_forge_run import (
    normalize_forge, original_forge,
)
from skeleton.game.gameplay.arena_forge_solver import plan_forge
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.arena_forge_author.v1"
MAX_EDITS = 32
MAX_BYTES = 2 * 1024 * 1024


def _recipe(source: dict[str, Any], key: Any) -> dict[str, Any]:
    recipe_id = _id(key, "recipe id")
    for recipe in source["recipes"]:
        if recipe["id"] == recipe_id:
            return recipe
    raise CombatSessionError("forge recipe not found")


def _stage(source: dict[str, Any], key: Any) -> dict[str, Any]:
    arena_id = _id(key, "arena id")
    for stage in source["stages"]:
        if stage["arena"]["arena_id"] == arena_id:
            return stage
    raise CombatSessionError("forge stage not found")


def _apply(source: dict[str, Any], raw: Any) -> None:
    if type(raw) is not dict or type(raw.get("kind")) is not str:
        raise CombatSessionError("invalid forge edit")
    kind = raw["kind"]
    if kind == "add_recipe":
        _object(raw, {"kind", "recipe"}, "add recipe")
        recipe = raw["recipe"]
        _object(recipe, {"id", "costs", "attack_bonus",
                         "defense_bonus", "durability"}, "recipe")
        if any(x["id"] == recipe["id"] for x in source["recipes"]):
            raise CombatSessionError("duplicate forge recipe")
        source["recipes"].append(deepcopy(recipe))
    elif kind == "remove_recipe":
        _object(raw, {"kind", "recipe_id"}, "remove recipe")
        source["recipes"].remove(_recipe(source, raw["recipe_id"]))
    elif kind == "set_recipe":
        _object(raw, {"kind", "recipe_id", "attack_bonus",
                      "defense_bonus", "durability"}, "set recipe")
        recipe = _recipe(source, raw["recipe_id"])
        recipe["attack_bonus"] = _integer(raw["attack_bonus"], "attack bonus", 0, 100)
        recipe["defense_bonus"] = _integer(raw["defense_bonus"], "defense bonus", 0, 100)
        recipe["durability"] = _integer(raw["durability"], "durability", 1, 6)
    elif kind == "set_costs":
        _object(raw, {"kind", "recipe_id", "costs"}, "set costs")
        _recipe(source, raw["recipe_id"])["costs"] = deepcopy(raw["costs"])
    elif kind == "set_drops":
        _object(raw, {"kind", "arena_id", "drops"}, "set drops")
        _stage(source, raw["arena_id"])["drops"] = deepcopy(raw["drops"])
    elif kind == "set_arena":
        _object(raw, {"kind", "arena_id", "arena"}, "set arena")
        stage = _stage(source, raw["arena_id"])
        stage["arena"] = deepcopy(raw["arena"])
    else:
        raise CombatSessionError("unsupported forge edit")


def author_forge(source: Any, edits: Any, *,
                 max_states: int = 128, max_depth: int = 16) -> dict[str, Any]:
    before = normalize_forge(source)
    if type(edits) is not list or len(edits) > MAX_EDITS:
        raise CombatSessionError("invalid forge edit batch")
    draft = deepcopy(before)
    for edit in edits:
        _apply(draft, edit)
    after = normalize_forge(draft)
    preview = plan_forge(after, max_states=max_states, max_depth=max_depth)
    report = {"schema_version": SCHEMA, "before_source": before,
              "before_digest": dig(before), "edits": deepcopy(edits),
              "source": after, "source_digest": dig(after),
              "preview": preview, "max_states": max_states,
              "max_depth": max_depth}
    report["receipt"] = dig(report)
    if len(json.dumps(report, sort_keys=True, allow_nan=False).encode()) > MAX_BYTES:
        raise CombatSessionError("forge author report budget exceeded")
    return report


def verify_author_report(payload: Any) -> dict[str, Any]:
    obj = _object(payload, {"schema_version", "before_source", "before_digest",
                            "edits", "source", "source_digest", "preview",
                            "max_states", "max_depth", "receipt"},
                  "forge author report")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported forge author report")
    expected = author_forge(
        obj["before_source"], obj["edits"],
        max_states=obj["max_states"], max_depth=obj["max_depth"],
    )
    if expected != obj:
        raise CombatSessionError("forge author report replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-forge-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    patch = sub.add_parser("patch")
    patch.add_argument("--source-json", required=True)
    patch.add_argument("--edits-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        read = lambda name: _parse_json(
            getattr(args, name.replace("-", "_")), name,
        )
        if args.command == "demo":
            result = author_forge(original_forge(), [{
                "kind": "set_recipe", "recipe_id": "tide_edge",
                "attack_bonus": 6, "defense_bonus": 1, "durability": 2,
            }])
        elif args.command == "patch":
            result = author_forge(read("source-json"), read("edits-json"))
        else:
            result = verify_author_report(read("report-json"))
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
