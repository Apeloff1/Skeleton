"""No dual canon: RPG choice scenes, NPCs and place lore bind to Chapter Studio."""
import pytest
from core.branching_narrative import validate_plan
from core.outcome_chapter_weave import audit_chapter_weave
from test_branching_narrative import plan


def canon(compiled):
    chapters = [{
        "chapter": 1, "revision": 3, "digest": "chapter-receipt",
        "voice_cast": {"aria": "voice-1"}, "face_cast": {"aria": "face-1"},
    }]
    scenes = [{
        "scene": node["scene"], "chapter": node["chapter"], "act": node["act"],
        "text": node["text"], "plot_points": node["plot_points"],
        "chapter_digest": "chapter-receipt", "chapter_revision": 3,
        "characters": ["aria"], "digest": "scene-" + str(node["scene"]),
        "status": "approved_for_production",
    } for node in compiled["nodes"].values()]
    return chapters, scenes


def code(report):
    return {i["code"] for i in report["issues"]}


def test_cross_canon_success_uses_exact_script_identity_and_unmodified_character_face_voice():
    compiled = validate_plan(plan())
    chapters, scenes = canon(compiled)
    result = audit_chapter_weave(compiled, chapters, scenes, complete_source=True)
    assert result["canon_weave_ready"]
    assert result["confirmed_approved_nodes"] == 2
    assert result["issue_count"] == 0
    assert len(result["receipt_digest"]) == 64


def test_missing_scene_or_incomplete_history_never_certifies_branch_quality():
    compiled = validate_plan(plan())
    chapters, scenes = canon(compiled)
    report = audit_chapter_weave(compiled, chapters, scenes[:1], complete_source=True)
    assert not report["canon_weave_ready"]
    assert "scene_not_authored" in code(report)
    report = audit_chapter_weave(compiled, chapters, scenes, complete_source=False)
    assert not report["canon_weave_ready"]


def test_production_must_bind_plot_highlights_speakers_and_correct_chapter_revisions():
    compiled = validate_plan(plan())
    chapters, scenes = canon(compiled)
    scenes[0]["plot_points"][0]["anchor"] = "edited-out old phrase"
    scenes[0]["characters"] = []
    scenes[0]["chapter_digest"] = "stale-history"
    scenes[0]["text"] = "A different author rewrote the script"
    report = audit_chapter_weave(compiled, chapters, scenes, complete_source=True)
    assert {"plot_anchor_mismatch", "speaker_unwitnessed",
            "stale_chapter_context", "choice_script_unbound"} <= code(report)


def test_facial_or_voice_identity_absent_and_scenes_unapproved_are_blocked():
    compiled = validate_plan(plan())
    chapters, scenes = canon(compiled)
    chapters[0]["face_cast"] = {}
    scenes[1]["status"] = "draft"
    result = audit_chapter_weave(compiled, chapters, scenes, complete_source=True)
    assert not result["canon_weave_ready"]
    assert "actor_identity_unpinned" in code(result)
    assert "scene_unapproved" in code(result)


def test_character_and_place_backstories_must_have_real_source_scenes():
    original = plan()
    original["characters"][0]["source_scene"] = 9999
    original["places"][0]["source_scene"] = 9998
    compiled = validate_plan(original)
    chapters, scenes = canon(compiled)
    report = audit_chapter_weave(compiled, chapters, scenes, complete_source=True)
    assert "character_origin_not_authored" in code(report)
    assert "place_origin_not_authored" in code(report)
