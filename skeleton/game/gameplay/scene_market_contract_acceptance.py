"""End-to-end market commission acceptance across source, play, replay and export.

Acceptance is intentionally single-source and offline. It does not imply
hardware qualification, provider authentication or consumer release approval.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _bounded, _json
from skeleton.game.gameplay.scene_market_contract import (
    contract_board, export_contract, import_contract, normalize_contract_source,
    original_contract, resume_contract, simulate_contract, verify_contract,
)
from skeleton.game.gameplay.scene_market_contract_author import (
    edit_contract, verify_contract_edit,
)
from skeleton.game.gameplay.scene_market_contract_interactive import play_contract
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_contract_acceptance.v1"


def accept_contract(source: Any, actions: Any, *,
                    require_victory: bool = True,
                    include_authoring: bool = True) -> dict[str, Any]:
    spec = normalize_contract_source(source)
    if type(actions) is not list:
        raise SceneTravelError("invalid contract acceptance action batch")
    final = simulate_contract(spec, actions)
    if require_victory and final["state"]["phase"] != "won":
        raise SceneTravelError("contract acceptance requires canonical victory")
    split = len(actions) // 2
    checkpoint = simulate_contract(spec, actions[:split])
    resumed = resume_contract(checkpoint, actions[split:])
    if resumed != final or verify_contract(final) != final:
        raise SceneTravelError("contract acceptance checkpoint replay mismatch")
    bundle = export_contract(final)
    if import_contract(bundle) != final:
        raise SceneTravelError("contract acceptance portable restore mismatch")
    board = contract_board(final)
    if (board["score"] != final["state"]["score"]
            or board["phase"] != final["state"]["phase"]):
        raise SceneTravelError("contract acceptance board drift")
    stream = io.StringIO()
    commands = "\n".join(json.dumps(action) for action in actions) + "\n"
    interactive = play_contract(
        spec, input_stream=io.StringIO(commands),
        output_stream=stream, checkpoint_every=4,
    )
    if interactive != final:
        raise SceneTravelError("contract acceptance interactive replay drift")
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    terminal = [event for event in events if event.get("event") == "terminal"]
    checkpoints = [event for event in events if event.get("event") == "checkpoint"]
    if (len(terminal) != 1 or not checkpoints
            or checkpoints[-1]["session"] != final
            or terminal[0]["state_digest"] != final["state_digest"]):
        raise SceneTravelError("contract acceptance missing terminal checkpoint")
    tampered = copy.deepcopy(bundle)
    tampered["session"]["state"]["score"] += 100
    tampered["checksum"] = dig({
        key: value for key, value in tampered.items() if key != "checksum"
    })
    try:
        import_contract(tampered)
    except SceneTravelError:
        tamper_rejected = True
    else:
        tamper_rejected = False
    if not tamper_rejected:
        raise SceneTravelError("contract acceptance accepted forged score")
    author_checksum = None
    if include_authoring:
        first = spec["contracts"][0]
        replacement = first["reward_score"] + 1 if first["reward_score"] < 1000 else 999
        receipt = edit_contract(spec, [{
            "kind": "set_reward_score", "contract_id": first["contract_id"],
            "value": replacement,
        }], dig(spec))
        if verify_contract_edit(receipt) != receipt:
            raise SceneTravelError("contract acceptance author receipt mismatch")
        author_checksum = receipt["checksum"]
    report = {
        "schema_version": SCHEMA, "ok": True,
        "source_digest": final["source_digest"],
        "state_digest": final["state_digest"],
        "phase": final["state"]["phase"],
        "actions": len(actions), "score": final["state"]["score"],
        "completed": final["state"]["completed"],
        "credits": final["state"]["market"]["state"]["credits"],
        "goods": final["state"]["market"]["state"]["goods"],
        "reputation": final["state"]["market"]["state"]["reputation"],
        "checkpoint_digest": checkpoint["state_digest"],
        "bundle_checksum": bundle["checksum"],
        "board_checksum": board["checksum"],
        "terminal_checkpoint_count": len(checkpoints),
        "tampered_score_rejected": tamper_rejected,
        "author_receipt_checksum": author_checksum,
        "qualification": "single_source_offline_gameplay_only",
    }
    report["checksum"] = dig(report)
    _bounded(report)
    return report


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-contract-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    audit = sub.add_parser("audit")
    audit.add_argument("--source-json", required=True)
    audit.add_argument("--actions-json", required=True)
    audit.add_argument("--allow-loss", action="store_true")
    audit.add_argument("--skip-authoring", action="store_true")
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_contract()
            result = accept_contract(source, actions)
        else:
            result = accept_contract(
                _json(args.source_json), _json(args.actions_json),
                require_victory=not args.allow_loss,
                include_authoring=not args.skip_authoring,
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
