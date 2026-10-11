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
from .game_project_workspace import GameWorkspace, WorkspaceError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.system_editor_cli",
        description="Typed, offline, bounded original game mechanics authoring")
    commands = result.add_subparsers(dest="operation", required=True)
    commands.add_parser("list", help="Enumerate real system editor capabilities")
    for name in ("template", "validate", "preview"):
        p = commands.add_parser(name)
        p.add_argument("--editor", required=name != "validate")
        p.add_argument("--settings", help="Path to a local UTF-8 JSON settings object")
        if name == "validate":
            p.add_argument("--document", required=True)
        if name == "preview":
            p.add_argument("--actions", help="Path to a bounded JSON action array")
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
        elif args.operation in ("template", "preview"):
            settings = _load(args.settings) if args.settings else None
            if args.operation == "template":
                output = json.loads(editor_source(args.editor, settings))
            else:
                actions = _load(args.actions) if args.actions else None
                output = preview_editor(args.editor, settings, actions)
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
