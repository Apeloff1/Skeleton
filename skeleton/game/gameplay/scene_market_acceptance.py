"""End-to-end offline market acceptance: play -> checkpoint -> replay -> export.

Acceptance is evidence about one exact authored source and action witness, not
a declaration that every game, target device or consumer installer is ready.
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
from skeleton.game.gameplay.scene_market import (
    _json, export_market, import_market, normalize_market, original_market,
    resume_market, simulate_market, verify_market,
)
from skeleton.game.gameplay.scene_market_author import (
    edit_market, verify_market_edit,
)
from skeleton.game.gameplay.scene_market_interactive import (
    play_market,
)
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_acceptance.v1"


def _commands(actions: list[dict[str, Any]]) -> str:
    # Strict JSON actions avoid conflating parser convenience with game logic.
    return "".join(json.dumps(action, sort_keys=True) + "\n"
                   for action in actions)


def audit_market(source: Any, actions: Any, *,
                 require_victory: bool = True,
                 include_editor: bool = False) -> dict[str, Any]:
    if type(require_victory) is not bool or type(include_editor) is not bool:
        raise SceneTravelError("invalid market acceptance options")
    spec = normalize_market(source)
    if type(actions) is not list or not actions:
        raise SceneTravelError("market acceptance requires action witness")
    complete = simulate_market(spec, actions)
    if require_victory and complete["state"]["phase"] != "won":
        raise SceneTravelError("market acceptance requires earned victory")
    split = len(actions) // 2
    partial = simulate_market(spec, actions[:split])
    resumed = resume_market(partial, actions[split:])
    if complete != resumed or verify_market(complete) != complete:
        raise SceneTravelError("market checkpoint replay differs from full play")
    bundle = export_market(complete)
    imported = import_market(bundle)
    if imported != complete:
        raise SceneTravelError("market portable import differs from game")
    stream = io.StringIO()
    interactive = play_market(
        spec, input_stream=io.StringIO(_commands(actions)),
        output_stream=stream, checkpoint_every=4,
    )
    if interactive != complete:
        raise SceneTravelError("interactive market differs from canonical play")
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    terminal = [e for e in events if e.get("event") == "terminal"]
    checkpoints = [e for e in events if e.get("event") == "checkpoint"]
    if (len(terminal) != 1 or not checkpoints
            or checkpoints[-1]["session"] != complete):
        raise SceneTravelError("market stream missing terminal custody")
    editor_receipt = None
    if include_editor:
        # A deliberately changed price is replayed without changing the
        # audited game source. Editor evidence is separate from play proof.
        offer = next((o for m in spec["markets"] for o in m["offers"]), None)
        if offer is None:
            raise SceneTravelError("editor acceptance requires a market offer")
        value = offer["price"] + 1 if offer["price"] < 1000 else 999
        editor_receipt = edit_market(
            spec, [{"kind": "set_price", "offer_id": offer["offer_id"],
                    "value": value}], dig(spec),
        )
        if verify_market_edit(editor_receipt) != editor_receipt:
            raise SceneTravelError("market author receipt replay differs")
    # A checksum is not a signature; replay and exact source custody are
    # the acceptance proof. Reject even syntactically valid altered bundles.
    tampered = copy.deepcopy(bundle)
    tampered["state_digest"] = "0" * 64
    try:
        import_market(tampered)
    except SceneTravelError:
        tamper_rejected = True
    else:
        tamper_rejected = False
    if not tamper_rejected:
        raise SceneTravelError("market bundle tampering accepted")
    report = {
        "schema_version": SCHEMA, "ok": True,
        "source_digest": complete["source_digest"],
        "state_digest": complete["state_digest"],
        "phase": complete["state"]["phase"],
        "actions": len(actions), "credits": complete["state"]["credits"],
        "goods": complete["state"]["goods"],
        "purchases": complete["state"]["purchases"],
        "crafted": complete["state"]["crafted"],
        "delivered": complete["state"]["delivered"],
        "reputation": complete["state"]["reputation"],
        "checkpoint_state_digest": partial["state_digest"],
        "portable_checksum": bundle["checksum"],
        "interactive_terminal_digest": terminal[0]["state_digest"],
        "interactive_checkpoints": len(checkpoints),
        "tampered_bundle_rejected": tamper_rejected,
        "editor_receipt_checksum": (
            editor_receipt["checksum"] if editor_receipt is not None else None
        ),
        "qualification": "single_source_offline_gameplay_only",
    }
    report["report_digest"] = dig(report)
    _bounded(report)
    return report


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    audit = sub.add_parser("audit")
    audit.add_argument("--source-json", required=True)
    audit.add_argument("--actions-json", required=True)
    audit.add_argument("--allow-loss", action="store_true")
    audit.add_argument("--include-editor", action="store_true")
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_market()
            result = audit_market(source, actions, include_editor=True)
        else:
            result = audit_market(
                _json(args.source_json), _json(args.actions_json),
                require_victory=not args.allow_loss,
                include_editor=args.include_editor,
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
