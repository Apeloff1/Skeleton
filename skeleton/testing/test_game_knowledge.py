"""Tests for reference-backed game knowledge retrieval."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skeleton.acquired.gaming import GameKnowledgeBase, GameReference, build_game_knowledge_context
from skeleton.pipelines.gameforge import GameForge


def _reference_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "appid": 1,
        "title": "Example",
        "era": "example",
        "dialect": "example",
        "source": "test",
        "citation": "Example citation",
        "license": "Test-License",
        "url": "https://example.invalid",
        "stored_prose": 0,
    }
    payload.update(overrides)
    return payload


def test_packaged_knowledge_loads_reference_index() -> None:
    knowledge = GameKnowledgeBase.packaged()

    assert len(knowledge.references) == 12
    assert knowledge.eras() == {
        "cozy": 1,
        "extraction_now": 2,
        "metroidvania": 2,
        "roguelike": 3,
        "soulslike": 4,
    }


def test_search_prefers_explicit_title_match_within_era() -> None:
    matches = GameKnowledgeBase.packaged().search(
        "elden ring boss combat",
        era="soulslike",
        limit=3,
    )

    assert matches[0].reference.title == "Elden Ring"
    assert matches[0].score > matches[1].score
    assert {"elden", "ring"}.issubset(matches[0].matched_terms)


def test_context_is_bounded_and_preserves_provenance() -> None:
    context = build_game_knowledge_context(
        "cooperative extraction game",
        era="extraction_now",
        limit=2,
    )

    assert context["kind"] == "game-reference-context"
    assert context["reference_count"] == 2
    assert len(context["references"]) == 2
    assert all(reference["citation"] for reference in context["references"])
    assert all(reference["license"] for reference in context["references"])
    assert "stored_prose" not in context["references"][0]


def test_reference_rejects_copied_prose() -> None:
    with pytest.raises(ValueError, match="metadata-only"):
        GameReference.from_mapping(_reference_payload(stored_prose=1))


@pytest.mark.parametrize("appid", [True, "1", 1.5, 0, -1])
def test_reference_requires_positive_integer_appid(appid: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        GameReference.from_mapping(_reference_payload(appid=appid))


def test_reference_rejects_non_text_required_metadata() -> None:
    with pytest.raises(ValueError, match="required text fields: title"):
        GameReference.from_mapping(_reference_payload(title=7))


def test_from_path_rejects_non_object_root(tmp_path: Path) -> None:
    path = tmp_path / "references.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="must contain an object"):
        GameKnowledgeBase.from_path(path)


def test_from_path_rejects_non_object_entries(tmp_path: Path) -> None:
    path = tmp_path / "references.json"
    path.write_text(
        json.dumps({"kind": "reference-index", "games": ["not-an-object"], "n": 1}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="entries must be objects"):
        GameKnowledgeBase.from_path(path)


def test_from_path_rejects_non_integer_declared_count(tmp_path: Path) -> None:
    path = tmp_path / "references.json"
    path.write_text(
        json.dumps({"kind": "reference-index", "games": [_reference_payload()], "n": "1"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="count must be an integer"):
        GameKnowledgeBase.from_path(path)


def test_search_limit_must_be_positive() -> None:
    with pytest.raises(ValueError, match="limit must be positive"):
        GameKnowledgeBase.packaged().search("soulslike", limit=0)


def test_gameforge_builds_era_grounding_from_acquired_knowledge() -> None:
    intake = SimpleNamespace(
        genre="action-adventure",
        era="extraction_now",
        vision="third-person tactical sci-fi extraction with equipment progression",
    )

    context = GameForge()._build_knowledge_context(intake)

    assert context["era"] == "extraction_now"
    assert context["reference_count"] == 2
    assert {reference["title"] for reference in context["references"]} == {
        "Hunt Showdown",
        "Lethal Company",
    }
    assert context["speculative_rag"]["pipeline"] == "game_logic"
    assert context["speculative_rag"]["queries"]
