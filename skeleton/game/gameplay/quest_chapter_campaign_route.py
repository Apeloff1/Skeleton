"""Deterministic playable chapter-campaign completion planner.

Composes independently bounded canonical quest routes. Each accepted action
passes through the real campaign runtime, so chapter unlocks, rewards and
portable saves cannot be manufactured by a search result. Exhaustion is
inconclusive; checksums detect corruption but do not authenticate authors.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import MAX_BYTES, _size
from skeleton.game.gameplay.expedition_quest_route import (
    MAX_DEPTH, MAX_STATES, plan_quest, verify_plan,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.quest_chapter_campaign import (
    MAX_ACTIONS, _step, demo_campaign_actions, export_campaign,
    import_campaign, new_campaign, original_campaign, resume_campaign,
    simulate_campaign, verify_campaign,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _object, _parse_json,
)

SCHEMA = "skeleton.quest_chapter_campaign_route.v1"


def _limits(max_states: int, max_depth: int) -> None:
    if type(max_states) is not int or not 1 <= max_states <= MAX_STATES:
        raise CombatSessionError("invalid chapter route state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise CombatSessionError("invalid chapter route depth budget")


def _receipt(start: dict[str, Any], status: str,
             actions: list[dict[str, Any]], chapters: list[dict[str, Any]],
             explored: int, exhausted: bool, final: dict[str, Any] | None,
             max_states: int, max_depth: int) -> dict[str, Any]:
    record = {
        "schema_version": SCHEMA, "status": status,
        "source_digest": start["source_digest"],
        "initial_state_digest": start["state_digest"],
        "final_state_digest": final["state_digest"] if final is not None else None,
        "portable_checksum": (
            export_campaign(final)["checksum"] if final is not None else None
        ),
        "actions": actions, "chapters": chapters,
        "explored": explored, "budget_exhausted": exhausted,
        "max_states": max_states, "max_depth": max_depth,
    }
    record["checksum"] = dig(record)
    _size(record, MAX_BYTES)
    return record


def plan_campaign(source: Any = None, *, session: Any = None,
                  max_states: int = 256, max_depth: int = 24) -> dict[str, Any]:
    """Plan all remaining chapters, never claiming success without replay."""
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one campaign source or checkpoint")
    _limits(max_states, max_depth)
    start = new_campaign(source) if session is None else verify_campaign(session)
    current = start
    actions: list[dict[str, Any]] = []
    chapters: list[dict[str, Any]] = []
    explored = 0
    if current["state"]["phase"] != "active":
        won = current["state"]["phase"] == "won"
        return _receipt(
            start, "found" if won else "unreachable", actions, chapters,
            0, False, current if won else None, max_states, max_depth,
        )
    while current["state"]["phase"] == "active":
        index = current["state"]["chapter_index"]
        chapter = current["source"]["chapters"][index]
        quest = current["state"]["active_quest"]
        if quest["state"]["phase"] == "active":
            plan = plan_quest(
                session=quest, target_ending=chapter["required_ending"],
                max_states=max_states, max_depth=max_depth,
            )
            explored += plan["explored"]
            if plan["status"] != "found":
                return _receipt(
                    start, plan["status"], actions, chapters,
                    explored, plan["budget_exhausted"], None,
                    max_states, max_depth,
                )
            final_quest = verify_plan(plan, session=quest)
            if final_quest["state"]["ending"] != chapter["required_ending"]:
                raise CombatSessionError("chapter route ending mismatch")
            for quest_action in plan["actions"]:
                if len(start["journal"]) + len(actions) >= MAX_ACTIONS:
                    return _receipt(
                        start, "inconclusive", actions, chapters,
                        explored, True, None, max_states, max_depth,
                    )
                action = {"kind": "quest", "action": quest_action}
                current = _step(current, action)
                actions.append(current["journal"][-1]["action"])
            if current["state"]["active_quest"] != final_quest:
                raise CombatSessionError("chapter route canonical replay mismatch")
        elif quest["state"]["ending"] != chapter["required_ending"]:
            return _receipt(
                start, "unreachable", actions, chapters, explored,
                False, None, max_states, max_depth,
            )
        if len(start["journal"]) + len(actions) >= MAX_ACTIONS:
            return _receipt(
                start, "inconclusive", actions, chapters,
                explored, True, None, max_states, max_depth,
            )
        current = _step(current, {"kind": "advance"})
        actions.append(current["journal"][-1]["action"])
        record = current["state"]["history"][-1]
        if not record["accepted"]:
            raise CombatSessionError("campaign route did not earn chapter reward")
        chapters.append({
            "chapter_id": chapter["id"],
            "required_ending": chapter["required_ending"],
            "quest_state_digest": record["quest_state_digest"],
            "campaign_state_digest": current["state_digest"],
            "flags": list(current["state"]["flags"]),
        })
    if current["state"]["phase"] != "won":
        raise CombatSessionError("campaign route unexpectedly blocked")
    if import_campaign(export_campaign(current)) != current:
        raise CombatSessionError("campaign route portable replay mismatch")
    return _receipt(
        start, "found", actions, chapters, explored,
        False, current, max_states, max_depth,
    )


def verify_campaign_plan(payload: Any, *, source: Any = None,
                         session: Any = None) -> dict[str, Any]:
    """Recompute route decisions, verify every transition and portable export."""
    _size(payload, MAX_BYTES)
    if type(payload) is not dict:
        raise CombatSessionError("invalid campaign route receipt")
    required = {
        "schema_version", "status", "source_digest", "initial_state_digest",
        "final_state_digest", "portable_checksum", "actions", "chapters",
        "explored", "budget_exhausted", "max_states", "max_depth", "checksum",
    }
    if set(payload) != required or payload["schema_version"] != SCHEMA:
        raise CombatSessionError("invalid campaign route schema")
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one campaign source or checkpoint")
    _limits(payload["max_states"], payload["max_depth"])
    start = new_campaign(source) if session is None else verify_campaign(session)
    expected = plan_campaign(
        session=start, max_states=payload["max_states"],
        max_depth=payload["max_depth"],
    )
    if expected != payload:
        raise CombatSessionError("campaign route search receipt mismatch")
    if payload["status"] != "found":
        raise CombatSessionError("only completed routes have playable witnesses")
    final = resume_campaign(start, payload["actions"])
    if (final["state"]["phase"] != "won"
            or final["state_digest"] != payload["final_state_digest"]
            or export_campaign(final)["checksum"] != payload["portable_checksum"]):
        raise CombatSessionError("campaign route witness replay mismatch")
    return final


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-campaign-route")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--session-json")
    parser.add_argument("--max-states", type=int, default=256)
    parser.add_argument("--max-depth", type=int, default=24)
    parser.add_argument("--verify-json")
    args = parser.parse_args(list(argv))
    try:
        source = original_campaign() if args.demo else (
            _parse_json(args.source_json, "campaign source")
            if args.source_json is not None else None
        )
        saved = (
            _parse_json(args.session_json, "campaign checkpoint")
            if args.session_json is not None else None
        )
        if args.verify_json is None:
            result = plan_campaign(
                source, session=saved, max_states=args.max_states,
                max_depth=args.max_depth,
            )
        else:
            final = verify_campaign_plan(
                _parse_json(args.verify_json, "campaign route receipt"),
                source=source, session=saved,
            )
            result = {
                "ok": True, "phase": final["state"]["phase"],
                "state_digest": final["state_digest"],
                "portable_checksum": export_campaign(final)["checksum"],
            }
        _size(result, MAX_BYTES)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
