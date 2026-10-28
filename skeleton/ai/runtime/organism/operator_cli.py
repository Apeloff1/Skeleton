"""Real product CLI adapters over the existing canonical organism and kernel.

Documented commands use typed, bounded arguments; no user-specified import
or execute-eval. Sensitive operations have explicit mutation switches.
"""
from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module
from typing import Any, Sequence

PRODUCT_COMMANDS = ("wiki", "seed", "caps", "lattice", "pulse", "orch", "season", "scoreboard", "hot", "coverage", "decade", "bank", "switch", "witness", "gov", "cage", "rot", "fieldcov", "enact", "day", "week", "calendar", "conductor", "ctx", "live", "observe", "stacks", "mix", "satellites", "path", "bound", "fieldwalk", "dump", "orgwalk", "sleep", "forget", "helix", "recall")
MAX_CUE = 4096
_COUNT_LIMIT = {"ready":8, "orgwalk":8, "fieldwalk":8, "day":8,
                "week":3, "season":8, "decade":10}
_CUE = {"wiki", "pulse", "orch", "ctx", "live", "forget", "recall"}
# Real no-argument owner methods: command -> (module, function, calling convention).
_VIEWS = {
    "caps": ("skeleton.organism.caps", "card", "plain"),
    "lattice": ("skeleton.galaxy.lattice", "card", "mesh"),
    "scoreboard": ("skeleton.kernel.scoreboard", "card", "plain"),
    "hot": ("skeleton.kernel.hot", "rank", "root_kw"),
    "coverage": ("skeleton.kernel.coverage", "card", "plain"),
    "witness": ("skeleton.kernel.witness", "card", "plain"),
    "gov": ("skeleton.kernel.persist", "load_gov", "root_kw"),
    "cage": ("skeleton.galaxy.quarantine", "card", "plain"),
    "rot": ("skeleton.organism.rotctx", "card", "plain"),
    "fieldcov": ("skeleton.social.coverage", "coverage_card", "plain"),
    "calendar": ("skeleton.organism.calendar", "card", "root"),
    "observe": ("skeleton.organism.observe", "card", "root"),
    "stacks": ("skeleton.organism.stacks", "card", "root"),
    "mix": ("skeleton.organism.context_step", "mix_card", "root"),
    "satellites": ("skeleton.organism.satellites", "satellites_card", "org"),
    "path": ("skeleton.organism.path10", "path_card", "org"),
    "bound": ("skeleton.organism.runloop", "bound_card", "root"),
}


def _load_view_module(module_name: str):
    """Resolve only audited CLI view owners via literal imports."""
    if module_name == "skeleton.organism.caps":
        return import_module("skeleton.organism.caps")
    if module_name == "skeleton.galaxy.lattice":
        return import_module("skeleton.galaxy.lattice")
    if module_name == "skeleton.kernel.scoreboard":
        return import_module("skeleton.kernel.scoreboard")
    if module_name == "skeleton.kernel.hot":
        return import_module("skeleton.kernel.hot")
    if module_name == "skeleton.kernel.coverage":
        return import_module("skeleton.kernel.coverage")
    if module_name == "skeleton.kernel.witness":
        return import_module("skeleton.kernel.witness")
    if module_name == "skeleton.kernel.persist":
        return import_module("skeleton.kernel.persist")
    if module_name == "skeleton.galaxy.quarantine":
        return import_module("skeleton.galaxy.quarantine")
    if module_name == "skeleton.organism.rotctx":
        return import_module("skeleton.organism.rotctx")
    if module_name == "skeleton.social.coverage":
        return import_module("skeleton.social.coverage")
    if module_name == "skeleton.organism.calendar":
        return import_module("skeleton.organism.calendar")
    if module_name == "skeleton.organism.observe":
        return import_module("skeleton.organism.observe")
    if module_name == "skeleton.organism.stacks":
        return import_module("skeleton.organism.stacks")
    if module_name == "skeleton.organism.context_step":
        return import_module("skeleton.organism.context_step")
    if module_name == "skeleton.organism.satellites":
        return import_module("skeleton.organism.satellites")
    if module_name == "skeleton.organism.path10":
        return import_module("skeleton.organism.path10")
    if module_name == "skeleton.organism.runloop":
        return import_module("skeleton.organism.runloop")
    raise ValueError("unregistered CLI view module")


def _parser(command: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=f"python -m skeleton {command}")
    parser.add_argument("--json", action="store_true")
    if command == "ready":
        parser.add_argument("--fix", action="store_true")
        parser.add_argument("--walk", action="store_true")
    if command in {"ready", "season", "day", "fieldwalk", "orgwalk"}:
        parser.add_argument("-n", type=int, default=2)
    if command == "week":
        parser.add_argument("--days", type=int, default=2)
    if command == "decade":
        parser.add_argument("--seasons", type=int, default=3)
    if command == "wiki":
        parser.add_argument("--limit", type=int, default=24, help="maximum citation rows, 1-128")
    if command == "bank":
        parser.add_argument("--reset", action="store_true")
    if command == "switch":
        from skeleton.kernel.profiles import PROFILES
        parser.add_argument("profile", choices=sorted(PROFILES))
    if command == "conductor":
        g = parser.add_mutually_exclusive_group()
        g.add_argument("--run", action="store_true")
        g.add_argument("--commit", action="store_true")
    if command == "ctx":
        g = parser.add_mutually_exclusive_group()
        g.add_argument("--replay", action="store_true")
        g.add_argument("--refine", action="store_true")
    if command == "dump":
        g = parser.add_mutually_exclusive_group()
        g.add_argument("--hot", action="store_true", help="inspect hot files without rotation")
        g.add_argument("--force", action="store_true", help="explicitly force a rotating backup")
    if command == "sleep":
        parser.add_argument("--force", action="store_true")
    if command in _CUE:
        parser.add_argument("cue", nargs="*")
    return parser


