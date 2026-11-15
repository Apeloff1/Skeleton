"""Recovered 2026-05 reading assessment contract: no fabricated answers."""
from copy import deepcopy

import pytest

from core.academy_chapter_quiz import (
    EvidenceUnavailable, SourceChanged, build_quiz, cache_identity, chapter_source,
    chapter_view, grade_quiz,
)


def chapter():
    glossary = [{"term": f"Term {i}", "definition": f"Distinct technical definition for concept number {i}."}
                for i in range(8)]
    sections = [{"title": f"Section {i}", "text": f"Distinct lesson passage number {i} explains a separate engineering technique."}
                for i in range(8)]
    body = "\n".join([f"## {s['title']}\n{s['text']}" for s in sections] +
                     [f"{g['term']} — {g['definition']}" for g in glossary])
    return {"chapter_name": "Engineering lesson", "body_md": body, "sections": sections,
            "glossary_structured": glossary}


def test_exact_sources_and_deterministic_legacy_shape():
    raw = chapter()
    source = chapter_source(raw)
    first = build_quiz(source, "book", "open_pro_git", 0)
    second = build_quiz(chapter_source(deepcopy(raw)), "book", "open_pro_git", 0)
    assert first == second
    assert first["offline_generated"] and not first["certification_qualified"]
    assert first["source_sha256"] == chapter_view(raw)["source_sha256"]
    assert len(first["questions"]) == 5
    for row in first["questions"]:
        assert len(set(row["options"])) == 4
        assert 0 <= row["answer_idx"] <= 3
        assert row["evidence"]["excerpt"] in raw["body_md"]
        assert row["evidence"]["source_sha256"] == source.digest
    assert len({row["id"] for row in first["questions"]}) == 5
    assert len({row["kind"] for row in first["questions"]}) >= 2


def test_profile_and_identity_change_receipt_and_can_grade():
    source = chapter_source(chapter())
    default = build_quiz(source, "book", "abc", 0)
    custom = build_quiz(source, "book", "abc", 0, {"ac_comp_quiz": 3, "ac_rev_hint": 2})
    assert len(custom["questions"]) > len(default["questions"])
    assert custom["assessment_sha256"] != default["assessment_sha256"]
    assert all("hint" in row for row in custom["questions"])
    answers = [row["answer_idx"] for row in custom["questions"]]
    assert grade_quiz(custom, custom["assessment_sha256"], answers)["score"] == 100
    with pytest.raises(SourceChanged):
        grade_quiz(custom, default["assessment_sha256"], answers)
    with pytest.raises(ValueError):
        grade_quiz(custom, custom["assessment_sha256"], [True] * len(answers))
    assert cache_identity("subject", "sub_rosetta_variables", 0)["book_id"] == "subject:sub_rosetta_variables"


def test_stale_and_detached_sources_fail_closed():
    original = chapter_source(chapter())
    raw = chapter()
    raw["body_md"] += "\nChanged."
    with pytest.raises(SourceChanged):
        build_quiz(chapter_source(raw), "book", "abc", 0,
                   expected_source_sha256=original.digest)
    raw["body_md"] = "No structured evidence."
    with pytest.raises(EvidenceUnavailable):
        build_quiz(chapter_source(raw), "book", "abc", 0)
    with pytest.raises(ValueError):
        build_quiz(original, "book", "../escape", 0)
    with pytest.raises(ValueError):
        build_quiz(original, "book", "abc", True)
    with pytest.raises(ValueError):
        build_quiz(original, "book", "abc", 0, {"ac_comp_quiz": float("nan")})


def test_generated_chapter_supplies_real_legacy_quiz_shape():
    from seeds.reading_content_generator import generate_chapter_content
    raw = generate_chapter_content("Pro Git", "Academy", "cs_foundations",
                                   "intermediate", "Getting started", 0, 12)
    quiz = build_quiz(chapter_source(raw), "book", "open_pro_git", 0)
    assert len(quiz["questions"]) == 5
    assert all(row["evidence"]["excerpt"] in raw["body_md"] for row in quiz["questions"])
