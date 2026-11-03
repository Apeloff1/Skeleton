"""Offline rescue-league CLI with real replay verification and CAS admission."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from .io import read_bounded, write_new
from .league import (LeagueError, parse_league, open_league, verify_league,
                     submit_run, export_league, verify_league_export)

SOURCE = Path(__file__).with_name("cinder_ridge_league.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ridge-league")
    parser.add_argument("command", choices=("inspect", "open", "submit", "rank", "verify", "export", "verify-export"))
    parser.add_argument("--source", help="source league JSON")
    parser.add_argument("--board", help="previous CAS league board")
    parser.add_argument("--run", help="canonical portable game run JSON")
    parser.add_argument("--bundle", help="portable league export")
    parser.add_argument("--handle", help="local entrant label, not trusted identity")
    parser.add_argument("--expected-head", help="CAS board revision")
    parser.add_argument("--output", help="create-only output")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-export":
            if not args.bundle:
                raise LeagueError("--bundle required")
            checked = verify_league_export(read_bounded(args.bundle, 1_000_000))
            report = {"valid": True, "head": checked["head"], "ranking": checked["ranking"]}
        else:
            source = parse_league(read_bounded(args.source or SOURCE, 128_000))
            if args.command == "inspect":
                report = {"source": source, "max_entries": source["max_entries"]}
            else:
                board = json.loads(read_bounded(args.board, 1_000_000)) if args.board else open_league(source)
                if args.command == "open":
                    report = board
                elif args.command == "submit":
                    if not args.run or not args.handle or not args.expected_head:
                        raise LeagueError("--run, --handle and --expected-head required")
                    report = submit_run(board, expected_head=args.expected_head, handle=args.handle,
                                        run=json.loads(read_bounded(args.run, 256_000)))
                elif args.command == "export":
                    report = export_league(board)
                else:
                    checked = verify_league(board)
                    report = {"valid": True, "head": checked["head"], "entries": checked["entries"],
                              "champion": checked["champion"], "ranking": checked["ranking"]}
        if args.output:
            write_new(args.output, report, 1_000_000)
        else:
            print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, f"ridge-league: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
