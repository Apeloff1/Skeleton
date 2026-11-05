"""Offline scene production acceptance: source -> runtime -> replay -> export.

An acceptance report is *evidence*, not a device or release qualification.
The authoritative scene runtime performs every transition; this module
never executes authored scripts or trusts caller-supplied state receipts.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_ending_audit import audit_endings
from skeleton.game.gameplay.scene_portable import (
    export_scene_bundle, import_scene_bundle,
)
from skeleton.game.gameplay.scene_route_solver import plan_victory
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _json, new_session, original_demo,
    resume_session, verify_session,
)

SCHEMA = "skeleton.scene_acceptance.v1"
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_STATES = 4096
MAX_DEPTH = 512


def _budget(value: Any, name: str, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise SceneTravelError(f"invalid acceptance {name}")
    return value


def _proof(start: dict[str, Any], actions: Any,
           expected_digest: str, phase: str) -> dict[str, Any]:
    """Produce independent runtime, replay, and portable-save evidence."""
    if type(actions) is not list:
        raise SceneTravelError("acceptance witness actions must be a list")
    final = resume_session(start, actions)
    restored = verify_session(json.loads(json.dumps(final)))
    if final != restored or final["state"]["phase"] != phase:
        raise SceneTravelError("acceptance witness phase or replay mismatch")
    if final["state_digest"] != expected_digest:
        raise SceneTravelError("acceptance witness digest mismatch")
    bundle = export_scene_bundle(final)
    imported = import_scene_bundle(json.loads(json.dumps(bundle)))
    if imported != final:
        raise SceneTravelError("acceptance portable save mismatch")
    return {
        "phase": phase,
        "actions": actions,
        "final_state_digest": final["state_digest"],
        "final_save_digest": dig(final["save"]),
        "portable_checksum": bundle["checksum"],
        "journal_length": len(final["journal"]),
    }


def accept_scene(world: Any = None, *, session: Any = None,
                 max_states: int = 1024,
                 max_depth: int = 64) -> dict[str, Any]:
    """Qualify a playable authored world from an exact source/session.

    A full reachable-scene audit and a replayable victory witness are
    mandatory for "passed". Budget exhaustion is always inconclusive,
    never evidence of unreachable content. Reports can be reverified
    without trusting their claimed status or embedded proof.
    """
    if (world is None) == (session is None):
        raise SceneTravelError("supply exactly one world or saved session")
    states = _budget(max_states, "state budget", MAX_STATES)
    depth = _budget(max_depth, "depth budget", MAX_DEPTH)
    start = new_session(world) if session is None else verify_session(session)
    audit = audit_endings(session=start, max_states=states, max_depth=depth)
    route = plan_victory(session=start, max_states=states, max_depth=depth)
    if (
        audit["source_digest"] != start["source_digest"]
        or route["source_digest"] != start["source_digest"]
        or audit["initial_state_digest"] != start["state_digest"]
        or route["initial_state_digest"] != start["state_digest"]
    ):
        raise SceneTravelError("acceptance source or initial state drift")
    proofs: dict[str, dict[str, Any]] = {}
    for phase in ("won", "lost", "draw"):
        witness = audit["endings"][phase]["witness"]
        if witness is not None:
            proofs[phase] = _proof(
                start, witness["actions"],
                witness["final_state_digest"], phase,
            )
    if route["status"] == "found":
        route_proof = _proof(
            start, route["actions"], route["final_state_digest"], "won"
        )
    else:
        route_proof = None
    inconclusive = (
        audit["coverage"] == "inconclusive"
        or route["status"] == "inconclusive"
    )
    complete = (
        audit["coverage"] == "complete"
        and not audit["unobserved_scenes"]
        and "won" in proofs
        and route_proof is not None
    )
    status = "inconclusive" if inconclusive else (
        "passed" if complete else "failed"
    )
    report = {
        "schema_version": SCHEMA,
        "status": status,
        "release_qualified": False,
        "start_session": start,
        "source_digest": start["source_digest"],
        "initial_state_digest": start["state_digest"],
        "state_budget": states,
        "depth_budget": depth,
        "audit": audit,
        "victory_route": route,
        "route_proof": route_proof,
        "ending_proofs": proofs,
        "holds": (
            ["search_budget_exhausted"] if inconclusive else
            (["unobserved_scenes"] if audit["unobserved_scenes"] else [])
            + (["victory_not_proven"] if not route_proof else [])
            + (["victory_ending_not_proven"] if "won" not in proofs else [])
        ),
    }
    try:
        serialized = json.dumps(report, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise SceneTravelError("invalid acceptance report encoding") from exc
    if len(serialized.encode("utf-8")) > MAX_REPORT_BYTES:
        raise SceneTravelError("acceptance report exceeds 2 MiB budget")
    report["report_digest"] = dig(report)
    return report


def verify_acceptance(payload: Any) -> dict[str, Any]:
    """Recompute all witnesses and status; never trust an unverified report."""
    if type(payload) is not dict or set(payload) != {
        "schema_version", "status", "release_qualified", "start_session",
        "source_digest", "initial_state_digest", "state_budget",
        "depth_budget", "audit", "victory_route", "route_proof",
        "ending_proofs", "holds", "report_digest",
    }:
        raise SceneTravelError("invalid acceptance report fields")
    if payload["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported acceptance report schema")
    expected = accept_scene(
        session=payload["start_session"],
        max_states=payload["state_budget"],
        max_depth=payload["depth_budget"],
    )
    if expected != payload:
        raise SceneTravelError("acceptance report or proof mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton.game.gameplay.scene_acceptance"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Produce replay/export acceptance")
    source = check.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true")
    source.add_argument("--world-json")
    source.add_argument("--session-json")
    check.add_argument("--max-states", type=int, default=1024)
    check.add_argument("--max-depth", type=int, default=64)
    verify = sub.add_parser("verify", help="Recompute saved report evidence")
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "verify":
            report = verify_acceptance(
                _json(args.report_json, "acceptance report",
                      max_bytes=MAX_REPORT_BYTES)
            )
        else:
            world = (
                original_demo()[0] if args.demo else
                _json(args.world_json, "world")
                if args.world_json is not None else None
            )
            saved = (
                _json(args.session_json, "session",
                      max_bytes=MAX_REPORT_BYTES)
                if args.session_json is not None else None
            )
            report = accept_scene(
                world, session=saved,
                max_states=args.max_states, max_depth=args.max_depth,
            )
    except SceneTravelError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return {"passed": 0, "failed": 1, "inconclusive": 3}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
