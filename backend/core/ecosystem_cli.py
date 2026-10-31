"""CLI entry for the full-stack ecosystem.

Usage:
  python -m backend.core.ecosystem_cli "a short platformer with a boss"
"""
from __future__ import annotations
import argparse
import json

from backend.core.ecosystem_orchestrator import get_orchestrator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the full-stack studio ecosystem")
    parser.add_argument("brief", nargs="?", default="A compact era-bound platformer")
    parser.add_argument("--era", default="ash")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args(argv)

    orch = get_orchestrator()
    if args.health:
        print(json.dumps(orch.health(), indent=2))
        return 0
    if args.list:
        print(json.dumps(orch.list_sessions(), indent=2))
        return 0

    created = orch.create_session(args.brief, era=args.era, actor="cli")
    if not created.get("ok"):
        print(json.dumps(created, indent=2))
        return 2
    ran = orch.run(created["session_id"], actor="cli")
    print(json.dumps(ran, indent=2))
    return 0 if ran.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
