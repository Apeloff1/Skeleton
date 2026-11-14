"""Player-driven capture bounty play with opponent AI and verified rewards.

Reuses the canonical control-point interactive input/AI policy. Only replayed
canonical actions can earn objective rewards; EOF and invalid commands return
a recoverable contract checkpoint without asserting a victory.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from skeleton.game.gameplay.arena_control import _encoded
from skeleton.game.gameplay.arena_control_contracts import (
    new_contract, normalize_contract, original_contract, play_contract,
    verify_contract,
)
from skeleton.game.gameplay.arena_control_interactive import (
    MAX_INPUTS, play_interactive,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.arena_control_contracts_interactive.v1"


def play_contract_interactive(
    source: Any, team: Any, *, resume: Any = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    max_inputs: int = MAX_INPUTS,
) -> dict[str, Any]:
    spec = normalize_contract(source)
    selected = _id(team, "team")
    if selected != spec["player_team"]:
        raise CombatSessionError("interactive contract requires authored player team")
    budget = _integer(max_inputs, "max_inputs", 1, MAX_INPUTS)
    current = new_contract(spec) if resume is None else verify_contract(resume)
    if current["source_digest"] != dig(spec):
        raise CombatSessionError("interactive contract source mismatch")
    writer = output_stream if output_stream is not None else sys.stdout
    control_result = play_interactive(
        spec["control"], selected,
        resume=current["control_session"],
        input_stream=input_stream, output_stream=writer, max_inputs=budget)
    control = control_result["session"]
    # Rebuild the entire bounty from the actual canonical action journal.
    # Neither a claimed score nor an interactive UI message is a reward.
    actions = [event["action"] for event in control["journal"]]
    contract = play_contract(spec, actions)
    if contract["control_session"] != control:
        raise CombatSessionError("interactive control replay mismatch")
    result = {
        "schema_version": SCHEMA,
        "status": control_result["status"],
        "reason": control_result["reason"],
        "team": selected,
        "contract_session": contract,
        "source_digest": contract["source_digest"],
        "state_digest": contract["state_digest"],
        "claim": "offline_replay_checked_not_authenticated",
    }
    result["receipt"] = dig(result)
    writer.write(_encoded({"type": "contract_result", **result}) + "\n")
    writer.flush()
    return result


def verify_interactive_receipt(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "status", "reason", "team", "contract_session",
        "source_digest", "state_digest", "claim", "receipt",
    }, "interactive capture contract receipt")
    if obj["schema_version"] != SCHEMA or obj["claim"] != "offline_replay_checked_not_authenticated":
        raise CombatSessionError("unsupported interactive capture contract receipt")
    _encoded(obj)
    session = verify_contract(obj["contract_session"])
    if obj["team"] != session["source"]["player_team"]:
        raise CombatSessionError("interactive contract team mismatch")
    if obj["source_digest"] != session["source_digest"] or obj["state_digest"] != session["state_digest"]:
        raise CombatSessionError("interactive contract digest mismatch")
    status = obj["status"]
    if status not in ("completed", "checkpoint", "rejected"):
        raise CombatSessionError("invalid interactive contract status")
    terminal = session["state"]["phase"] != "active"
    if (status == "completed") != terminal:
        raise CombatSessionError("interactive contract terminal status mismatch")
    if type(obj["reason"]) is not str or len(obj["reason"]) > 512:
        raise CombatSessionError("invalid interactive contract reason")
    if dig({k: v for k, v in obj.items() if k != "receipt"}) != obj["receipt"]:
        raise CombatSessionError("interactive contract receipt mismatch")
    return obj


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-control-contracts-play")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--max-inputs", type=int, default=MAX_INPUTS)
    play = sub.add_parser("play")
    play.add_argument("--source-json", required=True)
    play.add_argument("--team", required=True)
    play.add_argument("--max-inputs", type=int, default=MAX_INPUTS)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--team", required=True)
    resume.add_argument("--max-inputs", type=int, default=MAX_INPUTS)
    verify = sub.add_parser("verify")
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = play_contract_interactive(original_contract(), "wayfarers",
                                               max_inputs=args.max_inputs)
        elif args.command == "play":
            result = play_contract_interactive(
                _parse_json(args.source_json, "contract source"), args.team,
                max_inputs=args.max_inputs)
        elif args.command == "resume":
            saved = _parse_json(args.session_json, "contract checkpoint")
            result = play_contract_interactive(
                saved["source"], args.team, resume=saved,
                max_inputs=args.max_inputs)
        else:
            result = verify_interactive_receipt(
                _parse_json(args.receipt_json, "interactive contract receipt"))
            print(_encoded(result))
            return 0
        return 2 if result["status"] == "rejected" else 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
