"""Spoiler-safe, receipt-bound player dialogue and creator guard diagnostics.

This is a projection of the canonical validated branching_narrative simulation.
Neither this view nor its hash can execute a choice or authorize a model/tool.
Player projections never serialize locked option dialogue, guards, branch targets,
unreached endings, NPC secrets, or omniscient background lore.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from core.branching_narrative import holds, receipt, simulate

SCHEMA = "jeeves.dialogue-projection.v1"
MAX_HISTORY_EXCERPT = 20
MAX_SCENE_TEXT = 5000


def _unmet(guard: Mapping[str, Any], state: Mapping[str, Any]) -> dict:
    """Editor-only, structured cause; never sent as player-facing copy."""
    kind = guard["op"]
    if holds(guard, state):
        return {"op": kind, "satisfied": True}
    if kind == "all":
        return {"op": "all", "satisfied": False, "missing": [
            _unmet(item, state) for item in guard["items"] if not holds(item, state)
        ]}
    if kind == "any":
        return {"op": "any", "satisfied": False, "alternatives": [
            _unmet(item, state) for item in guard["items"]
        ]}
    if kind == "not":
        return {"op": "not", "satisfied": False,
                "reason": "Forbidden prerequisite is currently true."}
    if kind == "quest":
        return {"op": "quest", "satisfied": False, "id": guard["id"],
                "expected": guard["state"],
                "actual": state["quests"].get(guard["id"], "unknown")}
    if kind in ("flag", "choice", "lore"):
        return {"op": kind, "satisfied": False, "id": guard["id"],
                "reason": "Required player discovery or historical choice is absent."}
    if kind == "meter":
        return {"op": "meter", "satisfied": False,
                "key": guard["key"], "comparison": guard["comparison"],
                "threshold": guard["value"],
                "actual": state["meters"].get(guard["key"], 0)}
    raise ValueError("Invalid prevalidated dialogue guard.")


def project_dialogue(plan: Mapping[str, Any], choices: Sequence[str],
                     *, creator_diagnostics: bool = False) -> dict:
    """Read-only replay to the current scene, bounded even for a long story.

    Only show actually unlocked player replies. Editor diagnostics are opt-in
    through a separately authorized route; no prompt or UI flag elevates them.
    """
    played = simulate(plan, choices)
    position = played["position"]
    current = plan["nodes"][position] if position else None
    unlocked = played["available_options"]
    visible = [
        {"id": row["id"], "label": row["label"], "dialogue": row["dialogue"]}
        for row in unlocked
    ]
    history = [
        {"scene": row["scene"], "speaker_id": row["character"],
         "choice_id": row["choice"], "receipt_digest": row["receipt_digest"]}
        for row in played["steps"][-MAX_HISTORY_EXCERPT:]
    ]
    script = current["text"] if current else ""
    result: dict[str, Any] = {
        "schema_version": SCHEMA,
        "plan_digest": plan["source_digest"],
        "branch_id": plan["branch_id"],
        "playthrough_receipt": played["receipt_digest"],
        "history_length": len(played["steps"]),
        "history_tail": history,
        "history_truncated": len(played["steps"]) > MAX_HISTORY_EXCERPT,
        "scene": current["scene"] if current else None,
        "speaker_id": current["speaker"] if current else None,
        "speaker_name": (
            plan["characters"][current["speaker"]]["name"]
            if current and current["speaker"] else None
        ),
        "place_id": current["place"] if current else None,
        "place_name": (
            plan["places"][current["place"]]["name"]
            if current and current["place"] else None
        ),
        "scene_text": script[:MAX_SCENE_TEXT],
        "scene_text_truncated": len(script) > MAX_SCENE_TEXT,
        "available_replies": visible,
        "ending_reached": bool(played["ending_id"]),
        "ending_accepted": bool(played["ending_accepted"]),
        "ending": (
            {"id": played["ending"]["id"],
             "title": played["ending"]["title"],
             "tone": played["ending"]["tone"],
             "epilogue": played["ending"]["epilogue"],
             "consequences": played["ending"]["consequences"],
             "character_conclusions": played["ending"]["character_conclusions"],
             "place_conclusions": played["ending"]["place_conclusions"],
             "quest_conclusions": played["ending"]["quest_conclusions"],
             "faction_conclusions": played["ending"]["faction_conclusions"],
             "selected_variants": played["ending_variants_selected"]}
            if played["ending"] else None
        ),
        "content_trust": "creator_authored_untrusted_not_model_instructions",
        "simulation_only": True,
    }
    if creator_diagnostics:
        locked = [
            {"id": option["id"], "label": option["label"],
             "unmet": _unmet(option["guard"], played["state"])}
            for option in current["options"]
            if not holds(option["guard"], played["state"])
        ] if current else []
        result["locked_choices"] = locked
        result["creator_diagnostics_only"] = True
        result["narrative_state"] = {
            "quests": played["state"]["quests"],
            "meters": played["state"]["meters"],
            "flags": played["state"]["flags"],
            "known_lore": played["state"]["known_lore"],
            "open_threads": played["unresolved_threads"],
        }
    result["projection_digest"] = receipt(result)
    return result
