"""python -m skeleton — operator diagnostics and policy steering.

Now includes repair orchestrator, telemetry, learned policy,
multi-pass repair, and adaptive threshold tuning.
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
    # Enforcement CLI
    gc = sub.add_parser("gate-check")
    gc.add_argument("surface")
    gc.add_argument("score", type=float)
    sub.add_parser("repair-gate")
    rg = sub.add_parser("repair-gate")
    rg.add_argument("--surface", default="")
    # Repair orchestrator CLI
    sub.add_parser("repair-sessions")
    rs = sub.add_parser("repair-sessions")
    rs.add_argument("--surface", default="")
    rs.add_argument("-n", type=int, default=8)
    sub.add_parser("repair-effectiveness")
    reff = sub.add_parser("repair-effectiveness")
    reff.add_argument("--surface", default="")
    sub.add_parser("repair-telemetry")
    rt = sub.add_parser("repair-telemetry")
    rt.add_argument("--surface", default="")
    rt.add_argument("-n", type=int, default=16)
    sub.add_parser("repair-errors")
    rerr = sub.add_parser("repair-errors")
    rerr.add_argument("--surface", default="")
    sub.add_parser("learned-policy")
    sub.add_parser("repair-orchestrator")
    # Adaptive policy CLI
    sub.add_parser("adaptive-policy")
    ad = sub.add_parser("adapt")
    ad.add_argument("--surface", default="")
    ad.add_argument("--dry-run", action="store_true")
    sub.add_parser("adapt-all")
    ada = sub.add_parser("adapt-all")
    ada.add_argument("--dry-run", action="store_true")
    sac = sub.add_parser("set-adaptive-config")
    sac.add_argument("--target-accept-rate", type=float)
    sac.add_argument("--adjustment-rate", type=float)
    sac.add_argument("--window-size", type=int)
    sac.add_argument("--min-threshold", type=float)
    sac.add_argument("--max-threshold", type=float)
    sac.add_argument("--enabled", type=lambda x: x.lower() in {"true", "1", "yes", "on"})
    ssc = sub.add_parser("set-surface-adaptive")
    ssc.add_argument("surface")
    ssc.add_argument("--target-accept-rate", type=float)
    ssc.add_argument("--adjustment-rate", type=float)
    ssc.add_argument("--min-threshold", type=float)
    ssc.add_argument("--max-threshold", type=float)

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
    if args.cmd == "repair-gate":
        from skeleton.organism.policy_enforcement import repair_gate
        print(json.dumps(repair_gate(args.surface or "forge"), indent=2, default=str)); return 0
    if args.cmd == "repair-sessions":
        print(json.dumps(deck.repair_sessions(surface=args.surface, limit=args.n), indent=2, default=str)); return 0
    if args.cmd == "repair-effectiveness":
        print(json.dumps(deck.repair_effectiveness(surface=args.surface), indent=2, default=str)); return 0
    if args.cmd == "repair-telemetry":
        print(json.dumps(deck.repair_telemetry(surface=args.surface, limit=args.n), indent=2, default=str)); return 0
    if args.cmd == "repair-errors":
        print(json.dumps(deck.repair_errors(surface=args.surface), indent=2, default=str)); return 0
    if args.cmd == "learned-policy":
        print(json.dumps(deck.learned_policy(), indent=2, default=str)); return 0
    if args.cmd == "repair-orchestrator":
        print(json.dumps(deck.repair_orchestrator(), indent=2, default=str)); return 0
    if args.cmd == "adaptive-policy":
        print(json.dumps(deck.adaptive_policy(), indent=2, default=str)); return 0
    if args.cmd == "adapt":
        if args.surface:
            print(json.dumps(deck.adapt_surface(args.surface, dry_run=args.dry_run), indent=2, default=str)); return 0
        print(json.dumps(deck.adapt_all(dry_run=args.dry_run), indent=2, default=str)); return 0
    if args.cmd == "adapt-all":
        print(json.dumps(deck.adapt_all(dry_run=args.dry_run), indent=2, default=str)); return 0
    if args.cmd == "set-adaptive-config":
        kwargs = {}
        if args.target_accept_rate is not None:
            kwargs["target_accept_rate"] = args.target_accept_rate
        if args.adjustment_rate is not None:
            kwargs["adjustment_rate"] = args.adjustment_rate
        if args.window_size is not None:
            kwargs["window_size"] = args.window_size
        if args.min_threshold is not None:
            kwargs["min_threshold"] = args.min_threshold
        if args.max_threshold is not None:
            kwargs["max_threshold"] = args.max_threshold
        if args.enabled is not None:
            kwargs["enabled"] = args.enabled
        print(json.dumps(deck.set_adaptive_config(**kwargs), indent=2, default=str)); return 0
    if args.cmd == "set-surface-adaptive":
        kwargs = {}
        if args.target_accept_rate is not None:
            kwargs["target_accept_rate"] = args.target_accept_rate
        if args.adjustment_rate is not None:
            kwargs["adjustment_rate"] = args.adjustment_rate
        if args.min_threshold is not None:
            kwargs["min_threshold"] = args.min_threshold
        if args.max_threshold is not None:
            kwargs["max_threshold"] = args.max_threshold
        print(json.dumps(deck.set_surface_adaptive(args.surface, **kwargs), indent=2, default=str)); return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
