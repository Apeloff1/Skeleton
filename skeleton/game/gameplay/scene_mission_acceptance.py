"""End-to-end authored scene-mission acceptance with real playable witnesses.

Every ending is checked against the canonical mission director, replayed,
portable-exported and audited for actual choice/quest consequences. A bounded
search is explicitly inconclusive, never silently treated as certified.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_mission import (
    MAX_BYTES, export_mission, import_mission, new_mission, original_mission,
    verify_mission,
)
from skeleton.game.gameplay.scene_mission_consequences import inspect_consequences
from skeleton.game.gameplay.scene_mission_solver import (
    MAX_DEPTH, MAX_STATES, plan_ending, verify_plan,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _json

SCHEMA = "skeleton.scene_mission_acceptance.v1"


def accept_mission(source: Any = None, *, session: Any = None,
                   ending_id: str | None = None,
                   max_states: int = 256,
                   max_depth: int = 32) -> dict[str, Any]:
    """Prove actual play/export for each requested authored ending."""
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one mission source or checkpoint")
    if type(max_states) is not int or not 1 <= max_states <= MAX_STATES:
        raise SceneTravelError("invalid acceptance state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise SceneTravelError("invalid acceptance depth budget")
    initial = new_mission(source) if session is None else verify_mission(session)
    ids = [ending["id"] for ending in initial["source"]["endings"]]
    if ending_id is not None:
        selected = _id(ending_id, "ending_id")
        if selected not in ids:
            raise SceneTravelError("unknown authored acceptance ending")
        ids = [selected]
    findings = []
    for target in ids:
        plan = plan_ending(
            session=initial, target_ending=target,
            max_states=max_states, max_depth=max_depth,
        )
        finding: dict[str, Any] = {
            "ending_id": target,
            "status": plan["status"],
            "explored": plan["explored"],
            "budget_exhausted": plan["budget_exhausted"],
            "actions": plan["actions"],
            "terminal": None,
        }
        if plan["status"] == "found":
            final = verify_plan(plan, session=initial)
            if final["state"]["phase"] != "finished" or final["state"]["ending"] != target:
                raise SceneTravelError("acceptance ending replay mismatch")
            bundle = export_mission(final)
            imported = import_mission(bundle)
            if imported != final:
                raise SceneTravelError("acceptance portable roundtrip mismatch")
            consequences = inspect_consequences(imported)
            if consequences["ending"] != target:
                raise SceneTravelError("acceptance consequence ending mismatch")
            finding["terminal"] = {
                "state_digest": final["state_digest"],
                "event_bus_digest": final["event_bus_digest"],
                "bundle_checksum": bundle["checksum"],
                "consequence_receipt": consequences["receipt"],
                "reputation": consequences["reputation"],
                "missions": consequences["missions"],
                "choices": consequences["choices"],
            }
        findings.append(finding)
    report = {
        "schema_version": SCHEMA,
        "source_digest": initial["source_digest"],
        "initial_state_digest": initial["state_digest"],
        "max_states": max_states, "max_depth": max_depth,
        "target_ending": ending_id,
        "accepted": all(item["status"] == "found" for item in findings),
        "findings": findings,
    }
    report["checksum"] = dig(report)
    encoded = json.dumps(
        report, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_BYTES:
        raise SceneTravelError("mission acceptance report size budget exceeded")
    return report


def verify_acceptance(payload: Any, *, source: Any = None,
                      session: Any = None) -> dict[str, Any]:
    """Recompute the complete report, not merely its checksum or witness."""
    keys = {
        "schema_version", "source_digest", "initial_state_digest",
        "max_states", "max_depth", "target_ending",
        "accepted", "findings", "checksum",
    }
    if (
        type(payload) is not dict or set(payload) != keys
        or payload["schema_version"] != SCHEMA
    ):
        raise SceneTravelError("invalid mission acceptance receipt")
    expected = accept_mission(
        source, session=session, ending_id=payload["target_ending"],
        max_states=payload["max_states"], max_depth=payload["max_depth"],
    )
    if expected != payload:
        raise SceneTravelError("mission acceptance replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-mission-accept")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--session-json")
    parser.add_argument("--ending-id")
    parser.add_argument("--max-states", type=int, default=256)
    parser.add_argument("--max-depth", type=int, default=32)
    parser.add_argument("--verify-json")
    args = parser.parse_args(list(argv))
    try:
        source = (
            original_mission() if args.demo else
            _json(args.source_json, "mission source")
            if args.source_json is not None else None
        )
        saved = (
            _json(args.session_json, "mission checkpoint", max_bytes=MAX_BYTES)
            if args.session_json is not None else None
        )
        if args.verify_json is None:
            report = accept_mission(
                source, session=saved, ending_id=args.ending_id,
                max_states=args.max_states, max_depth=args.max_depth,
            )
        else:
            report = verify_acceptance(
                _json(args.verify_json, "acceptance receipt", max_bytes=MAX_BYTES),
                source=source, session=saved,
            )
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
