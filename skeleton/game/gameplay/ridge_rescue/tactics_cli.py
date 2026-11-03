"""Playable field tactics CLI: source -> preview -> canonical turn -> export."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from .custody import digest
from .io import read_bounded, write_new
from .journal import open_journal, verify_journal, export_journal
from .schema import parse_world
from .tactics import TacticsError, parse_policy, suggest, advance, autoplay
from .tactics_editor import revise_policy, verify_policy_revision

DEMO = Path(__file__).with_name("cinder_ridge.json")
POLICY = Path(__file__).with_name("cinder_ridge_tactics.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ridge-tactics")
    parser.add_argument("command", choices=("inspect", "open", "suggest", "step", "autoplay",
                                            "verify", "export", "edit", "verify-edit"))
    parser.add_argument("--world", help="source world JSON")
    parser.add_argument("--policy", help="source tactics policy JSON")
    parser.add_argument("--journal", help="CAS-protected journal JSON")
    parser.add_argument("--expected-head", help="previous journal head for step")
    parser.add_argument("--operation", help="JSON policy edit")
    parser.add_argument("--revision", help="JSON policy revision")
    parser.add_argument("--output", help="create-only output file")
    args = parser.parse_args(argv)
    try:
        world = parse_world(read_bounded(args.world or DEMO, 96_000))
        policy = parse_policy(read_bounded(args.policy or POLICY, 16_384))
        journal = json.loads(read_bounded(args.journal, 256_000)) if args.journal else open_journal(world)
        if args.command == "inspect":
            report = {"policy": policy, "source_sha256": digest(policy),
                      "world": world.name, "max_turns": world.max_turns}
        elif args.command == "open":
            report = open_journal(world)
        elif args.command == "suggest":
            report = suggest(world, journal, policy)
        elif args.command == "step":
            if not args.expected_head:
                raise TacticsError("--expected-head required")
            result = advance(world, journal, policy, expected_head=args.expected_head)
            report = result["journal"]
        elif args.command == "autoplay":
            report = autoplay(world, policy, journal)
        elif args.command == "verify":
            checked = verify_journal(journal)
            report = {"valid": True, "status": checked["state"]["status"], "head": checked["head"]}
        elif args.command == "export":
            report = export_journal(journal)
        elif args.command == "edit":
            if not args.operation:
                raise TacticsError("--operation required")
            report = revise_policy(world, policy, json.loads(args.operation))
        else:
            if not args.operation or not args.revision:
                raise TacticsError("--operation and --revision required")
            report = {"valid": verify_policy_revision(world, policy, json.loads(args.operation),
                      json.loads(read_bounded(args.revision, 16_384)))}
        if args.output:
            write_new(args.output, report, 512_000)
        else:
            print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, f"ridge-tactics: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
