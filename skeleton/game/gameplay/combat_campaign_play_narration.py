"""Accessible turn narration for player-controlled canonical campaigns.

Uses the same verified damage/guard/rest caption derivation as the autoplay
campaign, while distinguishing player decisions from deterministic opponent
turns and including an unfinished encounter's actual checkpoint.
"""
from __future__ import annotations

from typing import Any

from skeleton.game.gameplay.combat_campaign_captions import _caption, _json
from skeleton.game.gameplay.combat_campaign_interactive import verify_interactive
from skeleton.game.gameplay.combat_inspector import inspect_session
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError, _object

SCHEMA = "skeleton.combat_campaign_play_narration.v1"
MAX_TURNS = 128


def narrate_interactive(raw: Any) -> dict[str, Any]:
    session = verify_interactive(raw)
    state = session["state"]
    hero = session["source"]["hero_id"]
    all_combats = [
        (index, entry["encounter_id"], entry["combat"], entry["reward"], True)
        for index, entry in enumerate(state["encounters"])
    ]
    if state["current_combat"] is not None:
        all_combats.append((
            state["encounter_index"],
            state["current_combat"]["scenario"]["encounter_id"],
            state["current_combat"], 0, False,
        ))
    captions: list[dict[str, Any]] = []
    chapters: list[dict[str, Any]] = []
    hero_turns = 0
    opponent_turns = 0
    for index, encounter_id, combat, reward, complete in all_combats:
        inspected = inspect_session(combat)
        first = len(captions)
        for turn in inspected["timeline"]:
            action = turn["action"]
            caption, damage, healing, knockout = _caption(
                action, turn["changes"], turn["phase"], turn["winner"],
            )
            is_player = action["actor_id"] == hero
            hero_turns += int(is_player)
            opponent_turns += int(not is_player)
            captions.append({
                "sequence": len(captions),
                "encounter_index": index,
                "encounter_id": encounter_id,
                "turn": turn["turn"],
                "speaker": "player" if is_player else "opponent",
                "actor_id": action["actor_id"],
                "target_id": action.get("target_id"),
                "action": action["kind"],
                "damage": damage,
                "healing": healing,
                "knockout": knockout,
                "caption": caption,
                "after_digest": turn["after_digest"],
                "turn_receipt": turn["receipt"],
            })
            if len(captions) > MAX_TURNS:
                raise CombatSessionError("interactive narration turn budget exceeded")
        chapters.append({
            "encounter_index": index, "encounter_id": encounter_id,
            "first_caption": first, "caption_count": len(captions) - first,
            "completed": complete, "reward": reward,
            "phase": inspected["phase"], "winner": inspected["winner"],
            "state_digest": inspected["state_digest"],
        })
    result = {
        "schema_version": SCHEMA,
        "session": session,
        "manifest": {
            "world_id": session["source"]["world_id"],
            "campaign_id": session["source"]["campaign_id"],
            "source_digest": session["source_digest"],
            "session_digest": dig(session),
            "phase": state["phase"],
            "hero_hp": state["hero_hp"],
            "currency": state["currency"],
            "completed_encounters": len(state["encounters"]),
            "caption_count": len(captions),
            "player_turns": hero_turns,
            "opponent_turns": opponent_turns,
            "captions_digest": dig(captions),
        },
        "chapters": chapters,
        "captions": captions,
        "claim": "canonical_replay_integrity_not_authorship",
    }
    result["receipt"] = dig(result)
    _json(result)
    return result


def verify_interactive_narration(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "session", "manifest", "chapters",
        "captions", "claim", "receipt",
    }, "interactive narration")
    if (obj["schema_version"] != SCHEMA
            or obj["claim"] != "canonical_replay_integrity_not_authorship"):
        raise CombatSessionError("unsupported interactive narration schema")
    _json(obj)
    expected = narrate_interactive(obj["session"])
    if expected != obj:
        raise CombatSessionError("interactive narration or replay mismatch")
    return expected
