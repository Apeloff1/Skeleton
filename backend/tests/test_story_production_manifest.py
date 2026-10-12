"""Whole-project story production: only real complete inventories qualify."""
from __future__ import annotations

from copy import deepcopy
from math import ceil

from core.chapter_continuity import chapter_for_act
from core.story_production_manifest import production_manifest


def chapter(n):
    return {
        "chapter": n, "revision": 1, "digest": "chapter:" + str(n),
        "voice_cast": {"aria": "voice_original"},
        "face_cast": {"aria": "face_scar_right"},
    }


def scene(n):
    act = ceil(n * 1000 / 9999)
    chapter_no = chapter_for_act(act)
    return {
        "scene": n, "act": act, "chapter": chapter_no,
        "chapter_revision": 1, "chapter_digest": "chapter:" + str(chapter_no),
        "digest": "scene:" + str(n),
        "status": "approved_for_production",
        "characters": ["aria"], "plot_points": [{"id": "point_" + str(n)}],
        "proof": {
            "status": "machine_checks_passed",
            "inspections_executed": 100000, "history_complete": True,
            "blocking_issues": [], "scene_digest": "scene:" + str(n),
            "chapter_digest": "chapter:" + str(chapter_no),
            "chapter_revision": 1,
            "predecessor_scene_digest": "scene:" + str(n - 1) if n > 1 else None,
            "receipt_digest": "receipt:" + str(n),
        },
    }


def test_empty_project_does_not_fabricate_completeness():
    m = production_manifest([], [])
    assert m["structural_ready"] is False
    assert m["coverage"]["scenes_expected"] == 9999
    assert m["coverage"]["chapters_expected"] == 100
    assert m["coverage"]["acts_expected"] == 1000
    assert m["missing_scenes_count"] == 9999
    assert m["missing_acts_count"] == 1000
    assert m["continuity_100_percent_guaranteed"] is False
    assert m["human_creative_quality_review_required"] is True


def test_structurally_complete_nine_thousand_nine_hundred_ninety_nine_scene_project():
    chapters = [chapter(i) for i in range(1, 101)]
    scenes = [scene(i) for i in range(1, 10000)]
    manifest = production_manifest(chapters, scenes)
    assert manifest["structural_ready"] is True
    assert manifest["coverage"]["structural_completion_pct"] == 100
    assert manifest["issue_count"] == 0
    assert manifest["missing_scenes_count"] == 0
    assert manifest["missing_acts_count"] == 0
    assert manifest["coverage"]["scenes_approved"] == 9999
    assert manifest["coverage"]["scenes_proofed"] == 9999
    assert manifest["coverage"]["scenes_plot_marked"] == 9999
    assert len(manifest["receipt_digest"]) == 64
    assert manifest["continuity_100_percent_guaranteed"] is False


def test_missing_scattered_scenes_and_chapters_cannot_be_hidden_by_high_counts():
    chapters = [chapter(i) for i in range(1, 100)]
    scenes = [scene(i) for i in range(1, 10000) if i != 5000]
    result = production_manifest(chapters, scenes)
    assert result["structural_ready"] is False
    assert result["missing_scenes_count"] == 1
    assert result["missing_scenes"] == [5000]
    assert result["missing_chapters"] == [100]
    assert result["issue_count"] > 0
    assert "broken_receipt_chain" in {x["kind"] for x in result["issues"]}


def test_tampered_proof_and_out_of_sequence_act_fail_closed():
    chapters = [chapter(1)]
    original = scene(1)
    altered = deepcopy(original)
    altered["proof"]["scene_digest"] = "false-receipt"
    altered["act"] = 999
    result = production_manifest(chapters, [altered])
    assert "proof_missing" in {x["kind"] for x in result["issues"]}
    assert "chapter_mismatch" in {x["kind"] for x in result["issues"]}


def test_voice_and_face_replacements_fail_even_with_all_scene_receipts():
    chapters = [chapter(1), chapter(2)]
    chapters[1]["voice_cast"] = {"aria": "replacement"}
    chapters[1]["face_cast"] = {"aria": "different_face"}
    result = production_manifest(chapters, [scene(1)])
    assert "voice_replacement" in {x["kind"] for x in result["issues"]}
    assert "face_replacement" in {x["kind"] for x in result["issues"]}


def test_partial_source_scan_and_missing_approval_never_certify():
    result = production_manifest([chapter(1)], [scene(1)], complete_source=False)
    assert result["complete_source"] is False
    assert result["structural_ready"] is False
    candidate = scene(1)
    candidate["status"] = "draft"
    result = production_manifest([chapter(1)], [candidate])
    assert "not_approved" in {x["kind"] for x in result["issues"]}
