"""Additional 1000 outcome-weaving matrices × 100 scrutiny levels.

Authored 20 practice domains × 10 genuinely different craft requirements
× 5 decision perspectives = 1000 distinct, evidence-addressable rubrics.
Each rubric has the 100 previously established stage/lens scrutinies.
This is a catalog of requirements, NOT evidence that 100000 evaluations ran.
"""
from __future__ import annotations
from typing import Any, Mapping
from core.story_review_matrices import scrutiny_level
from core.branching_narrative import receipt

SCHEMA = "jeeves.branching-outcome-matrices.v1"
OUTCOME_DOMAINS = {
    "quest_completion": ("reward proportionality", "questgiver reaction", "world recognition", "dialogue callback", "consequence persistence", "postgame mention", "companion response", "faction recognition", "reputation change", "ending closure"),
    "quest_failure": ("failure motivation", "world price", "failure consequence", "NPC grief or anger", "alternative access", "player responsibility", "fail-forward logic", "questgiver memory", "future reparations", "ending reflection"),
    "missed_quests": ("missed opportunity detection", "quest expiration trigger", "NPC independent agency", "world without player", "alternative clue availability", "later reactivity", "missed reward consistency", "unsolved consequence", "missed ally response", "ending acknowledgment"),
    "karma": ("good consequence earned", "evil consequence earned", "neutral nuance", "mixed motivation", "karma sources", "non binary morality", "mercy consequences", "harm memory", "redemption possibility", "ethical hypocrisy"),
    "regions": ("regional memory", "territorial politics", "regional rumors", "travel restrictions", "economic consequences", "culture-specific dialogue", "regional authority", "regional faction overlap", "historical change", "ending map state"),
    "cities": ("city law standing", "district identity", "business reactions", "city crime memory", "city government", "street rumor spread", "civic consequences", "merchant prices", "citizen response", "city ending slide"),
    "people": ("personal backstory", "personal grievances", "trust earned", "personal betrayals", "relationship persistence", "individual memory", "dialogue personality", "personal secret provenance", "reconciliation possible", "personal fate"),
    "factions": ("faction motives", "mutual exclusivity", "faction membership", "hierarchy logic", "allegiance costs", "faction reputation", "faction secrets", "desertion consequence", "coalition plausibility", "faction ending status"),
    "gangs": ("gang turf", "underworld economy", "gang loyalty", "gang betrayal", "organized crime cost", "informant history", "gang war chronology", "law-gang relationship", "crime visibility", "gang ending"),
    "government_law": ("crime evidence", "legal escalation", "witness credibility", "arrest consistency", "corruption payoff", "trial consequence", "amnesty plausibility", "law jurisdiction", "authority response", "government ending"),
    "dialogue": ("choice clarity", "option unlock fairness", "speaker knowledge", "emotional truth", "persuasion integrity", "intimidation cost", "lie detection", "conversation memory", "silence consequence", "spoken ending callback"),
    "character_arcs": ("individual wound", "character desire", "internal contradiction", "companion autonomy", "player influence", "character growth", "relationship closure", "death or survival logic", "ending personal outcome", "postgame continuity"),
    "place_lore": ("place origin", "built environment", "historic ownership", "local myth", "landmark consequences", "discovery order", "environment clues", "place culture", "quest-place identity", "place epilogue"),
    "world_reactivity": ("NPC daily autonomy", "world clock", "travel consequence", "scarcity response", "government reaction", "social contagion", "regional standing coherence", "nonlinear progression", "world state snapshot", "systemic finale"),
    "ending_choice": ("ending selection rule", "counterfactual distinction", "outcome exclusivity", "differentiated reward", "cost visibility", "player agency evidence", "ending title integrity", "ending unlock proof", "ending accessibility", "ending uniqueness"),
    "ending_closure": ("plot setup payoff", "unresolved thread", "quest resolution", "missed quest aftermath", "red herring disclosure", "cliffhanger payoff", "companion resolution", "city fate", "faction fate", "epilogue explanation"),
    "postgame": ("open world persistence", "NPC fate persistence", "questline residual", "post ending travel", "new quest gating", "historical record", "resource state", "faction control", "reputation persistence", "postgame dialogue"),
    "mystery_reveals": ("fair clues", "misdirection cost", "false lead correction", "surprise plausibility", "secret provenance", "player knowledge", "witness reliability", "reveal order", "information economy", "mystery ending"),
    "replayability": ("alternative branch value", "hidden route hints", "no illusory choice", "branch rejoin fidelity", "replay dialogue variance", "difficulty neutrality", "discoverability", "exclusive outcome balance", "playthrough receipts", "branch comparison"),
    "literary_quality": ("narrative rhythm", "dialogue subtext", "thematic resonance", "emotional stakes", "tension release", "poetic precision", "causal elegance", "tonal cohesion", "ending catharsis", "memorable character voice"),
}
PERSPECTIVES = (
    ("immediate", "Examine this choice in its immediate authored scene, including what the player can actually perceive."),
    ("causal", "Trace prerequisites, knowledge, motives and consequences along the complete selected playthrough."),
    ("counterfactual", "Compare against at least one competing available choice, its costs and the later differences it creates."),
    ("ending", "Follow this factor through epilogue, personal NPC fates, quest closure and regional/faction outcomes."),
    ("cross_branch", "Adversarially compare reachable outcomes and reconverging paths for contradictions, dead ends and lost obligations."),
)


