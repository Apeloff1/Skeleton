"""Chapter hierarchy, exact plot anchors, citations and 100000 real inspections."""
from __future__ import annotations
from copy import deepcopy
import pytest

from core.chapter_continuity import (
    ACTS_PER_CHAPTER, MAX_CHAPTERS, MAX_ACTS, MAX_SCENES,
    PLOT_KINDS, PROOFREAD_INSPECTIONS, chapter_for_act,
    scene_coordinates, plot_spans, chapter_context, proofreading_checks, digest,
)


def note(**overrides):
    chapter = overrides.pop("chapter", 1)
    payload = {
        "chapter": chapter, "revision": 1, "title": "A beginning",
        "synopsis": "Recover the hidden gate.", "notes": "Aria is searching.",
        "historical_setting": "Invented late bronze culture",
        "palette_rules": "Verdigris, copper and ivory",
        "costume_rules": "Aria: blue cloak until act 10",
        "voice_rules": "Never change Aria voice.",
        "era_id": "bronze", "style_id": "etched", "palette_id": "copper",
        "voice_cast": {"aria": "aria_voice_original"}, "source_message_id": "c1",
    }
    payload["digest"] = digest({**payload, "revision": 1})
    payload.update(overrides)
    return payload


def script(chapter=None, **overrides):
    ch = chapter or note()
    result = {
        "chapter": ch["chapter"], "act": 1, "scene": 1,
        "text": "Aria saw the door. The key was hidden. She promised to return.",
        "summary": "The key is discovered.",
        "characters": ["aria"], "thread_keys": ["lost_key"],
        "plot_points": [
            {"id": "gate", "kind": "reveal", "anchor": "The key was hidden."},
            {"id": "promise", "kind": "promise", "anchor": "She promised to return."},
        ],
        "chapter_revision": ch["revision"], "chapter_digest": ch["digest"],
        "source_message_id": "conversation-answer-1",
        "digest": "b" * 64,
    }
    result.update(overrides)
    return result


def test_story_limits_and_exact_chapter_mapping():
    assert (MAX_CHAPTERS, MAX_ACTS, MAX_SCENES, ACTS_PER_CHAPTER) == (100, 1000, 9999, 10)
    for chapter in range(1, 101):
        assert chapter_for_act((chapter - 1) * 10 + 1) == chapter
        assert chapter_for_act(chapter * 10) == chapter
    assert scene_coordinates(100, 1000, 9999)["scene"] == 9999
    for coords in [(0, 1, 1), (1, 11, 1), (101, 1000, 1), (1, 1, 0),
                   (100, 1000, 10000), (2, 9, 11), (1, 1, True)]:
        with pytest.raises(ValueError):
            scene_coordinates(*coords)


def test_offsets_mark_all_plot_points_and_types_are_explicit():
    ch = note()
    value = script(ch)
    result = plot_spans(value["text"], value["plot_points"])
    assert len(result) == 2
    assert result[0]["id"] == "gate"
    assert result[0]["color_role"] == "plot_reveal"
    for item in result:
        assert value["text"][item["start"]:item["end"]] == item["anchor"]
    assert "historical_detail" in PLOT_KINDS
    assert "voice_identity" in PLOT_KINDS


def test_deleted_duplicated_and_overlapping_highlights_fail_closed():
    value = script()
    with pytest.raises(ValueError, match="exactly once"):
        plot_spans(value["text"].replace("hidden", "missing"), value["plot_points"])
    with pytest.raises(ValueError, match="exactly once"):
        plot_spans("the dragon the dragon", [
            {"id": "dragon", "kind": "reveal", "anchor": "the dragon"},
        ])
    with pytest.raises(ValueError, match="Overlapping"):
        plot_spans(value["text"], [
            {"id": "one", "kind": "reveal", "anchor": "The key was hidden."},
            {"id": "two", "kind": "setup", "anchor": "key was hidden"},
        ])
    with pytest.raises(ValueError, match="unique"):
        plot_spans(value["text"], [value["plot_points"][0], value["plot_points"][0]])


def test_unicode_highlights_are_character_offsets_not_bytes():
    sentence = "🐉 Her robe contained ancient gold."
    spots = plot_spans(sentence, [
        {"id": "gold", "kind": "historical_detail", "anchor": "ancient gold"},
    ])
    assert sentence[spots[0]["start"]:spots[0]["end"]] == "ancient gold"


