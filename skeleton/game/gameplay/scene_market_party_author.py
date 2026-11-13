"""Source-digest-fenced cooperative market role editor with replayable receipts."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _json
from skeleton.game.gameplay.scene_market_party import (
    ROLES, normalize_party, original_party, simulate_party,
)
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _object

SCHEMA = "skeleton.scene_market_party_edit.v1"
MAX_EDITS = 32


def edit_party(source: Any, operations: Any, expected_source_digest: str,
               preview_turns: Any = None) -> dict[str, Any]:
    original = normalize_party(source)
    before = dig(original)
    if type(expected_source_digest) is not str or before != expected_source_digest:
        raise SceneTravelError("party source changed since editor read")
    if type(operations) is not list or not 1 <= len(operations) <= MAX_EDITS:
        raise SceneTravelError("invalid party edit batch")
    updated = copy.deepcopy(original)
    cleaned = []
    for raw in operations:
        op = _object(raw, {"kind", "player_id", "role"}, "party edit")
        if op["kind"] not in ("grant_role", "revoke_role"):
            raise SceneTravelError("unsupported party edit")
        player_id = _id(op["player_id"], "edited player")
        role = op["role"]
        if type(role) is not str or role not in ROLES:
            raise SceneTravelError("invalid edited role")
        player = next((p for p in updated["players"]
                       if p["player_id"] == player_id), None)
        if player is None:
            raise SceneTravelError("party edit player not authored")
        roles = set(player["roles"])
        if op["kind"] == "grant_role":
            roles.add(role)
        else:
            roles.discard(role)
        player["roles"] = sorted(roles)
        cleaned.append({"kind": op["kind"], "player_id": player_id,
                        "role": role})
    changed = normalize_party(updated)
    if changed == original:
        raise SceneTravelError("party edit has no effect")
    if preview_turns is not None and type(preview_turns) is not list:
        raise SceneTravelError("invalid party preview")
    preview = (simulate_party(changed, preview_turns)
               if preview_turns is not None else None)
    receipt = {"schema_version": SCHEMA, "original_source": original,
               "expected_source_digest": before, "operations": cleaned,
               "source": changed, "source_digest": dig(changed),
               "preview_turns": preview_turns,
               "preview_state_digest": preview["state_digest"]
               if preview is not None else None,
               "preview_phase": preview["state"]["market"]["state"]["phase"]
               if preview is not None else None}
    receipt["checksum"] = dig(receipt)
    _bounded(receipt)
    return receipt


def verify_party_edit(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "original_source",
                        "expected_source_digest", "operations", "source",
                        "source_digest", "preview_turns", "preview_state_digest",
                        "preview_phase", "checksum"}, "party edit receipt")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported party edit receipt")
    rebuilt = edit_party(obj["original_source"], obj["operations"],
                         obj["expected_source_digest"], obj["preview_turns"])
    if rebuilt != obj:
        raise SceneTravelError("party edit replay mismatch")
    return rebuilt


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-party-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    p = sub.add_parser("edit")
    p.add_argument("--source-json", required=True)
    p.add_argument("--expected-source-digest", required=True)
    p.add_argument("--operations-json", required=True)
    p.add_argument("--preview-turns-json")
    sub.add_parser("verify").add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, turns = original_party()
            result = edit_party(
                source, [{"kind": "grant_role", "player_id": "mira",
                          "role": "merchant"}],
                dig(normalize_party(source)), turns)
        elif args.command == "edit":
            result = edit_party(
                _json(args.source_json), _json(args.operations_json),
                args.expected_source_digest,
                _json(args.preview_turns_json)
                if args.preview_turns_json is not None else None)
        else:
            result = verify_party_edit(_json(args.receipt_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
