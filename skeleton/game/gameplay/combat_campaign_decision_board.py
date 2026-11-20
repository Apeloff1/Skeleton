"""Read-only human combat decision board with canonical outcome previews.

Every preview uses the same replayable campaign reducer as interactive play.
A preview is not a recommendation, source signature or claim of victory.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign import original_campaign
from skeleton.game.gameplay.combat_campaign_player import (
    _advance, _bounded, demo_player_campaign, export_player_campaign,
    new_player_campaign, verify_player_campaign,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _active_actor, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_decision_board.v1"
MAX_CHOICES = 16


def decision_board(session: Any, *, max_choices: int = 16,
                   expected_source_digest: str | None = None) -> dict[str, Any]:
    """Preview actual hero turns without changing the verified input checkpoint."""
    if type(max_choices) is not int or not 1 <= max_choices <= MAX_CHOICES:
        raise CombatSessionError("invalid campaign decision preview budget")
    current = verify_player_campaign(session)
    if expected_source_digest is not None and (
        type(expected_source_digest) is not str or
        expected_source_digest != current["source_digest"]
    ):
        raise CombatSessionError("stale campaign decision source lease")
    state, source = current["state"], current["source"]
    actions: list[dict[str, Any]] = []
    if state["phase"] == "active":
        combat = state["combat"]
        actor_id, _ = _active_actor(combat["scenario"], combat["state"])
        if actor_id != source["hero_id"]:
            raise CombatSessionError("campaign decision is not a hero turn")
        actions.extend([
            {"kind": "attack", "actor_id": actor_id, "target_id": actor["id"]}
            for actor in combat["scenario"]["actors"]
            if actor["team"] != source["hero_team"]
            and combat["state"]["actors"][actor["id"]]["hp"] > 0
        ])
        actions.extend([
            {"kind": "guard", "actor_id": actor_id},
            {"kind": "rest", "actor_id": actor_id},
        ])
    actions.sort(key=lambda action: json.dumps(action, sort_keys=True))
    previews = []
    for action in actions[:max_choices]:
        following = _advance(current, action)
        after = following["state"]
        previews.append({
            "action": action,
            "state_digest": following["state_digest"],
            "save_digest": dig(following["save"]),
            "hero_hp": after["hero_hp"],
            "currency": after["currency"],
            "earned_currency_delta": after["currency"] - state["currency"],
            "phase": after["phase"],
            "next_encounter": after["next_index"],
            "player_turns": after["player_turns"],
            "combat_phase": after["combat"]["state"]["phase"],
        })
    result = {
        "schema_version": SCHEMA,
        "source_digest": current["source_digest"],
        "state_digest": current["state_digest"],
        "save_digest": dig(current["save"]),
        "phase": state["phase"],
        "hero_id": source["hero_id"],
        "hero_hp": state["hero_hp"],
        "currency": state["currency"],
        "encounter": state["next_index"],
        "player_turns": state["player_turns"],
        "choices": previews,
        "choices_truncated": len(actions) > max_choices,
        "preview_kind": "canonical_counterfactual_not_guaranteed_win",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-campaign-board")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    p = sub.add_parser("inspect")
    p.add_argument("--session-json", required=True)
    p.add_argument("--max-choices", type=int, default=16)
    p.add_argument("--expected-source-digest")
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = decision_board(new_player_campaign(original_campaign()))
        else:
            result = decision_board(
                _parse_json(args.session_json, "campaign checkpoint"),
                max_choices=args.max_choices,
                expected_source_digest=args.expected_source_digest,
            )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
