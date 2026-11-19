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

# Literal imports are delayed until the selected command executes. The catalog
# stays cheap and user input cannot construct an import target.
_ENTRYPOINTS: dict[str, Callable[[], Callable[[list[str] | None], int]]] = {
    "rescue": lambda: importlib.import_module("skeleton.game.gameplay.ridge_rescue.cli").main,
    "consumer": lambda: importlib.import_module("skeleton.game.gameplay.ridge_rescue.consumer_cli").main,
    "campaign": lambda: importlib.import_module("skeleton.game.gameplay.ridge_rescue.campaign_cli").main,
    "missions": lambda: importlib.import_module("skeleton.game.gameplay.ridge_rescue.missions_cli").main,
    "journal": lambda: importlib.import_module("skeleton.game.gameplay.ridge_rescue.journal_cli").main,
    "package": lambda: importlib.import_module("skeleton.game.gameplay.ridge_rescue.package_cli").main,
    "routebook": lambda: importlib.import_module("skeleton.game.gameplay.ridge_rescue.routebook_cli").main,
    "tactics": lambda: importlib.import_module("skeleton.game.gameplay.ridge_rescue.tactics_cli").main,
    "workbench": lambda: importlib.import_module("skeleton.game.gameplay.ridge_rescue.workbench_cli").main,
    "league": lambda: importlib.import_module("skeleton.game.gameplay.ridge_rescue.league_cli").main,
    "league-demo": lambda: importlib.import_module("skeleton.game.gameplay.ridge_rescue.league_acceptance").main,
    "acceptance": lambda: importlib.import_module("skeleton.game.gameplay.ridge_rescue.qualification_cli").main,
    "challenges": lambda: importlib.import_module("skeleton.game.gameplay.ridge_rescue.challenges_cli").main,
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
    entrypoint = _ENTRYPOINTS[parsed.system]()
    return entrypoint(parsed.args)


if __name__ == "__main__":
    raise SystemExit(main())
