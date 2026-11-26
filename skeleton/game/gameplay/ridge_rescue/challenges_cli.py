"""Play and verify original Cinder Ridge terrain challenges."""
from __future__ import annotations
import argparse
import json

from .challenges import ChallengeError, list_challenges, play_challenge
from .custody import verify_run
from .io import read_bounded, write_new


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ridge-challenges")
    parser.add_argument("command", choices=("list", "play", "verify"))
    parser.add_argument("--id", help="authored challenge identifier")
    parser.add_argument("--bundle", help="portable game replay for verification")
    parser.add_argument("--output", help="create-only output")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            report = list_challenges()
        elif args.command == "play":
            if not args.id:
                raise ChallengeError("--id required")
            report = play_challenge(args.id)
        else:
            if not args.bundle:
                raise ChallengeError("--bundle required")
            checked = verify_run(read_bounded(args.bundle, 256_000))
            report = {"valid": True, "status": checked["state"]["status"],
                      "turns": checked["state"]["turn"]}
        if args.output:
            write_new(args.output, report, 256_000)
        else:
            print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, f"ridge-challenges: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
