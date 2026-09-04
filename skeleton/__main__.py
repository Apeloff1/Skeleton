"""python -m skeleton — run, intake, eras, check.

Fix (2026-08-29): two subparsers were both registered under the name
``plan`` (``pl`` and ``pb``), so argparse raised ``conflicting subparser``
at startup — no CLI command could run at all. The builder-plan command is
now ``build-plan``; ``plan`` keeps the live-Jeeves plan_build path.
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m skeleton")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("product", help="operator product card for the living organism")
    sub.add_parser("failures", help="latest failure and recurring failure issues")
    sub.add_parser("repairs", help="latest repair and repair rollups")
    ac = sub.add_parser("activity", help="recent quality and repair activity")
    ac.add_argument("-n", type=int, default=8)
    sub.add_parser("recurring", help="recurring failure issues and repair targets")

    args = p.parse_args(argv)

    if args.cmd == "product":
        from skeleton.cortex.deck import live_deck
        print(json.dumps(live_deck().product(), indent=2, default=str))
        return 0

    if args.cmd == "failures":
        from skeleton.cortex.deck import live_deck
        print(json.dumps(live_deck().failures(), indent=2, default=str))
        return 0

    if args.cmd == "repairs":
        from skeleton.cortex.deck import live_deck
        print(json.dumps(live_deck().repairs(), indent=2, default=str))
        return 0

    if args.cmd == "activity":
        from skeleton.cortex.deck import live_deck
        out = live_deck().activity()
        out["requested_n"] = int(args.n)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "recurring":
        from skeleton.cortex.deck import live_deck
        print(json.dumps(live_deck().recurring(), indent=2, default=str))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
