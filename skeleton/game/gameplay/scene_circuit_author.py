"""Atomic source editor for playable scene circuits with verified preview.

No partial edit is published. Every source edit is revalidated against
canonical scene topology and bounded circuit switch/gate constraints.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_circuit import (
    normalize_circuit, original_circuit,
)
from skeleton.game.gameplay.scene_circuit_solver import plan_circuit
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _id, _json, _object,
)

SCHEMA = "skeleton.scene_circuit_author.v1"
MAX_EDITS = 32
MAX_BYTES = 2 * 1024 * 1024


def _switch(source: dict[str, Any], key: Any) -> dict[str, Any]:
    name = _id(key, "switch id")
    for switch in source["switches"]:
        if switch["id"] == name:
            return switch
    raise SceneTravelError("circuit switch not found")


def _gate(source: dict[str, Any], scene: Any, exit_id: Any) -> dict[str, Any]:
    scene_id = _id(scene, "scene id")
    edge = _id(exit_id, "exit id")
    for gate in source["gates"]:
        if gate["scene_id"] == scene_id and gate["exit_id"] == edge:
            return gate
    raise SceneTravelError("circuit gate not found")


def _apply(source: dict[str, Any], raw: Any) -> None:
    if type(raw) is not dict or type(raw.get("kind")) is not str:
        raise SceneTravelError("invalid circuit edit")
    kind = raw["kind"]
    if kind == "add_switch":
        _object(raw, {"kind", "switch"}, "add switch")
        switch = raw["switch"]
        _object(switch, {"id", "scene_id", "initial_on"}, "switch")
        if any(s["id"] == switch["id"] for s in source["switches"]):
            raise SceneTravelError("duplicate circuit switch")
        source["switches"].append(deepcopy(switch))
    elif kind == "remove_switch":
        _object(raw, {"kind", "switch_id"}, "remove switch")
        switch = _switch(source, raw["switch_id"])
        if any(switch["id"] in gate["requires_on"] + gate["requires_off"]
               for gate in source["gates"]):
            raise SceneTravelError("cannot remove referenced circuit switch")
        source["switches"].remove(switch)
    elif kind == "set_initial":
        _object(raw, {"kind", "switch_id", "initial_on"}, "set initial")
        if type(raw["initial_on"]) is not bool:
            raise SceneTravelError("initial switch state must be boolean")
        _switch(source, raw["switch_id"])["initial_on"] = raw["initial_on"]
    elif kind == "add_gate":
        _object(raw, {"kind", "gate"}, "add gate")
        gate = raw["gate"]
        _object(gate, {"scene_id", "exit_id", "requires_on",
                       "requires_off"}, "gate")
        if any(g["scene_id"] == gate["scene_id"]
               and g["exit_id"] == gate["exit_id"] for g in source["gates"]):
            raise SceneTravelError("duplicate circuit gate")
        source["gates"].append(deepcopy(gate))
    elif kind == "remove_gate":
        _object(raw, {"kind", "scene_id", "exit_id"}, "remove gate")
        source["gates"].remove(_gate(source, raw["scene_id"], raw["exit_id"]))
    elif kind == "set_gate":
        _object(raw, {"kind", "scene_id", "exit_id",
                      "requires_on", "requires_off"}, "set gate")
        gate = _gate(source, raw["scene_id"], raw["exit_id"])
        gate["requires_on"] = deepcopy(raw["requires_on"])
        gate["requires_off"] = deepcopy(raw["requires_off"])
    else:
        raise SceneTravelError("unsupported circuit edit")


def author_circuit(source: Any, edits: Any, *,
                   max_states: int = 1024, max_depth: int = 64) -> dict[str, Any]:
    before = normalize_circuit(source)
    if type(edits) is not list or len(edits) > MAX_EDITS:
        raise SceneTravelError("invalid circuit edit batch")
    draft = deepcopy(before)
    for edit in edits:
        _apply(draft, edit)
    after = normalize_circuit(draft)
    preview = plan_circuit(after, max_states=max_states, max_depth=max_depth)
    result = {"schema_version": SCHEMA, "before_source": before,
              "before_digest": dig(before), "edits": deepcopy(edits),
              "source": after, "source_digest": dig(after),
              "preview": preview, "max_states": max_states,
              "max_depth": max_depth}
    result["receipt"] = dig(result)
    if len(json.dumps(result, sort_keys=True, allow_nan=False).encode()) > MAX_BYTES:
        raise SceneTravelError("circuit authoring report budget exceeded")
    return result


def verify_author_report(payload: Any) -> dict[str, Any]:
    obj = _object(payload, {"schema_version", "before_source", "before_digest",
                            "edits", "source", "source_digest", "preview",
                            "max_states", "max_depth", "receipt"},
                  "circuit author report")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported circuit author report")
    expected = author_circuit(
        obj["before_source"], obj["edits"],
        max_states=obj["max_states"], max_depth=obj["max_depth"],
    )
    if expected != obj:
        raise SceneTravelError("circuit author report replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-circuit-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    patch = sub.add_parser("patch")
    patch.add_argument("--source-json", required=True)
    patch.add_argument("--edits-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        read = lambda name: _json(getattr(args, name.replace("-", "_")), name,
                                  max_bytes=MAX_BYTES)
        if args.command == "demo":
            source, _ = original_circuit()
            result = author_circuit(source, [{
                "kind": "set_initial", "switch_id": "quay_lantern",
                "initial_on": True,
            }])
        elif args.command == "patch":
            result = author_circuit(read("source-json"), read("edits-json"))
        else:
            result = verify_author_report(read("report-json"))
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (SceneTravelError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
