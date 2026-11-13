"""Accessible JSON-lines combat contract play with human or auto opponents.

The canonical combat engine owns turn validation. The mission is reconstructed
from the combat actions, so the interactive transcript cannot mint rewards.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _parse_json, play_interactive,
)
from skeleton.game.gameplay.combat_contract import (
    MAX_SESSION_BYTES, _bounded, new_contract, normalize_contract,
    original_contract, resume_contract, verify_contract,
)


def play_contract(source: Any, *, resume: Any = None,
                  auto_opponents: bool = True,
                  input_stream: Any = None,
                  output_stream: Any = None) -> dict[str, Any]:
    spec = normalize_contract(source)
    session = new_contract(spec) if resume is None else verify_contract(resume)
    if session["source"] != spec:
        raise CombatSessionError("interactive contract source mismatch")
    if session["state"]["phase"] != "active":
        raise CombatSessionError("cannot interact with terminal contract")
    if type(auto_opponents) is not bool:
        raise CombatSessionError("invalid auto-opponents flag")
    teams = sorted({actor["team"] for actor in spec["scenario"]["actors"]})
    automated = ([team for team in teams if team != spec["player_team"]]
                 if auto_opponents else [])
    writer = sys.stdout if output_stream is None else output_stream
    start = len(session["journal"])
    combat = play_interactive(
        spec["scenario"], resume=session["state"]["combat"],
        auto_teams=automated, input_stream=input_stream,
        output_stream=writer,
    )
    actions = [event["action"] for event in combat["journal"][start:]]
    finished = resume_contract(session, actions)
    if finished["state"]["combat"] != combat:
        raise CombatSessionError("interactive combat replay mismatch")
    writer.write(json.dumps({
        "event": "contract_terminal",
        "phase": finished["state"]["phase"],
        "earned_credits": finished["state"]["credits"],
        "earned_inventory": finished["state"]["inventory"],
        "objectives": finished["state"]["objectives"],
        "state_digest": finished["state_digest"],
        "save": finished["save"],
    }, sort_keys=True, separators=(",", ":")) + "\n")
    writer.flush()
    return finished


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-contract-play")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--source-json")
    parser.add_argument("--resume-json")
    parser.add_argument("--manual-opponents", action="store_true")
    args = parser.parse_args(list(argv))
    try:
        if args.demo == (args.source_json is not None):
            raise CombatSessionError("choose exactly one of --demo or --source-json")
        source = (original_contract() if args.demo
                  else _parse_json(args.source_json, "contract source"))
        resume = (_parse_json(args.resume_json, "contract checkpoint")
                  if args.resume_json is not None else None)
        finished = play_contract(
            source, resume=resume, auto_opponents=not args.manual_opponents,
        )
        _bounded(finished, MAX_SESSION_BYTES)
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError,
            RecursionError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
