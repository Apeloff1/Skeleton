"""Terminal map editor and scripted CLI for source-bound playable worlds."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shlex

from .custody import digest
from .io import read_bounded, write_new
from .render import render_map
from .engine import initial_state
from .schema import parse_world
from .workbench import (WorkbenchError, open_workbench, verify_workbench,
                        edit_workbench, undo_workbench, export_workbench,
                        verify_workbench_export, preview_workbench)

DEMO = Path(__file__).with_name("cinder_ridge.json")


def parse_command(line: str) -> dict | str:
    if not isinstance(line, str) or len(line) > 512:
        raise WorkbenchError("invalid editor command")
    try:
        parts = shlex.split(line)
    except ValueError as exc:
        raise WorkbenchError("invalid command quoting") from exc
    if not parts:
        raise WorkbenchError("empty editor command")
    verb = parts[0]
    if len(parts) == 1 and verb in {"show", "undo", "export", "quit"}:
        return verb
    if verb == "tile" and len(parts) == 4:
        return {"kind": "set-tile", "target": [int(parts[1]), int(parts[2])], "value": parts[3]}
    if verb == "move" and len(parts) == 5 and parts[1] in {"civilian", "raider", "resource"}:
        return {"kind": "move-" + parts[1], "target": parts[2], "value": [int(parts[3]), int(parts[4])]}
    if verb == "resource" and len(parts) == 3:
        return {"kind": "set-resource-count", "target": parts[1], "value": int(parts[2])}
    if verb == "turns" and len(parts) == 2:
        return {"kind": "set-turn-budget", "target": "world", "value": int(parts[1])}
    if verb == "name" and len(parts) >= 2:
        return {"kind": "rename", "target": "world", "value": " ".join(parts[1:])}
    raise WorkbenchError("unsupported editor command")


def _edit_commands(session: dict, commands: list[str]) -> dict:
    if not isinstance(commands, list) or len(commands) > 128:
        raise WorkbenchError("invalid editor command count")
    result = session
    for line in commands:
        op = parse_command(line)
        if op == "undo":
            result = undo_workbench(result, expected_head=result["head"])
        elif op == "show":
            verify_workbench(result)
        elif op in ("export", "quit"):
            raise WorkbenchError("non-edit command in scripted edit list")
        else:
            result = edit_workbench(result, op, expected_head=result["head"])
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ridge-workbench")
    parser.add_argument("command", choices=("open", "inspect", "edit", "undo", "export",
                                           "verify-export", "preview", "interactive"))
    parser.add_argument("--source", help="original world source")
    parser.add_argument("--session", help="existing workbench session")
    parser.add_argument("--expected-head", help="CAS revision for edit and undo")
    parser.add_argument("--commands", help="JSON array of editor commands")
    parser.add_argument("--actions", default="[]", help="JSON array of canonical gameplay actions")
    parser.add_argument("--bundle", help="portable workbench export")
    parser.add_argument("--output", help="create-only output")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-export":
            if not args.bundle:
                raise WorkbenchError("--bundle required")
            checked = verify_workbench_export(read_bounded(args.bundle, 512_000))
            report = {"valid": True, "head": checked["head"], "source_sha256": checked["revision_sha256"]}
        else:
            if args.session:
                session = json.loads(read_bounded(args.session, 512_000))
            else:
                session = open_workbench(read_bounded(args.source or DEMO, 96_000))
            if args.command == "open":
                report = session
            elif args.command == "inspect":
                checked = verify_workbench(session)
                report = {"valid": True, "head": checked["head"],
                          "operations": len(checked["operations"]),
                          "source_sha256": checked["revision_sha256"]}
            elif args.command == "edit":
                if not args.expected_head or not args.commands:
                    raise WorkbenchError("--expected-head and --commands required")
                if args.expected_head != session["head"]:
                    raise WorkbenchError("stale workbench revision")
                report = _edit_commands(session, json.loads(args.commands))
            elif args.command == "undo":
                if not args.expected_head:
                    raise WorkbenchError("--expected-head required")
                report = undo_workbench(session, expected_head=args.expected_head)
            elif args.command == "export":
                report = export_workbench(session)
            elif args.command == "preview":
                report = preview_workbench(session, json.loads(args.actions))
            else:
                report = session
                while True:
                    checked = verify_workbench(report)
                    world = checked["world"]
                    print(render_map(world, initial_state(world)))
                    print("Commands: tile x y .|#|~|^ ; move civilian|raider|resource id x y ;")
                    print("resource id count ; turns count ; name text ; undo ; show ; export ; quit")
                    try:
                        command = parse_command(input("ridge-workbench> "))
                        if command == "quit":
                            break
                        if command == "show":
                            print(json.dumps({"head": checked["head"], "sha256": checked["revision_sha256"]}))
                            continue
                        if command == "export":
                            print(json.dumps(export_workbench(report), sort_keys=True))
                            continue
                        if command == "undo":
                            report = undo_workbench(report, expected_head=checked["head"])
                        else:
                            report = edit_workbench(report, command, expected_head=checked["head"])
                    except (ValueError, TypeError) as exc:
                        print("rejected:", exc)
            if args.output:
                write_new(args.output, report, 512_000)
            else:
                print(json.dumps(report, sort_keys=True, separators=(",", ":")))
            return 0
        if args.output:
            write_new(args.output, report, 512_000)
        else:
            print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (ValueError, OSError, TypeError, KeyError, EOFError) as exc:
        parser.exit(2, f"ridge-workbench: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
