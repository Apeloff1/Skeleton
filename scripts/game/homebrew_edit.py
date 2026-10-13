"""Homebrew-only game editor recipe CLI: inspect, apply, analyze, export.

A 32-command atomic batch uses a source SHA lock. A failed command does not
partially mutate or overwrite project data. Every successful output is a
new verified capsule, never an imported commercial game or ROM.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from scripts.game.game_project import _read_json, _write_new
from skeleton.ai.runtime.homebrew_editor import (
    HomebrewEditor, HomebrewEditorError, MAX_BATCH, MAX_COMMANDS,
)

SCHEMA = "skeleton.game.homebrew_editor_recipe.v1"


def execute_recipe(
    capsule: dict[str, Any], request: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(request, dict) or set(request) != {
        "schema_version", "base_tile_sha256", "batches", "analysis_targets",
        "require_final_controller_win",
    } or request["schema_version"] != SCHEMA:
        raise HomebrewEditorError("editor recipe must have exact v1 schema")
    editor = HomebrewEditor(capsule)
    if request["base_tile_sha256"] != editor.tile_sha256:
        raise HomebrewEditorError("editor recipe source SHA has changed")
    batches = request["batches"]
    if (not isinstance(batches, list) or len(batches) > MAX_COMMANDS
            or sum(len(batch.get("commands", [])) if isinstance(batch, dict) and
                       isinstance(batch.get("commands"), list) else MAX_COMMANDS + 1
                       for batch in batches) > MAX_COMMANDS):
        raise HomebrewEditorError("editor operation budget exceeded")
    if type(request["require_final_controller_win"]) is not bool:
        raise HomebrewEditorError("controller-win requirement must be boolean")
    analysis_targets = request["analysis_targets"]
    if (not isinstance(analysis_targets, list) or not 1 <= len(analysis_targets) <= 16
            or any(not isinstance(x, str) for x in analysis_targets)
            or len(set(analysis_targets)) != len(analysis_targets)):
        raise HomebrewEditorError("editor target selection is invalid")
    for batch in batches:
        if (
            not isinstance(batch, dict)
            or set(batch) != {"commands", "require_grid_route", "require_controller_win"}
            or type(batch["require_grid_route"]) is not bool
            or type(batch["require_controller_win"]) is not bool
            or not 1 <= len(batch["commands"]) <= MAX_BATCH
        ):
            raise HomebrewEditorError("editor operation batches have invalid shape")
        editor.apply(
            batch["commands"], expected_tile_sha256=editor.tile_sha256,
            require_grid_route=batch["require_grid_route"],
            require_controller_win=batch["require_controller_win"],
        )
    analysis = editor.analyze(target_ids=analysis_targets)
    if request["require_final_controller_win"] and analysis["controller_status"] != "playable":
        raise HomebrewEditorError("recipe final level failed real-controller proof")
    product = editor.export_capsule()
    return product, {
        "schema_version": "skeleton.game.homebrew_editor_result.v1",
        "source_capsule_sha256": capsule["capsule_sha256"],
        "new_capsule_sha256": product["capsule_sha256"],
        "edited_tile_sha256": product["edited_tile_sha256"],
        "batches_executed": len(batches),
        "commands_executed": editor.command_count,
        "modified_cells": len(product["modifications"]),
        "audit_sha256": editor.audit_sha256,
        "analysis": analysis,
        "homebrew_only": True,
        "asset_ownership_independently_verified": False,
        "third_party_rom_exported": False,
        "training_examples_added": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Purely original offline game editor: fail-closed, immutable, model-free.",
    )
    parser.add_argument("--capsule", type=Path, required=True)
    kind = parser.add_mutually_exclusive_group(required=True)
    kind.add_argument("--tools", action="store_true", help="list bounded tool options")
    kind.add_argument("--analyze", action="store_true", help="analyze a verified original level")
    kind.add_argument("--recipe", type=Path, help="apply editor recipe and write new capsule")
    parser.add_argument("--output", type=Path, help="new project path for editor recipe")
    parser.add_argument("--targets", default="chip8-vip,windows-11",
                        help="comma-delimited design targets for --analyze")
    args = parser.parse_args(argv)
    if bool(args.output) != bool(args.recipe):
        parser.error("--output and --recipe are required together")
    try:
        editor = HomebrewEditor(_read_json(args.capsule))
        if args.tools:
            report = editor.capabilities()
        elif args.analyze:
            report = editor.analyze(target_ids=args.targets.split(","))
        else:
            product, report = execute_recipe(
                editor.source, _read_json(args.recipe),
            )
            output = _write_new(args.output, product)
            report["output_path"] = output
        print(json.dumps(report, sort_keys=True, ensure_ascii=True))
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(
            "homebrew editor rejected: " + type(exc).__name__ + ": " + str(exc),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