def _execute(command: str, org: Any, args: Any) -> Any:
    root = getattr(org, "root", None)
    cue = " ".join(args.cue) if command in _CUE else ""
    if command in _VIEWS:
        module, func, mode = _VIEWS[command]
        method = getattr(_load_view_module(module), func)
        return (method() if mode == "plain" else
                method(root) if mode == "root" else
                method(root=root) if mode == "root_kw" else
                method(org.galaxy.mesh) if mode == "mesh" else
                method(org))
    if command == "ready":
        from skeleton.organism.ready import ready_card
        return ready_card(org, walk=args.walk, fix=args.fix, n=args.n)
    if command == "product":
        from skeleton.organism.product import product_card
        return product_card(org)
    if command == "health":
        from skeleton.organism.health import health_card
        return health_card(org)
    if command == "next":
        from skeleton.organism.next import hint
        return hint(org)
    if command == "wiki":
        from skeleton.galaxy.query import run
        return run(org.galaxy.mesh, cue, limit=args.limit)
    if command == "seed":
        from skeleton.social.seed import seed_field
        return seed_field(org.galaxy)
    if command == "pulse":
        from skeleton.organism.pulse import pulse
        return pulse(org, stimulus=cue)
    if command == "orch":
        from skeleton.kernel.bank import boot, get
        boot()
        engine = get("orch")
        if engine is None:
            return {"kind":"kernel-orch", "ok":0, "reason":"active profile has no orchestrator"}
        return engine.dispatch(cue or "plan tensor ttk")
    if command == "season":
        from skeleton.kernel.season import run
        return run(n=args.n)
    if command == "decade":
        from skeleton.kernel.decade import run
        return run(seasons=args.seasons)
    if command == "bank":
        from skeleton.kernel.bank import boot, reset, snapshot
        if args.reset:
            return reset()
        boot()
        return snapshot()
    if command == "switch":
        from skeleton.kernel.switch import to
        return to(args.profile)
    if command == "enact":
        from skeleton.organism.scope import enact
        return enact(org)
    if command == "day":
        from skeleton.organism.day import run
        return run(org, n=args.n)
    if command == "week":
        from skeleton.organism.week import run
        return run(org, days=args.days)
    if command == "conductor":
        from skeleton.organism.conductor import commit, decide, run
        return commit(org) if args.commit else run(org) if args.run else decide(org)
    if command == "ctx":
        from skeleton.organism.context_step import refine, replay, run
        return replay(org, cue, root=root) if args.replay else (
            refine(org, cue, rounds=2) if args.refine else run(org, cue))
    if command == "live":
        from skeleton.organism.runtime import dispatch
        return dispatch(org, stimulus=cue)
    if command == "fieldwalk":
        from skeleton.organism.fieldwalk import walk
        return walk(org, n=args.n, root=root)
    if command == "orgwalk":
        from skeleton.organism.runloop import walk
        return walk(org, n=args.n)
    if command == "dump":
        from skeleton.organism.chronicle.dump import dump, hot_card
        return hot_card(root) if args.hot else dump(root, force=args.force)
    if command == "sleep":
        from skeleton.organism.sleep import cycle
        return cycle(org, force=args.force)
    if command == "forget":
        from skeleton.organism.forget import sweep
        return sweep(org.galaxy.mesh, cue=cue)
    if command == "helix":
        from skeleton.organism.helix import card, verify
        result = card(root)
        return {**result, "integrity":verify(root)}
    if command == "recall":
        from skeleton.organism.helix import recall
        return recall(cue, root=root)
    raise ValueError(f"unsupported operator command: {command}")


def run_operator_cli(command: str, argv: Sequence[str]) -> int:
    if command not in ("ready", "product", "health", "next", *PRODUCT_COMMANDS):
        raise ValueError("unknown operator command")
    parser = _parser(command)
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return int(exc.code)
    count = (
        args.n if hasattr(args, "n") else
        args.days if hasattr(args, "days") else
        args.seasons if hasattr(args, "seasons") else None
    )
    if (command in _COUNT_LIMIT and (count is None or not 1 <= count <= _COUNT_LIMIT[command])) or (
            command == "wiki" and not 1 <= args.limit <= 128) or (
            command in _CUE and len(" ".join(args.cue)) > MAX_CUE):
        parser.print_usage(sys.stderr)
        print(f"{command}: workload or cue exceeds bounds", file=sys.stderr)
        return 2
    from skeleton.organism.organismer import live_organismer
    try:
        result = _execute(command, live_organismer(), args)
    except (OSError, ValueError) as exc:
        print(f"{command}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 1 if not isinstance(result, dict) or (
        "ok" in result and not bool(result["ok"])) else 0
