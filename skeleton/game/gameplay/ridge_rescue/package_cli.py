"""Portable package CLI: build, verify and play an exported original game."""
from __future__ import annotations
import argparse
import json
from .cli import DEMO_PATH
from .schema import parse_world
from .io import read_bounded, write_new
from .package import build_package, verify_package, play_package

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ridge-rescue-package")
    parser.add_argument("command", choices=("build", "verify", "play"))
    parser.add_argument("--world", default=str(DEMO_PATH))
    parser.add_argument("--package")
    parser.add_argument("--actions", default="[]")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            report = build_package(parse_world(read_bounded(args.world, 96_000)))
        else:
            if not args.package:
                raise ValueError("--package required")
            package = json.loads(read_bounded(args.package, 192_000))
            if args.command == "verify":
                verified = verify_package(package)
                report = {"valid": True, "manifest": verified["manifest"]}
            else:
                actions = json.loads(args.actions)
                if not isinstance(actions, list):
                    raise ValueError("actions must be a list")
                report = play_package(package, actions)
        if args.output:
            write_new(args.output, report)
        else:
            print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f"ridge-rescue-package: {exc}\n")

if __name__ == "__main__":
    raise SystemExit(main())
