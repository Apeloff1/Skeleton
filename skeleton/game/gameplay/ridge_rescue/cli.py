"""CLI: source -> play -> deterministic save -> verify -> edit -> export."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .schema import parse_world, world_dict
from .engine import apply, available_actions, initial_state, RescueError
from .custody import export_run, verify_run, digest
from .authoring import revise, verify_revision, validate_reachability
from .guidance import hint
from .io import read_bounded, write_new
from .acceptance import run_acceptance
from .quests import progress
from .economy import BASE, price
from .render import render_map, legend

DEMO_PATH = Path(__file__).with_name("cinder_ridge.json")

def _source(path: str | None):
    return parse_world(read_bounded(path or DEMO_PATH, 96_000))

def _actions(raw: str) -> list[dict]:
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("actions must be a JSON list")
    return data

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ridge-rescue")
    parser.add_argument("command", choices=("inspect", "play", "verify", "guide", "author", "verify-author", "interactive", "demo", "quests", "market"))
    parser.add_argument("--world")
    parser.add_argument("--actions", default="[]", help="JSON array of canonical action objects")
    parser.add_argument("--bundle", help="existing portable bundle for verify")
    parser.add_argument("--operation", help="JSON authoring operation")
    parser.add_argument("--revision", help="existing revision for verify-author")
    parser.add_argument("--output", help="create-only portable output file")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            report = run_acceptance("protect")
        elif args.command == "verify":
            if not args.bundle:
                raise ValueError("--bundle required")
            result = verify_run(read_bounded(args.bundle))
            report = {"valid": True, "status": result["state"]["status"], "turns": result["state"]["turn"]}
        elif args.command == "verify-author":
            if not args.revision or not args.operation:
                raise ValueError("--revision and --operation required")
            world = _source(args.world)
            revision = json.loads(read_bounded(args.revision))
            report = {"valid": verify_revision(world, revision, json.loads(args.operation))}
        else:
            world = _source(args.world)
            if args.command == "inspect":
                validate_reachability(world)
                report = {"name": world.name, "sha256": digest(world_dict(world)), "civilians": len(world.civilians), "raiders": len(world.raiders), "max_turns": world.max_turns}
            elif args.command == "author":
                if not args.operation:
                    raise ValueError("--operation required")
                report = revise(world, expected_sha256=digest(world_dict(world)), operation=json.loads(args.operation))
            elif args.command in {"quests", "market"}:
                state = initial_state(world)
                for action in _actions(args.actions):
                    state = apply(world, state, action)
                report = progress(world, state) if args.command == "quests" else {"credits": state["credits"], "stock": state["market"], "buy": {item: price(state["market"], "buy", item) for item in BASE}, "sell": {item: price(state["market"], "sell", item) for item in BASE}}
            elif args.command == "guide":
                state = initial_state(world)
                for action in _actions(args.actions):
                    state = apply(world, state, action)
                report = hint(world, state)
            elif args.command == "interactive":
                history = []
                state = initial_state(world)
                while state["status"] == "playing":
                    choices = available_actions(world, state)
                    print(render_map(world, state))
                    print(legend())
                    print(json.dumps({"actions": choices}, sort_keys=True))
                    line = input("action index (q to quit)> ").strip()
                    if line == "q":
                        break
                    if not line.isdigit() or not 0 <= int(line) < len(choices):
                        print("invalid choice")
                        continue
                    action = choices[int(line)]
                    state = apply(world, state, action)
                    history.append(action)
                report = export_run(world, history)
            else:
                actions = _actions(args.actions)
                report = export_run(world, actions)
        if args.output:
            write_new(args.output, report)
        else:
            print(json.dumps(report, sort_keys=True, separators=(",", ":"), default=str))
        return 0
    except (ValueError, OSError, json.JSONDecodeError, EOFError) as exc:
        parser.exit(2, f"ridge-rescue: {exc}\n")

if __name__ == "__main__":
    raise SystemExit(main())
