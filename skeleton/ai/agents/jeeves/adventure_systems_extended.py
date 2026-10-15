"""Extended adventure systems: additional puzzle types, state machines, and fairness tooling.
Companion to adventure_game_capability. Data-only.
"""

from __future__ import annotations

from typing import Any


def multi_room_puzzle(theme: str, rooms_involved: int = 3) -> dict[str, Any]:
    return {
        "type": "multi_room",
        "theme": theme,
        "rooms_involved": rooms_involved,
        "steps": [
            "Clue discovered in room A (examine or dialogue)",
            "Item or state change acquired in room B",
            "Application in room C sets reward flag",
        ],
        "fairness": "Clue visible before item is required; failure feedback in each room",
        "hint_ladder": ["environmental change", "NPC remark", "in-character direct hint"],
    }


def sequence_puzzle(name: str, length: int = 4) -> dict[str, Any]:
    return {
        "type": "sequence",
        "name": name,
        "length": length,
        "reset_on_fail": True,
        "feedback": "Distinct audio/visual per correct step; clear fail state",
        "no_soft_lock": "Sequence can always be restarted; no consumable without backup",
    }


def dialogue_gated_puzzle(npc: str, flag: str) -> dict[str, Any]:
    return {
        "type": "dialogue_gated",
        "npc": npc,
        "required_flag": flag,
        "unlocks": "physical action or new exit",
        "note": "Information from dialogue is necessary but not sufficient; still requires observation",
    }


def inventory_state_machine(item_id: str, states: list[str]) -> dict[str, Any]:
    return {
        "item": item_id,
        "states": states,
        "transitions": [{"from": states[i], "to": states[i+1], "trigger": "use_or_combine"} for i in range(len(states)-1)],
        "visual_distinction": "Each state has unique examine text and sprite/silhouette change",
    }


def fairness_audit_checklist() -> list[str]:
    return [
        "Every critical-path puzzle has a visible clue before it blocks progress",
        "Failure produces readable feedback",
        "At least two hint levels exist",
        "No soft-locks on critical path",
        "Red herrings are clearly optional",
        "Item combinations are enumerated, not free-parsed",
        "Hotspots are adequately sized or highlighted on focus",
    ]
