"""End-to-end acceptance for authored, playable circuit puzzles.

The acceptance witness is built from real game transitions. A search timeout
never becomes a victory; saved checkpoints and portable exports must replay
to the same source-bound terminal state before a report can be certified.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_circuit import (
    export_circuit, import_circuit, normalize_circuit, original_circuit,
    resume_circuit, simulate_circuit, verify_circuit,
)
from skeleton.game.gameplay.scene_circuit_author import (
    author_circuit, verify_author_report,
)
from skeleton.game.gameplay.scene_circuit_solver import (
    plan_circuit, verify_plan,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _json, _object

SCHEMA = "skeleton.scene_circuit_accept.v1"
MAX_BYTES = 2 * 1024 * 1024


def _bounded(value: Any, label: str) -> Any:
    try:
        size = len(json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8"))
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise SceneTravelError(f"invalid {label} JSON") from exc
    if size > MAX_BYTES:
        raise SceneTravelError(f"{label} exceeds portable size budget")
    return value


def accept_circuit(
    source: Any, edits: Any = None, *,
    max_states: int = 1024, max_depth: int = 64,
) -> dict[str, Any]:
    """Prove editor -> legal route -> live game -> save -> export -> import.

    No source or edit argument is mutated. An unproved victory is rejected,
    including exhausted solver budgets and terminal failure endings.
    """
    before = normalize_circuit(source)
    operations = [] if edits is None else edits
    authored = author_circuit(
        before, operations, max_states=max_states, max_depth=max_depth,
    )
    verify_author_report(authored)
    world = authored["source"]
    plan = authored["preview"]
    if plan["status"] != "found":
        raise SceneTravelError(
            "circuit acceptance requires replay-proven victory; "
            f"solver returned {plan['status']}"
        )
    verify_plan(plan, source=world)
    actions = plan["actions"]
    halfway = len(actions) // 2
    checkpoint = simulate_circuit(world, actions[:halfway])
    verified_checkpoint = verify_circuit(checkpoint)
    terminal = resume_circuit(verified_checkpoint, actions[halfway:])
    terminal = verify_circuit(terminal)
    if (
        terminal["state"]["scene"]["state"]["phase"] != "won"
        or terminal["state_digest"] != plan["final_state_digest"]
        or terminal["source_digest"] != plan["source_digest"]
    ):
        raise SceneTravelError("circuit acceptance victory witness mismatch")
    portable = export_circuit(terminal)
    restored = import_circuit(portable)
    if restored != terminal:
        raise SceneTravelError("circuit portable round-trip mismatch")
    report = {
        "schema_version": SCHEMA,
        "source": before,
        "edits": authored["edits"],
        "source_digest": authored["source_digest"],
        "author_receipt": authored["receipt"],
        "plan": plan,
        "checkpoint": checkpoint,
        "terminal": terminal,
        "portable": portable,
        "phase": "won",
    }
    report["receipt"] = dig(report)
    return _bounded(report, "circuit acceptance report")


def verify_acceptance(payload: Any) -> dict[str, Any]:
    """Recompute every witness; a self-consistent forged digest is insufficient."""
    report = _object(payload, {
        "schema_version", "source", "edits", "source_digest",
        "author_receipt", "plan", "checkpoint", "terminal",
        "portable", "phase", "receipt",
    }, "circuit acceptance report")
    if report["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported circuit acceptance report")
    _bounded(report, "circuit acceptance report")
    plan = report["plan"]
    if type(plan) is not dict:
        raise SceneTravelError("invalid circuit acceptance plan")
    try:
        rebuilt = accept_circuit(
            report["source"], report["edits"],
            max_states=plan["max_states"], max_depth=plan["max_depth"],
        )
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise SceneTravelError("invalid circuit acceptance witness") from exc
    if rebuilt != report:
        raise SceneTravelError("circuit acceptance replay mismatch")
    return rebuilt


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-circuit-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    check = sub.add_parser("check")
    check.add_argument("--source-json", required=True)
    check.add_argument("--edits-json", default="[]")
    check.add_argument("--max-states", type=int, default=1024)
    check.add_argument("--max-depth", type=int, default=64)
    verify = sub.add_parser("verify")
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_circuit()
            result = accept_circuit(source)
        elif args.command == "check":
            result = accept_circuit(
                _json(args.source_json, "circuit source", max_bytes=MAX_BYTES),
                _json(args.edits_json, "circuit edits", max_bytes=MAX_BYTES),
                max_states=args.max_states, max_depth=args.max_depth,
            )
        else:
            result = verify_acceptance(
                _json(args.report_json, "acceptance report", max_bytes=MAX_BYTES)
            )
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (SceneTravelError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
