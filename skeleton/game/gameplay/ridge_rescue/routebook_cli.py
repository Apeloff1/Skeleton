"""CLI for source-authored routebooks and replay-verified game sessions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .io import read_bounded, write_new
from .routebook import (RoutebookError, parse_routebook, open_route, verify_route,
                        step_route, run_route, export_route, verify_route_export)
from .routebook_editor import revise_routebook, verify_routebook_revision

DEMO = Path(__file__).with_name("cinder_ridge_routebook.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ridge-routebook")
    parser.add_argument("command", choices=("inspect", "open", "step", "run", "verify", "export",
                                           "verify-export", "edit", "verify-edit", "interactive"))
    parser.add_argument("--source", help="routebook source JSON")
    parser.add_argument("--track", default="protect-route")
    parser.add_argument("--session", help="previous route session JSON")
    parser.add_argument("--bundle", help="portable route export")
    parser.add_argument("--revision", help="previous route source revision")
    parser.add_argument("--operation", help="JSON edit operation")
    parser.add_argument("--expected-head", help="CAS revision of the previous session")
    parser.add_argument("--output", help="create-only output; never overwrites")
    args = parser.parse_args(argv)
    try:
        if args.command in {"inspect", "open", "run", "edit", "verify-edit"}:
            source = read_bounded(args.source or DEMO, 160_000)
        if args.command == "inspect":
            data = parse_routebook(source)
            report = {"id": data["id"], "tracks": [{"id": x["id"], "steps": len(x["steps"]),
                      "ending": x["ending"]} for x in data["tracks"]]}
        elif args.command == "open":
            report = open_route(source, args.track)
        elif args.command == "run":
            report = export_route(run_route(source, args.track))
        elif args.command == "edit":
            if not args.operation:
                raise RoutebookError("--operation required")
            report = revise_routebook(source, json.loads(args.operation))
        elif args.command == "verify-edit":
            if not args.revision or not args.operation:
                raise RoutebookError("--revision and --operation required")
            report = {"valid": verify_routebook_revision(source,
                      json.loads(read_bounded(args.revision, 160_000)), json.loads(args.operation))}
        elif args.command == "verify-export":
            if not args.bundle:
                raise RoutebookError("--bundle required")
            checked = verify_route_export(read_bounded(args.bundle, 512_000))
            report = {"valid": True, "status": checked["status"], "head": checked["head"]}
        else:
            if not args.session:
                raise RoutebookError("--session required")
            session = json.loads(read_bounded(args.session, 512_000))
            if args.command == "step":
                if not args.expected_head:
                    raise RoutebookError("--expected-head required")
                report = step_route(session, expected_head=args.expected_head)
            elif args.command == "export":
                report = export_route(session)
            elif args.command == "interactive":
                report = session
                while True:
                    checked = verify_route(report)
                    if checked["status"] == "completed":
                        break
                    step = checked["track"]["steps"][checked["cursor"]]
                    print(json.dumps({"turn": checked["state"]["turn"], "next": step,
                                      "health": checked["state"]["health"]}, sort_keys=True))
                    answer = input("execute next route action? (y/q)> ").strip().lower()
                    if answer == "q":
                        break
                    if answer != "y":
                        print("expected y or q")
                        continue
                    report = step_route(report, expected_head=checked["head"])
            else:
                checked = verify_route(session)
                report = {"valid": True, "status": checked["status"], "cursor": checked["cursor"],
                          "head": checked["head"], "state": checked["state"]}
        if args.output:
            write_new(args.output, report, 512_000)
        else:
            print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (ValueError, OSError, KeyError, TypeError, EOFError) as exc:
        parser.exit(2, f"ridge-routebook: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
