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

# Reviewed literal import dispatch; no runtime-computed module paths.
_MODULE_LOADERS = {
    "cli": lambda: importlib.import_module(".cli", package=__package__),
    "consumer_cli": lambda: importlib.import_module(".consumer_cli", package=__package__),
    "campaign_cli": lambda: importlib.import_module(".campaign_cli", package=__package__),
    "missions_cli": lambda: importlib.import_module(".missions_cli", package=__package__),
    "journal_cli": lambda: importlib.import_module(".journal_cli", package=__package__),
    "package_cli": lambda: importlib.import_module(".package_cli", package=__package__),
    "routebook_cli": lambda: importlib.import_module(".routebook_cli", package=__package__),
    "tactics_cli": lambda: importlib.import_module(".tactics_cli", package=__package__),
    "workbench_cli": lambda: importlib.import_module(".workbench_cli", package=__package__),
    "league_cli": lambda: importlib.import_module(".league_cli", package=__package__),
    "league_acceptance": lambda: importlib.import_module(".league_acceptance", package=__package__),
    "qualification_cli": lambda: importlib.import_module(".qualification_cli", package=__package__),
    "challenges_cli": lambda: importlib.import_module(".challenges_cli", package=__package__),
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
    module = _MODULE_LOADERS[module_name]()
    entrypoint: Callable[[list[str] | None], int] = getattr(module, "main")
    return entrypoint(parsed.args)


if __name__ == "__main__":
    raise SystemExit(main())
