"""User-facing mission graph inspection, evaluation, transactional editing and export."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .custody import digest
from .io import read_bounded, write_new
from .missions import (parse_missions, evaluate_missions, revise_missions,
                       verify_revision, export_missions, verify_export, MissionError)

SOURCE = Path(__file__).with_name("cinder_ridge_missions.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ridge-rescue-missions")
    parser.add_argument("command", choices=("inspect", "evaluate", "author", "verify-author", "export", "verify"))
    parser.add_argument("--source")
    parser.add_argument("--journal")
    parser.add_argument("--bundle")
    parser.add_argument("--operation")
    parser.add_argument("--revision")
    parser.add_argument("--expected-head")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            if not args.bundle:
                raise MissionError("--bundle required")
            report = verify_export(read_bounded(args.bundle, 512_000))
        else:
            source = parse_missions(read_bounded(args.source or SOURCE, 128_000))
            if args.command == "inspect":
                report = {"id": source["id"], "sha256": digest(source),
                          "nodes": len(source["nodes"]), "total_points": sum(n["points"] for n in source["nodes"])}
            elif args.command in {"evaluate", "export"}:
                if not args.journal:
                    raise MissionError("--journal required")
                journal = json.loads(read_bounded(args.journal, 256_000))
                report = evaluate_missions(source, journal) if args.command == "evaluate" else export_missions(source, journal)
            else:
                if not args.operation:
                    raise MissionError("--operation required")
                operation = json.loads(args.operation)
                if args.command == "author":
                    if not args.expected_head:
                        raise MissionError("--expected-head required")
                    report = revise_missions(source, expected_sha256=args.expected_head, operation=operation)
                else:
                    if not args.revision:
                        raise MissionError("--revision required")
                    report = {"valid": verify_revision(source, json.loads(read_bounded(args.revision, 128_000)), operation)}
        if args.output:
            write_new(args.output, report, 512_000)
        else:
            print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f"ridge-rescue-missions: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
