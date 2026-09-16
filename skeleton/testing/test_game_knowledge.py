"""Tests for reference-backed game knowledge retrieval."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from skeleton.acquired.gaming import GameKnowledgeBase, GameReference, build_game_knowledge_context
from skeleton.pipelines.gameforge import GameForge


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
        GameReference.from_mapping({
            "appid": 1,
            "title": "Example",
            "era": "example",
            "dialect": "example",
            "source": "test",
            "citation": "Example citation",
            "license": "Test-License",
            "url": "https://example.invalid",
            "stored_prose": 1,
        })


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
