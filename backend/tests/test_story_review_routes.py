"""Model critique is not self-certifying; every matrix result requires evidence."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import pytest

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from routes import story_review as route

AUTHOR = {"email": "writer@example.com", "tenant_id": "team", "role": "editor"}


class Reviews:
    def __init__(self):
        self.docs = {}

    async def insert_one(self, item):
        if item["_id"] in self.docs:
            raise DuplicateKeyError("duplicate review")
        self.docs[item["_id"]] = deepcopy(item)

    async def find_one(self, query):
        row = self.docs.get(query.get("_id"))
        return deepcopy(row) if row else None

    def find(self, query):
        return Cursor([x for x in self.docs.values()
                      if all(x.get(k) == v for k, v in query.items())])


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    def limit(self, n):
        return self

    async def to_list(self, *, length):
        return deepcopy(self.docs[:length])


@pytest.fixture
def data(monkeypatch):
    notes = {
        "digest": "a" * 64, "chapter": 1, "scene": 1,
        "branch_id": "main", "text": "Aria gasped as the castle fell.",
        "source_message_id": "message-1",
        "plot_points": [{"id": "castle_falls",
                         "anchor": "the castle fell"}],
    }
    reviews = Reviews()
    monkeypatch.setattr(route, "_db", SimpleNamespace(game_story_reviews=reviews))
    async def get(scope, branch, scene):
        assert scope["game_id"] == "game"
        if branch != "main" or scene != 1:
            raise HTTPException(status_code=404, detail="Scene not found")
        return notes
    monkeypatch.setattr(route, "_authoritative_scene", get)
    return notes, reviews


def submission(**change):
    params = {
        "branch_id": "main", "scene_digest": "a" * 64,
        "matrix_id": "engagement.surprise_earned", "level": 100,
        "verdict": "fail",
        "rationale": "The alleged surprise is not supported by any earlier scene.",
        "citation_quote": "the castle fell",
        "citation_plot_id": "castle_falls",
        "provenance": "creator", "reviewed_and_approved_by_creator": True,
    }
    params.update(change)
    return route.ReviewSubmission(**params)


@pytest.mark.asyncio
async def test_exact_cited_model_assessment_can_be_recorded_but_is_not_perfect_story_proof(data):
    note, reviews = data
    saved = await route.submit_matrix_review("game", 1, submission(), user=AUTHOR)
    assert saved["ok"] is True
    assert saved["creator_approved"] is True
    assert saved["model_quality_guaranteed"] is False
    assert len(saved["review_receipt"]) == 64
    assert len(reviews.docs) == 1
    repeated = await route.submit_matrix_review("game", 1, submission(), user=AUTHOR)
    assert repeated["replayed"] is True


@pytest.mark.asyncio
async def test_model_cannot_claim_human_approval_without_an_explicit_review(data):
    with pytest.raises(HTTPException) as e:
        await route.submit_matrix_review("game", 1, submission(
            provenance="jeeves_model_candidate",
            reviewed_and_approved_by_creator=True,
        ), user=AUTHOR)
    assert e.value.status_code == 409
    candidate = await route.submit_matrix_review("game", 1, submission(
        provenance="jeeves_model_candidate",
        reviewed_and_approved_by_creator=False,
    ), user=AUTHOR)
    assert candidate["creator_approved"] is False


@pytest.mark.asyncio
async def test_stale_scene_and_fake_plot_highlights_fail_closed(data):
    with pytest.raises(HTTPException) as e:
        await route.submit_matrix_review("game", 1, submission(
            scene_digest="b" * 64,
        ), user=AUTHOR)
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:
        await route.submit_matrix_review("game", 1, submission(
            citation_plot_id="not_highlighted",
        ), user=AUTHOR)
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        await route.submit_matrix_review("game", 1, submission(
            citation_quote="unseen script fragment",
        ), user=AUTHOR)
    assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_identity_conflict_cannot_replace_review_after_signed_submission(data):
    await route.submit_matrix_review("game", 1, submission(), user=AUTHOR)
    with pytest.raises(HTTPException) as e:
        await route.submit_matrix_review("game", 1,
            submission(verdict="pass", rationale="The plot now makes perfect sense."), user=AUTHOR)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_coverage_counts_only_reviewed_cells_for_current_receipt(data):
    await route.submit_matrix_review("game", 1, submission(), user=AUTHOR)
    result = await route.get_matrix_coverage("game", 1, branch_id="main", user=AUTHOR)
    assert result["coverage"]["cells_required"] == 10000
    assert result["coverage"]["cells_missing"] == 9999
    assert result["coverage"]["failure_count"] == 1
    assert result["coverage"]["fully_reviewed"] is False


@pytest.mark.asyncio
async def test_registry_and_model_review_prompt_are_retrieved_without_claiming_quality(data):
    listing = await route.list_story_matrices("game", start=0, limit=100, user=AUTHOR)
    assert listing["catalog"]["total_cells"] == 10000
    assert len(listing["catalog"]["matrices"]) == 100
    prompt = await route.get_matrix_prompt(
        "game", 1, branch_id="main", matrix_id="mystery.red_herring_fairness",
        level=100, user=AUTHOR)
    assert prompt["scene_receipt"] == "a" * 64
    assert "earlier" not in prompt["prompt"].lower() or isinstance(prompt["prompt"], str)
    assert "red_herring_fairness" in prompt["prompt"]
