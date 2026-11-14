"""Portable journal commands. All writes create new files, no in-place mutation."""
from __future__ import annotations
import argparse
import json
from .cli import DEMO_PATH
from .schema import parse_world
from .io import read_bounded, write_new
from .journal import open_journal, append_journal, verify_journal, fork_journal, export_journal, import_run

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ridge-rescue-journal")
    parser.add_argument("command", choices=("init", "append", "verify", "fork", "export", "import"))
    parser.add_argument("--world", default=str(DEMO_PATH))
    parser.add_argument("--journal")
    parser.add_argument("--bundle")
    parser.add_argument("--expected", help="exact prior journal head digest")
    parser.add_argument("--action", help="one canonical action JSON object")
    parser.add_argument("--sequence", type=int)
    parser.add_argument("--output", help="create-only output path")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            report = open_journal(parse_world(read_bounded(args.world, 96_000)))
        elif args.command == "import":
            if not args.bundle:
                raise ValueError("--bundle required")
            report = import_run(read_bounded(args.bundle))
        else:
            if not args.journal:
                raise ValueError("--journal required")
            journal = json.loads(read_bounded(args.journal))
            if args.command == "verify":
                verified = verify_journal(journal)
                report = {"valid": True, "head": verified["head"], "turn": verified["state"]["turn"], "status": verified["state"]["status"]}
            elif args.command == "append":
                if not args.expected or not args.action:
                    raise ValueError("--expected and --action required")
                report = append_journal(journal, json.loads(args.action), expected_head=args.expected)
            elif args.command == "fork":
                if not args.expected or args.sequence is None:
                    raise ValueError("--expected and --sequence required")
                report = fork_journal(journal, expected_head=args.expected, sequence=args.sequence)
            else:
                report = export_journal(journal)
        if args.output:
            write_new(args.output, report)
        else:
            print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, f"ridge-rescue-journal: {exc}\n")

if __name__ == "__main__":
    raise SystemExit(main())
