"""Transactional, digest-fenced editing of authored evacuation NPC contracts.

Edits operate on a deep copy, revalidate the entire canonical source and
optionally replay the actual authored gameplay before publishing a new source.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_evacuation import (
    MAX_BYTES, _bounded, demo_actions, normalize_evacuation,
    original_evacuation, simulate_evacuation,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _object

MAX_EDITS = 16
EDIT_FIELDS = frozenset({"health", "available_from", "expires_at", "reward"})


def edit_evacuation(source: Any, edits: Any, expected_digest: Any,
                    *, preview_actions: Any = None) -> dict[str, Any]:
    original = normalize_evacuation(source)
    before = dig(original)
    if type(expected_digest) is not str or expected_digest != before:
        raise SceneTravelError("evacuation author source digest mismatch")
    if type(edits) is not list or not 1 <= len(edits) <= MAX_EDITS:
        raise SceneTravelError("evacuation author requires 1..16 edits")
    working = copy.deepcopy(original)
    touched: set[str] = set()
    for raw in edits:
        edit = _object(raw, {"npc_id", "changes"}, "evacuation edit")
        npc_id = _id(edit["npc_id"], "edited NPC")
        changes = edit["changes"]
        if (npc_id in touched or type(changes) is not dict
                or not changes or not set(changes) <= EDIT_FIELDS):
            raise SceneTravelError("invalid or duplicate evacuation NPC edit")
        touched.add(npc_id)
        npc = next((n for n in working["npcs"] if n["id"] == npc_id), None)
        if npc is None:
            raise SceneTravelError("cannot edit a missing NPC")
        npc.update(changes)
    revised = normalize_evacuation(working)
    after = dig(revised)
    if after == before:
        raise SceneTravelError("evacuation edit made no source change")
    preview = None
    if preview_actions is not None:
        if type(preview_actions) is not list:
            raise SceneTravelError("invalid evacuation author preview")
        played = simulate_evacuation(revised, preview_actions)
        preview = {
            "state_digest": played["state_digest"],
            "phase": played["state"]["phase"],
            "tick": played["state"]["tick"],
            "reward": played["state"]["reward"],
        }
    result = {
        "schema_version": "skeleton.scene_evacuation_author.v1",
        "previous_source_digest": before, "source_digest": after,
        "source": revised, "edited_npcs": sorted(touched),
        "preview": preview,
    }
    result["receipt"] = dig(result)
    _bounded(result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-evacuation-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    edit = sub.add_parser("edit")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--edits-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    edit.add_argument("--preview-json")
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source = original_evacuation()
            result = edit_evacuation(
                source, [{"npc_id": "watch_keeper", "changes": {"reward": 21}}],
                dig(normalize_evacuation(source)), preview_actions=demo_actions(),
            )
        else:
            parse = lambda raw: _strict_json(raw, "evacuation author", max_bytes=MAX_BYTES)
            result = edit_evacuation(
                parse(args.source_json), parse(args.edits_json),
                args.expected_digest,
                preview_actions=(parse(args.preview_json)
                                 if args.preview_json is not None else None),
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
