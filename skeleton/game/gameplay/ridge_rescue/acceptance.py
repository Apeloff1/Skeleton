"""Executable real source-to-protect/salvage end-to-end game acceptance."""
from __future__ import annotations
from pathlib import Path
from .schema import parse_world
from .custody import export_run, verify_run
from .engine import RescueError

ACCEPTANCE_SOURCE = Path(__file__).with_name("cinder_ridge_acceptance.json")
# Real actions: civilian -> finite gathering -> craft -> movement -> shelter -> earned ending.
COMMON = [
    {"verb": "rescue", "target": "tavi"},
    {"verb": "gather", "target": "kindling"},
    {"verb": "move", "direction": "east"},
    {"verb": "gather", "target": "ridge_ore"},
    {"verb": "gather", "target": "ridge_ore"},
]
TRAVEL = [
    {"verb": "move", "direction": "east"},
    {"verb": "move", "direction": "south"},
    {"verb": "move", "direction": "south"},
]

def acceptance_actions(choice: str) -> list[dict]:
    if choice not in {"protect", "salvage"}:
        raise RescueError("invalid acceptance ending")
    if choice == "protect":
        return COMMON + [{"verb": "craft", "item": "signal"}] + TRAVEL + [
            {"verb": "signal"},
            {"verb": "evacuate", "choice": "protect"},
        ]
    return COMMON + TRAVEL + [{"verb": "evacuate", "choice": "salvage"}]

def run_acceptance(choice: str = "protect") -> dict:
    world = parse_world(ACCEPTANCE_SOURCE.read_bytes())
    bundle = export_run(world, acceptance_actions(choice))
    verified = verify_run(bundle)
    if verified["state"]["status"] != f"won:{choice}":
        raise RescueError("acceptance outcome was not earned")
    if verified["state"]["civilians"]["tavi"] != "rescued":
        raise RescueError("acceptance did not rescue civilian")
    if choice == "protect" and not verified["state"]["flags"]["beacon"]:
        raise RescueError("protection ending missing beacon")
    return bundle
