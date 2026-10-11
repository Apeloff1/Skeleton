"""Offline deterministic system-editor command line, no implicit writes.

Examples:
  python -m skeleton.ai.game_builder.system_editor_cli list
  python -m skeleton.ai.game_builder.system_editor_cli template --editor racing
  python -m skeleton.ai.game_builder.system_editor_cli preview --editor platformer
  python -m skeleton.ai.game_builder.system_editor_cli assembly --root WORKSPACE --project my_game
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .system_editors import (
    catalog, editor_source, preview_editor, validate_editor_document,
    SystemEditorError,
)
from .system_editor_assembly import assemble_workspace_systems
from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .advanced_level_scenes import make_advanced_scene
from .advanced_puzzle_solver import solve_advanced_puzzle
from .advanced_godot_export import (
    render_advanced_godot_package, write_advanced_godot_package,
)
from .advanced_platformer_godot import render_platformer_godot_package
from .advanced_deck_godot import render_deck_godot_package
from .advanced_shooter_godot import render_shooter_godot_package
from .advanced_gameplay_save import (
    export_advanced_savegame, import_advanced_savegame, continue_advanced_savegame,
)
from .game_project_workspace import GameWorkspace, WorkspaceError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.system_editor_cli",
        description="Typed, offline, bounded original game mechanics authoring")
    commands = result.add_subparsers(dest="operation", required=True)
    commands.add_parser("list", help="Enumerate real system editor capabilities")
    for name in ("template", "validate", "preview", "play"):
        p = commands.add_parser(name)
        p.add_argument("--editor", required=name != "validate")
        p.add_argument("--settings", help="Path to a local UTF-8 JSON settings object")
        if name == "validate":
            p.add_argument("--document", required=True)
        if name in ("preview", "play"):
            p.add_argument("--actions", help="Path to a bounded JSON action array")
        if name == "play":
            p.add_argument("--seed", type=int, default=0)
            p.add_argument("--scene", help="Reviewed original scene JSON document")
    scene = commands.add_parser("scene-template", help="Generate a typed advanced original scene")
    scene.add_argument("--editor",required=True)
    scene.add_argument("--seed",type=int,default=0)
    scene.add_argument("--scene-id",default="scene_01")
    scene.add_argument("--settings")
    scene.add_argument("--layout",help="Optional JSON authored geometry and resource map")
    solve=commands.add_parser("solve-puzzle",help="Bounded original puzzle reachability proof")
    solve.add_argument("--scene",required=True)
    solve.add_argument("--settings")
    solve.add_argument("--max-states",type=int,default=12000)
    solve.add_argument("--max-depth",type=int,default=96)
    native=commands.add_parser("godot-export",help="Real offline native Godot 4 puzzle source, proof and export presets")
    native.add_argument("--session",required=True)
    native.add_argument("--settings")
    native.add_argument("--output",required=True,help="New local destination; existing paths never overwritten")
    native.add_argument("--trusted-local-operator",action="store_true")
    save = commands.add_parser("save",help="Save a verified advanced game receipt")
    save.add_argument("--session",required=True)
    save.add_argument("--settings")
    load = commands.add_parser("load-save",help="Verify and restore a portable game save")
    load.add_argument("--savegame",required=True)
    cont = commands.add_parser("continue-save",help="Continue a verified portable game")
    cont.add_argument("--savegame",required=True)
    cont.add_argument("--actions",required=True)
    verify = commands.add_parser("verify-play", help="Independently verify advanced action receipts")
    verify.add_argument("--session", required=True)
    verify.add_argument("--settings")
    assembly = commands.add_parser("assembly", help="Validate approved current-game systems")
    assembly.add_argument("--root", required=True)
    assembly.add_argument("--project", required=True)
    assembly.add_argument("--trusted-local-operator", action="store_true")
    return result


def _load(path: str):
    source = Path(path)
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 200000:
        raise SystemEditorError("editor input must be a bounded regular local JSON file")
    def distinct(pairs):
        values = {}
        for k, v in pairs:
            if k in values:
                raise SystemEditorError("duplicate JSON member rejected")
            values[k] = v
        return values
    return json.loads(source.read_text(encoding="utf-8"),
                      object_pairs_hook=distinct,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          SystemEditorError("non-finite JSON number rejected")))


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.operation == "list":
            output = {"schema":"skeleton.game_builder.system_editor_catalog.v1",
                      "editors":catalog()}
        elif args.operation == "assembly":
            output = assemble_workspace_systems(
                GameWorkspace(args.root), args.project,
                authorized=args.trusted_local_operator)
        elif args.operation == "validate":
            output = validate_editor_document(_load(args.document))
        elif args.operation == "scene-template":
            output = make_advanced_scene(args.editor,
                _load(args.settings) if args.settings else None,
                seed=args.seed,scene_id=args.scene_id,
                layout=_load(args.layout) if args.layout else None)
        elif args.operation == "solve-puzzle":
            output = solve_advanced_puzzle(
                _load(args.scene),
                _load(args.settings) if args.settings else None,
                max_states=args.max_states,max_depth=args.max_depth)
        elif args.operation == "godot-export":
            receipt=_load(args.session)
            settings=_load(args.settings) if args.settings else None
            renderer=(render_platformer_godot_package if receipt.get("editor")=="platformer"
                      else render_deck_godot_package if receipt.get("editor")=="deck_battler"
                      else render_shooter_godot_package if receipt.get("editor")=="shooter"
                      else render_advanced_godot_package)
            artifact=renderer(receipt,settings,authorized=args.trusted_local_operator)
            destination=write_advanced_godot_package(
                artifact,args.output,authorized=args.trusted_local_operator)
            output={**artifact.manifest,"local_output_path":str(destination)}
        elif args.operation == "save":
            output = export_advanced_savegame(_load(args.session),
                _load(args.settings) if args.settings else None)
        elif args.operation == "load-save":
            output = import_advanced_savegame(_load(args.savegame))
        elif args.operation == "continue-save":
            output = continue_advanced_savegame(
                _load(args.savegame),_load(args.actions))
        elif args.operation == "verify-play":
            output = {"verified":verify_advanced_session(
                _load(args.session), _load(args.settings) if args.settings else None)}
        elif args.operation in ("template", "preview", "play"):
            settings = _load(args.settings) if args.settings else None
            if args.operation == "template":
                output = json.loads(editor_source(args.editor, settings))
            else:
                actions = _load(args.actions) if args.actions else []
                if args.operation == "play":
                    output = run_advanced_session(
                        args.editor, settings, actions, seed=args.seed,
                        scene=_load(args.scene) if args.scene else None)
                else:
                    output = preview_editor(args.editor, settings, actions or None)
        else:
            raise SystemEditorError("unknown editor command")
        print(json.dumps(output, sort_keys=True, ensure_ascii=True,
                         separators=(",", ":"), allow_nan=False))
        return 0
    except (SystemEditorError, WorkspaceError, PermissionError,
            OSError, UnicodeError, ValueError) as exc:
        print("system editor rejected: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
