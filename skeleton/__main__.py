"""python -m skeleton — operator diagnostics and policy steering.

Now includes policy-enforcement CLI commands.
"""
from __future__ import annotations

import argparse
import json


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m skeleton")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("product")
    fl = sub.add_parser("failures")
    fl.add_argument("--surface", default="")
    rp = sub.add_parser("repairs")
    rp.add_argument("--surface", default="")
    ac = sub.add_parser("activity")
    ac.add_argument("-n", type=int, default=8)
    ac.add_argument("--surface", default="")
    ac.add_argument("--kind", default="")
    rc = sub.add_parser("recurring")
    rc.add_argument("--surface", default="")
    sub.add_parser("policy")
    th = sub.add_parser("threshold")
    th.add_argument("--surface", default="")
    sth = sub.add_parser("set-threshold")
    sth.add_argument("surface")
    sth.add_argument("value", type=float)
    sre = sub.add_parser("set-repair-enabled")
    sre.add_argument("surface")
    sre.add_argument("enabled")
    src = sub.add_parser("set-repair-class")
    src.add_argument("name")
    src.add_argument("enabled")
    # New enforcement CLI
    sub.add_parser("gate-check")
    gc = sub.add_parser("gate")
    gc.add_argument("surface")
    gc.add_argument("score", type=float)
    sub.add_parser("repair-gate")
    rg = sub.add_parser("repair-gate")
    rg.add_argument("--surface", default="")

    args = p.parse_args(argv)
    from skeleton.cortex.deck import live_deck
    deck = live_deck()

    if args.cmd == "product":
        print(json.dumps(deck.product(), indent=2, default=str)); return 0
    if args.cmd == "failures":
        print(json.dumps(deck.failures(surface=args.surface), indent=2, default=str)); return 0
    if args.cmd == "repairs":
        print(json.dumps(deck.repairs(surface=args.surface), indent=2, default=str)); return 0
    if args.cmd == "activity":
        print(json.dumps(deck.activity(surface=args.surface, kind=args.kind, limit=args.n), indent=2, default=str)); return 0
    if args.cmd == "recurring":
        print(json.dumps(deck.recurring(surface=args.surface), indent=2, default=str)); return 0
    if args.cmd == "policy":
        print(json.dumps(deck.policy(), indent=2, default=str)); return 0
    if args.cmd == "threshold":
        print(json.dumps(deck.threshold(surface=args.surface), indent=2, default=str)); return 0
    if args.cmd == "set-threshold":
        print(json.dumps(deck.set_threshold(args.surface, args.value), indent=2, default=str)); return 0
    if args.cmd == "set-repair-enabled":
        enabled = str(args.enabled).lower() in {"1", "true", "yes", "on"}
        print(json.dumps(deck.set_repair_enabled(args.surface, enabled), indent=2, default=str)); return 0
    if args.cmd == "set-repair-class":
        enabled = str(args.enabled).lower() in {"1", "true", "yes", "on"}
        print(json.dumps(deck.set_repair_class(args.name, enabled), indent=2, default=str)); return 0
    if args.cmd == "gate-check":
        from skeleton.organism.policy_enforcement import gate_check
        print(json.dumps(gate_check(args.surface, args.score), indent=2, default=str)); return 0
    if args.cmd == "gate":
        from skeleton.organism.policy_enforcement import gate_check
        print(json.dumps(gate_check(args.surface, args.score), indent=2, default=str)); return 0
    if args.cmd == "repair-gate":
        from skeleton.organism.policy_enforcement import repair_gate
        print(json.dumps(repair_gate(args.surface or "forge"), indent=2, default=str)); return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
