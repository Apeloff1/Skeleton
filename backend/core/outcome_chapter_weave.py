"""Cross-authority narrative weave checks: conditional graph ↔ chapter canon.

A branching outcome engine must not form a parallel, contradictory history.
This audit references existing saved chapter, scene, plot highlights, voice/face
registries and lineage, and checks that authored choice scripts, characters
and locations actually exist in the studio. It reports incomplete material
rather than pretending the plan is ready to ship.
"""
from __future__ import annotations
from typing import Any, Mapping, Sequence

from core.chapter_continuity import MAX_CHAPTERS, MAX_SCENES
from core.branching_narrative import receipt

SCHEMA = "jeeves.outcome-chapter-weave.v1"


def audit_chapter_weave(
    plan: Mapping[str, Any],
    chapters: Sequence[Mapping[str, Any]],
    scenes: Sequence[Mapping[str, Any]],
    *, complete_source: bool,
) -> dict:
    if len(chapters) > MAX_CHAPTERS or len(scenes) > MAX_SCENES:
        raise ValueError("A malformed canonical chapter inventory exceeds bounds.")
    chapter_map = {}
    scene_map = {}
    violations: list[dict] = []
    total = 0

    def issue(code: str, reference: str, detail: str):
        nonlocal total
        total += 1
        if len(violations) < 150:
            violations.append({"code": code, "reference": reference, "detail": detail})

    for c in chapters:
        num = c.get("chapter")
        if type(num) is not int or num < 1 or num > MAX_CHAPTERS or num in chapter_map:
            issue("bad_chapter_coordinate", str(num), "Duplicate or malformed chapter.")
            continue
        chapter_map[num] = c
    for s in scenes:
        num = s.get("scene")
        if type(num) is not int or num < 1 or num > MAX_SCENES or num in scene_map:
            issue("bad_scene_coordinate", str(num), "Duplicate or malformed scene.")
            continue
        scene_map[num] = s
    bound_nodes = 0
    character_arcs = set()
    place_arcs = set()
    for node in plan["nodes"].values():
        ref = node["id"]
        scene = scene_map.get(node["scene"])
        chapter = chapter_map.get(node["chapter"])
        if not scene:
            issue("scene_not_authored", ref, "Decision belongs to no saved canonical scene.")
            continue
        if not chapter:
            issue("chapter_not_authored", ref, "Decision chapter lacks canonical notes.")
            continue
        if scene.get("chapter") != node["chapter"] or scene.get("act") != node["act"]:
            issue("scene_chronology_mismatch", ref, "Decision node and saved script disagree on act/chapter.")
        if (scene.get("chapter_digest") != chapter.get("digest")
            or scene.get("chapter_revision") != chapter.get("revision")):
            issue("stale_chapter_context", ref, "This scene references superseded chapter notes.")
        script = scene.get("text", "")
        if node["text"] not in script:
            issue("choice_script_unbound", ref,
                  "Canonical scene script does not include the referenced decision dialogue.")
        anchors = {p.get("id"): p.get("anchor") for p in scene.get("plot_points", [])}
        for point in node["plot_points"]:
            if anchors.get(point["id"]) != point["anchor"]:
                issue("plot_anchor_mismatch", ref, "Choice anchor is missing or differs from canonical script.")
        if node["speaker"]:
            actor = node["speaker"]
            character_arcs.add(actor)
            if actor not in scene.get("characters", []):
                issue("speaker_unwitnessed", ref, "Speaker absent from canonical participants.")
            if actor not in chapter.get("voice_cast", {}) or actor not in chapter.get("face_cast", {}):
                issue("actor_identity_unpinned", ref, "Speaker voice and face not pinned in chapter.")
        if node["place"]:
            place_arcs.add(node["place"])
            if not plan["places"][node["place"]].get("history"):
                issue("place_lore_missing", ref, "Place has no authored history.")
        if scene.get("status") != "approved_for_production":
            issue("scene_unapproved", ref, "Decision is not bound to an approved scene.")
        if scene.get("digest") and scene.get("status") == "approved_for_production":
            bound_nodes += 1
    for char_id, character in plan["characters"].items():
        if character["source_scene"] not in scene_map:
            issue("character_origin_not_authored", char_id,
                  "Character backstory does not reference an authored canonical scene.")
        if char_id in character_arcs and not any(
            char_id in e.get("character_conclusions", {}) for e in plan["endings"].values()
        ):
            issue("character_without_fate", char_id, "No authored ending concludes the NPC arc.")
    for place_id, location in plan["places"].items():
        if location["source_scene"] not in scene_map:
            issue("place_origin_not_authored", place_id,
                  "Place history lacks a cited canonical scene.")
        if place_id in place_arcs and not any(
            place_id in e.get("place_conclusions", {}) for e in plan["endings"].values()
        ):
            issue("place_without_fate", place_id, "No authored ending records this place's fate.")

    audit = {
        "schema_version": SCHEMA, "plan_digest": plan["source_digest"],
        "scanned_chapters": len(chapter_map), "scanned_scenes": len(scene_map),
        "graph_nodes": len(plan["nodes"]), "confirmed_approved_nodes": bound_nodes,
        "complete_source": bool(complete_source), "issue_count": total,
        "issues": violations,
        "canon_weave_ready": bool(complete_source) and total == 0
        and bound_nodes == len(plan["nodes"]),
        "guaranteed_narrative_quality": False,
    }
    audit["receipt_digest"] = receipt(audit)
    return audit
