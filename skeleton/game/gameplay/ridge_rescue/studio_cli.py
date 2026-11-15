"""Single user-reachable launcher for Cinder Ridge's original playable systems.

The command table is closed and explicit; user input never selects a Python
module or file to import. Every subsystem keeps its own source, save, replay
and fail-closed CLI contracts.
"""
from __future__ import annotations

import argparse
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
    # Closed lazy imports preserve optional subsystem isolation without
    # passing even allowlisted variable strings into importlib.
    entrypoint: Callable[[list[str] | None], int]
    if parsed.system == "rescue":
        from .cli import main as entrypoint
    elif parsed.system == "consumer":
        from .consumer_cli import main as entrypoint
    elif parsed.system == "campaign":
        from .campaign_cli import main as entrypoint
    elif parsed.system == "missions":
        from .missions_cli import main as entrypoint
    elif parsed.system == "journal":
        from .journal_cli import main as entrypoint
    elif parsed.system == "package":
        from .package_cli import main as entrypoint
    elif parsed.system == "routebook":
        from .routebook_cli import main as entrypoint
    elif parsed.system == "tactics":
        from .tactics_cli import main as entrypoint
    elif parsed.system == "workbench":
        from .workbench_cli import main as entrypoint
    elif parsed.system == "league":
        from .league_cli import main as entrypoint
    elif parsed.system == "league-demo":
        from .league_acceptance import main as entrypoint
    elif parsed.system == "acceptance":
        from .qualification_cli import main as entrypoint
    elif parsed.system == "challenges":
        from .challenges_cli import main as entrypoint
    else:
        raise RuntimeError("launcher inventory and dispatch differ")
    return entrypoint(parsed.args)


if __name__ == "__main__":
    raise SystemExit(main())
