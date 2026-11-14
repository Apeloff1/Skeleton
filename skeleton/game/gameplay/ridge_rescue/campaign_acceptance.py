"""Full two-chapter deterministic campaign acceptance, from source to portable replay.

The script exercises actual engine transitions. It does not inject flags, skip
turns, patch state, or claim a victory that the runtime did not earn.
"""
from __future__ import annotations

from pathlib import Path

from .acceptance import acceptance_actions
from .campaign import open_campaign, step_campaign, verify_campaign, export_campaign, verify_export
from .engine import RescueError

SOURCE = Path(__file__).with_name("cinder_ridge_campaign.json")

LAST_SIGNAL = [
    {"verb": "move", "direction": "east"},
    {"verb": "rescue", "target": "mira"},
    {"verb": "move", "direction": "south"},
    {"verb": "move", "direction": "south"},
    {"verb": "move", "direction": "south"},
    {"verb": "move", "direction": "south"},
    {"verb": "move", "direction": "south"},
    {"verb": "move", "direction": "east"},
    {"verb": "move", "direction": "east"},
    {"verb": "rest"},
    {"verb": "move", "direction": "east"},
    {"verb": "move", "direction": "east"},
    {"verb": "rescue", "target": "orin"},
    {"verb": "move", "direction": "south"},
    {"verb": "rest"},
    {"verb": "move", "direction": "east"},
    {"verb": "move", "direction": "east"},
    {"verb": "move", "direction": "east"},
    {"verb": "evacuate", "choice": "salvage"},
]


def run_acceptance() -> dict:
    """Play both original worlds and return a verified, portable campaign export."""
    session = open_campaign(SOURCE.read_bytes())
    for index, actions in enumerate((acceptance_actions("protect"), LAST_SIGNAL)):
        if session["index"] != index:
            raise RescueError("campaign chapter did not unlock")
        for action in actions:
            session = step_campaign(session, action, expected_head=session["head"])
        if len(session["completed"]) != index + 1:
            raise RescueError("chapter did not earn required ending")
    checked = verify_campaign(session)
    if checked["status"] != "completed" or checked["index"] != 2:
        raise RescueError("campaign was not completed")
    if checked["session"]["completed"][0]["state"]["status"] != "won:protect":
        raise RescueError("first chapter ending mismatch")
    if checked["session"]["completed"][1]["state"]["status"] != "won:salvage":
        raise RescueError("second chapter ending mismatch")
    result = export_campaign(session)
    if verify_export(result)["head"] != session["head"]:
        raise RescueError("portable replay did not round-trip")
    return result
