"""Transactional offline authoring and playable previews for market leagues.

Rules are editable only before attempts exist. Each edit requires the exact
source-bound league digest; a preview plays a real verified party checkpoint,
scores it with the proposed rules and checks portable export.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _json
from skeleton.game.gameplay.scene_market_party import original_party, simulate_party
from skeleton.game.gameplay.scene_market_party_league import (
    export_league, import_league, new_league, normalize_rules,
    rank_league, record_attempt, verify_league,
)
from skeleton.game.gameplay.scene_tile_walk import _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_party_league_edit.v1"
PREVIEW = "skeleton.scene_market_party_league_preview.v1"
MAX_BYTES = 2 * 1024 * 1024


def _limit(value: Any) -> None:
    _bounded(value, MAX_BYTES)


def edit_league(league: Any, patch: Any,
                *, expected_state_digest: str) -> dict[str, Any]:
    current = verify_league(league)
    if current["revision"] or current["entries"] or current["journal"]:
        raise SceneTravelError("cannot edit cooperative league after scored attempts")
    if type(expected_state_digest) is not str or expected_state_digest != current["state_digest"]:
        raise SceneTravelError("stale cooperative league author lease")
    _limit(patch)
    if type(patch) is not dict or not patch or not set(patch).issubset(current["rules"]):
        raise SceneTravelError("invalid cooperative league rule patch")
    updated = dict(current["rules"])
    updated.update(patch)
    rules = normalize_rules(updated)
    if rules == current["rules"]:
        raise SceneTravelError("cooperative league rule edit has no effect")
    authored = new_league(current["source"], rules)
    receipt = {"schema_version": SCHEMA,
               "source_digest": current["source_digest"],
               "before_state_digest": current["state_digest"],
               "before_rules_digest": dig(current["rules"]),
               "after_rules_digest": dig(authored["rules"]),
               "patch": dict(patch), "league": authored,
               "qualification": "offline_scoring_edit_not_retroactive_awards"}
    receipt["checksum"] = dig(receipt)
    _limit(receipt)
    return receipt


def verify_league_edit(original: Any, receipt: Any) -> dict[str, Any]:
    _limit(receipt)
    if type(receipt) is not dict or receipt.get("schema_version") != SCHEMA:
        raise SceneTravelError("invalid cooperative league edit receipt")
    expected = edit_league(original, receipt.get("patch"),
                           expected_state_digest=receipt.get("before_state_digest"))
    if receipt != expected:
        raise SceneTravelError("cooperative league edit receipt altered")
    return expected


def preview_league(league: Any, checkpoint: Any) -> dict[str, Any]:
    original = verify_league(league)
    if original["revision"] != 0:
        raise SceneTravelError("preview requires an unscored cooperative league")
    recorded = record_attempt(original, "author-preview", checkpoint,
                              expected_revision=0)
    portable = export_league(recorded)
    restored = import_league(json.loads(json.dumps(portable)))
    if restored != recorded:
        raise SceneTravelError("cooperative league preview export mismatch")
    ranking = rank_league(restored)
    if (len(ranking["ranking"]) != 1
            or ranking["ranking"][0]["party_state_digest"]
            != checkpoint["state_digest"]):
        raise SceneTravelError("cooperative league preview replay mismatch")
    result = {"schema_version": PREVIEW,
              "source_digest": original["source_digest"],
              "authored_rules_digest": dig(original["rules"]),
              "checkpoint_state_digest": checkpoint["state_digest"],
              "ranking": ranking,
              "export_checksum": portable["checksum"],
              "qualification": "offline_preview_not_identity_attestation"}
    result["checksum"] = dig(result)
    _limit(result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton scene-market-party-league-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    edit = sub.add_parser("edit")
    edit.add_argument("--league-json", required=True)
    edit.add_argument("--patch-json", required=True)
    edit.add_argument("--expected-state-digest", required=True)
    verify = sub.add_parser("verify-edit")
    verify.add_argument("--original-json", required=True)
    verify.add_argument("--receipt-json", required=True)
    preview = sub.add_parser("preview")
    preview.add_argument("--league-json", required=True)
    preview.add_argument("--checkpoint-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, turns = original_party()
            league = new_league(source)
            authored = edit_league(league, {"credits": 4},
                                  expected_state_digest=league["state_digest"])
            verify_league_edit(league, authored)
            result = preview_league(authored["league"], simulate_party(source, turns))
        elif args.command == "edit":
            result = edit_league(_json(args.league_json), _json(args.patch_json),
                                 expected_state_digest=args.expected_state_digest)
        elif args.command == "verify-edit":
            result = verify_league_edit(_json(args.original_json),
                                        _json(args.receipt_json))
        else:
            result = preview_league(_json(args.league_json),
                                    _json(args.checkpoint_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