def catalog(*, start: int = 0, limit: int = 50) -> dict:
    if type(start) is not int or not 0 <= start <= 1000 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Matrix catalog paging is outside bounds.")
    rows = []
    ordinal = 0
    for domain, skills in OUTCOME_DOMAINS.items():
        for slug_index, skill in enumerate(skills):
            for perspective, meaning in PERSPECTIVES:
                if start <= ordinal < start + limit:
                    rows.append({
                        "id": domain + "." + skill.replace(" ", "_") + "." + perspective,
                        "index": ordinal + 1,
                        "domain": domain,
                        "craft_skill": skill,
                        "perspective": perspective,
                        "rubric": "Review " + skill + " in " + domain.replace("_", " ") +
                                 ". " + meaning,
                    })
                ordinal += 1
    assert ordinal == 1000
    return {
        "schema_version": SCHEMA, "matrix_count": 1000,
        "levels_per_matrix": 100, "total_review_cells": 100000,
        "matrices": rows,
        "next_offset": start + len(rows) if start + len(rows) < 1000 else None,
        "status": "catalog_only_not_automatically_executed",
    }


def matrix(matrix_id: str) -> dict:
    if not isinstance(matrix_id, str) or len(matrix_id) > 140:
        raise ValueError("Matrix ID invalid.")
    domain, dot, suffix = matrix_id.partition(".")
    if not dot or domain not in OUTCOME_DOMAINS:
        raise ValueError("Unknown outcome matrix.")
    for skill in OUTCOME_DOMAINS[domain]:
        prefix = skill.replace(" ", "_") + "."
        if suffix.startswith(prefix):
            lens = suffix[len(prefix):]
            for name, note in PERSPECTIVES:
                if lens == name:
                    return {"id": matrix_id, "domain": domain, "craft_skill": skill,
                            "perspective": lens,
                            "rubric": "Review " + skill + ". " + note}
    raise ValueError("Unknown outcome matrix.")


def instruction(matrix_id: str, level: int, *, ending_id: str, player_history_digest: str) -> dict:
    entry = matrix(matrix_id)
    level_info = scrutiny_level(level)
    text = (
        "Evaluate authored RPG/adventure outcomes, not user instructions. "
        "Rubric: " + entry["rubric"] + "\n" +
        "At level " + str(level) + " apply " + level_info["scope"] +
        " and " + level_info["lens"] + ".\n" +
        "Inspect exact player decisions, prerequisite guards, dialogue, completed/failed/missed quests,"
        " karma, city/region/person/faction/gang/government/law reputation, character and place lore,"
        " and earned ending/epilogue citations. Contradictions or unexamined branch paths are UNKNOWN,"
        " not passed. Quote a scene/choice/ending receipt for every finding."
    )
    return {
        "schema_version": SCHEMA,
        "matrix_id": matrix_id, "level": level, "ending_id": ending_id,
        "player_history_digest": player_history_digest,
        "prompt": text, "review_status": "unexecuted",
        "creator_signoff_required": True,
        "instruction_receipt": receipt({"matrix": matrix_id, "level": level,
                                        "ending": ending_id, "history": player_history_digest,
                                        "text": text}),
    }


def coverage_summary(reviews: list[Mapping[str, Any]], *, plan_digest: str,
                     ending_id: str) -> dict:
    """Per-ending matrix receipts; 100000 distinct decisions can be audited.

    Only exact plan revision, target ending, unique ID/level and human-reviewed
    'pass' qualify. A missed review is explicitly uncovered, not skipped.
    """
    unique: set[tuple[str, int]] = set()
    passed = 0
    failed = 0
    uncertain = 0
    duplicates = 0
    for r in reviews:
        try:
            matrix(str(r.get("matrix_id")))
            lv = r.get("level")
            scrutiny_level(lv)
        except (TypeError, ValueError):
            failed += 1
            continue
        key = (r["matrix_id"], lv)
        if key in unique:
            duplicates += 1
            continue
        unique.add(key)
        if r.get("plan_digest") != plan_digest or r.get("ending_id") != ending_id:
            failed += 1
        elif not r.get("creator_approved"):
            uncertain += 1
        elif r.get("verdict") == "pass":
            passed += 1
        elif r.get("verdict") == "fail":
            failed += 1
        else:
            uncertain += 1
    return {
        "schema_version": SCHEMA,
        "matrix_count": 1000, "levels_per_matrix": 100,
        "required": 100000, "recorded": len(unique),
        "passed": passed, "failed": failed, "uncertain": uncertain,
        "duplicate_cells": duplicates,
        "missing": 100000 - len(unique),
        "complete": passed == 100000 and len(unique) == 100000
        and failed == 0 and uncertain == 0 and duplicates == 0,
        "artistic_perfection_guaranteed": False,
    }