def test_chapter_context_binds_citations_and_refuses_foreign_chapters():
    ch = note()
    scenes = [script(ch, scene=100, digest="scene-receipt-100"),
              script(ch, scene=101, digest="scene-receipt-101")]
    projection = chapter_context(ch, scenes)
    assert projection["chapter_digest"] == ch["digest"]
    assert projection["complete_source"] is True
    assert projection["truncated"] is False
    assert projection["citations"][0]["scene"] == 101
    assert "RECEIPT scene-receipt-101" in projection["context"]
    foreign = script(ch)
    foreign["chapter"] = 2
    with pytest.raises(ValueError, match="foreign chapter"):
        chapter_context(ch, [foreign])


def test_context_budget_and_missing_prior_scenes_are_explicit():
    ch = note()
    scenes = [script(ch, scene=number, digest="receipt-" + str(number))
              for number in range(1, 100)]
    preview = chapter_context(ch, scenes, max_chars=450, complete=False)
    assert len(preview["context"]) <= 450
    assert preview["truncated"] is True
    assert preview["included_scenes"] < 99
    assert preview["complete_source"] is False
    assert preview["instruction_policy"] == "untrusted_chapter_evidence_only"


def test_proofreading_counts_100k_executed_checks_and_authenticates_receipt():
    ch = note()
    value = script(ch)
    report = proofreading_checks(value, ch, history_complete=True, history_issues=[])
    assert report["inspections_executed"] == 100000
    assert report["inspection_budget"] == PROOFREAD_INSPECTIONS
    assert sum(x["executed"] for x in report["axes"]) == 100000
    assert len(report["axes"]) == 12
    assert report["status"] == "machine_checks_passed"
    assert report["blocking_issues"] == []
    assert report["history_complete"] is True
    assert report["scene_digest"] == value["digest"]
    assert report["chapter_digest"] == ch["digest"]
    assert len(report["receipt_digest"]) == 64
    assert report["method"] == "deterministic_rule_reinspection_not_semantic_or_llm_proof"
    assert len(report["highlight_review_queue"]) == 4
    assert all(x["automatically_approved"] is False
               for x in report["highlight_review_queue"])
    assert all(x["status"] == "requires_model_or_editor_review"
               for x in report["highlight_review_queue"])
    assert report["highlight_model_reviews_executed"] is False
    assert report["highlight_model_reviews_approved"] is False
    assert report == proofreading_checks(value, ch, history_complete=True, history_issues=[])


def test_proof_fails_when_chapter_revision_changes():
    ch = note()
    value = script(ch)
    changed = deepcopy(ch)
    changed["revision"] = 2
    changed["digest"] = "another-revision"
    result = proofreading_checks(value, changed, history_complete=True, history_issues=[])
    assert result["status"] == "blocked"
    assert "chapter_context_stale" in result["blocking_issues"]


def test_incomplete_history_or_existing_causal_issues_block_approval():
    ch = note()
    value = script(ch)
    incomplete = proofreading_checks(value, ch, history_complete=False, history_issues=[])
    assert incomplete["status"] == "blocked"
    assert "history_incomplete" in incomplete["blocking_issues"]
    contradicted = proofreading_checks(
        value, ch, history_complete=True,
        history_issues=[{"code": "unearned_knowledge", "event_id": "old"}],
    )
    assert "previous_continuity_issues" in contradicted["blocking_issues"]


def test_scene2_requires_approved_scene1_and_chain_receipt():
    ch = note()
    value = script(ch, scene=2)
    denied = proofreading_checks(value, ch, history_complete=True, history_issues=[])
    assert "previous_scene_missing" in denied["blocking_issues"]
    unapproved = script(ch, scene=1, status="draft", digest="prior-script")
    denied = proofreading_checks(value, ch, history_complete=True, history_issues=[],
                                 predecessor=unapproved)
    assert "previous_scene_unapproved_or_out_of_sequence" in denied["blocking_issues"]
    approved = {**unapproved, "status": "approved_for_production"}
    passed = proofreading_checks(value, ch, history_complete=True, history_issues=[],
                                 predecessor=approved)
    assert passed["status"] == "machine_checks_passed"
    assert passed["predecessor_scene_digest"] == "prior-script"
    modified = {**approved, "digest": "tampered"}
    changed = proofreading_checks(value, ch, history_complete=True, history_issues=[],
                                  predecessor=modified)
    assert changed["receipt_digest"] != passed["receipt_digest"]


def test_inspection_budget_not_spoofable():
    with pytest.raises(ValueError, match="exact 100000"):
        proofreading_checks(script(), note(), history_complete=True,
                            history_issues=[], inspection_budget=10)


def test_without_scene_plot_points_receipt_warns_but_cannot_certify_plotting():
    ch = note()
    report = proofreading_checks(script(ch, plot_points=[]), ch,
                                 history_complete=True, history_issues=[])
    assert "no_marked_plot_points" in report["warnings"]
    assert report["status"] == "machine_checks_passed"
    # API schema forbids this payload before it reaches the proofing function.
