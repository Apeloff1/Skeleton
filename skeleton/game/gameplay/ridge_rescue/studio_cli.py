"""Single user-reachable launcher for Cinder Ridge's original playable systems.

The command table is closed and explicit; user input never selects a Python
module or file to import. Every subsystem keeps its own source, save, replay
and fail-closed CLI contracts.
"""
from __future__ import annotations

import argparse
import importlib
import json
from typing import Callable

COMMANDS = {
    "rescue": ("cli", "Base rescue game: movement, combat, crafting and earned endings"),
    "consumer": ("consumer_cli", "Persistent original game: play, save, quit, restart and export"),
    "campaign": ("campaign_cli", "Multi-episode original rescue campaign"),
    "missions": ("missions_cli", "Source-bound mission DAG and replay-derived objectives"),
    "journal": ("journal_cli", "CAS-protected deterministic save and recovery"),
    "package": ("package_cli", "Portable offline game packaging"),
    "routebook": ("routebook_cli", "Authored executable rescue routes"),
    "tactics": ("tactics_cli", "Exact next-turn preview and bounded autoplay"),
    "workbench": ("workbench_cli", "Interactive terrain, actor and source editing"),
    "league": ("league_cli", "Replay-derived offline championship"),
    "league-demo": ("league_acceptance", "Real two-entrant earned championship"),
    "acceptance": ("qualification_cli", "Executable source-to-runtime acceptance matrix"),
    "challenges": ("challenges_cli", "Eight original playable terrain rescue frontiers"),
}


def catalog() -> dict:
    return {"schema": "ridge.rescue.launcher.v1", "game_id": "cinder-ridge-rescue",
            "offline": True, "commands": [
                {"id": name, "module": module, "description": description}
                for name, (module, description) in sorted(COMMANDS.items())
            ], "release_certified": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ridge", description="Cinder Ridge original game studio")
    parser.add_argument("system", nargs="?", help="subsystem name or 'list'")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="arguments passed to the subsystem")
    parsed = parser.parse_args(argv)
    if parsed.system in (None, "list"):
        print(json.dumps(catalog(), sort_keys=True, separators=(",", ":")))
        return 0
    if parsed.system not in COMMANDS:
        parser.error("unknown Cinder Ridge subsystem")
    module_name = COMMANDS[parsed.system][0]
    # Only the closed, statically defined package namespace may be imported.
    module = importlib.import_module("." + module_name, package=__package__)
    entrypoint: Callable[[list[str] | None], int] = getattr(module, "main")
    return entrypoint(parsed.args)


if __name__ == "__main__":
    raise SystemExit(main())
