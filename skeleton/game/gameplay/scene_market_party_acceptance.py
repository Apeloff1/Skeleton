"""End-to-end acceptance of cooperative player turns and portable market saves."""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _json
from skeleton.game.gameplay.scene_market_party import (
    export_party, import_party, normalize_party, original_party,
    resume_party, simulate_party, verify_party,
)
from skeleton.game.gameplay.scene_market_party_board import inspect_party
from skeleton.game.gameplay.scene_market_party_interactive import play_party
from skeleton.game.gameplay.scene_market_party_route import (
    solve_party_route, verify_party_route,
)
from skeleton.game.gameplay.scene_tile_walk import MAX_STEPS, _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_party_delivery_acceptance.v1"


def accept_party_delivery(source: Any, turns: Any,
                          *, split: int | None = None) -> dict[str, Any]:
    spec = normalize_party(source)
    if type(turns) is not list or not 1 <= len(turns) <= MAX_STEPS:
        raise SceneTravelError("invalid cooperative acceptance turn list")
    cut = len(turns) // 2 if split is None else split
    if type(cut) is not int or not 0 <= cut < len(turns):
        raise SceneTravelError("invalid cooperative acceptance split")
    initial = simulate_party(spec, [])
    first = simulate_party(spec, turns[:cut])
    if verify_party(first) != first:
        raise SceneTravelError("pre-restart party replay diverged")
    portable_partial = export_party(first)
    restored = import_party(json.loads(json.dumps(portable_partial)))
    if restored != first:
        raise SceneTravelError("portable party restart changed checkpoint")
    board = inspect_party(restored)
    if board["state_digest"] != restored["state_digest"]:
        raise SceneTravelError("cooperative legal-action board drift")
    # The real interactive engine reads action-only JSON lines and assigns
    # the next actor from canonical turn state; caller-supplied actor IDs
    # remain checked by the independent replay below.
    commands = "".join(json.dumps(turn["action"], sort_keys=True) + "\n"
                       for turn in turns[cut:])
    output = io.StringIO()
    played = play_party(session=restored,
                        expected_source_digest=restored["source_digest"],
                        checkpoint_every=3,
                        input_stream=io.StringIO(commands),
                        output_stream=output)
    direct = simulate_party(spec, turns)
    resumed = resume_party(restored, turns[cut:])
    if played != direct or resumed != direct:
        raise SceneTravelError("interactive and batch cooperative replays diverged")
    if direct["state"]["market"]["state"]["phase"] != "won":
        raise SceneTravelError("cooperative acceptance did not earn victory")
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    if (not events or events[-1].get("event") != "terminal"
            or events[-1].get("state_digest") != direct["state_digest"]):
        raise SceneTravelError("interactive cooperative terminal receipt missing")
    checkpoints = [item for item in events if item.get("event") == "checkpoint"]
    if not checkpoints or checkpoints[-1]["session"] != direct:
        raise SceneTravelError("interactive terminal checkpoint not replayable")
    for item in checkpoints:
        if verify_party(item["session"]) != item["session"]:
            raise SceneTravelError("interactive checkpoint lineage invalid")
    final_bundle = export_party(direct)
    if import_party(json.loads(json.dumps(final_bundle))) != direct:
        raise SceneTravelError("cooperative final export failed round trip")
    witness = solve_party_route(initial, max_depth=min(MAX_STEPS, len(turns)),
                                hint_turns=turns)
    if verify_party_route(initial, witness) != witness:
        raise SceneTravelError("cooperative route proof failed verification")
    if witness["terminal_state_digest"] != direct["state_digest"]:
        raise SceneTravelError("cooperative route proof differs from gameplay")
    result = {
        "schema_version": SCHEMA,
        "source_digest": direct["source_digest"],
        "initial_state_digest": initial["state_digest"],
        "checkpoint_state_digest": first["state_digest"],
        "terminal_state_digest": direct["state_digest"],
        "terminal_save_digest": dig(direct["save"]),
        "portable_partial_checksum": portable_partial["checksum"],
        "portable_final_checksum": final_bundle["checksum"],
        "route_checksum": witness["checksum"],
        "turn_count": len(turns),
        "restart_turn": cut,
        "interactive_accepted": sum(
            event.get("event") == "accepted" for event in events),
        "checkpoint_count": len(checkpoints),
        "phase": "won",
        "qualification": "offline_gameplay_replay_not_device_or_release",
    }
    if result["interactive_accepted"] != len(turns) - cut:
        raise SceneTravelError("interactive accepted turn count mismatch")
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-party-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    accept = sub.add_parser("accept")
    accept.add_argument("--source-json", required=True)
    accept.add_argument("--turns-json", required=True)
    accept.add_argument("--split", type=int)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, turns = original_party()
            result = accept_party_delivery(source, turns)
        else:
            result = accept_party_delivery(
                _json(args.source_json), _json(args.turns_json),
                split=args.split,
            )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
