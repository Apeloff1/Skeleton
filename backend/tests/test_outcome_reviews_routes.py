"""Witnessed dialogue reviews, model nonapproval and per-ending isolation."""
from __future__ import annotations
from copy import deepcopy
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from core.branching_narrative import validate_plan
from routes import outcome_reviews as route
from test_branching_narrative import plan as authored_plan

USER = {"email": "author@example.org", "tenant_id": "studio", "role": "editor"}


class Ledger:
    def __init__(self):
        self.entries = {}

    async def insert_one(self, doc):
        if doc["_id"] in self.entries:
            raise DuplicateKeyError("duplicate review")
        self.entries[doc["_id"]] = deepcopy(doc)

    async def find_one(self, query):
        return next((deepcopy(x) for x in self.entries.values()
                     if all(x.get(k) == v for k, v in query.items())), None)

    async def update_one(self, query, edit):
        for row in self.entries.values():
            if all(row.get(k) == v for k, v in query.items()):
                row.update(edit["$set"])
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    def find(self, query):
        records = [deepcopy(x) for x in self.entries.values()
                   if all(x.get(k) == v for k, v in query.items())]
        class Cursor:
            def limit(self, amount):
                self.count = amount
                return self
            async def to_list(self, *, length):
                return records[:length]
        return Cursor()


@pytest.fixture
def bound(monkeypatch):
    plan = validate_plan(authored_plan())
    ledger = Ledger()
    monkeypatch.setattr(route, "_db", SimpleNamespace(game_story_outcome_reviews=ledger))
    async def get(scope, branch):
        assert scope["game_id"] == "game"
        if branch != "main":
            raise HTTPException(status_code=404, detail="no branch")
        return {"compiled": plan, "source_digest": plan["source_digest"]}
    monkeypatch.setattr(route, "_plan", get)
    return plan, ledger


def review(plan, **overrides):
    data = dict(
        branch_id="main", plan_digest=plan["source_digest"],
        ending_id="restoration", matrix_id="ending_closure.plot_setup_payoff.ending",
        level=100, verdict="fail",
        rationale="This apparent ending does not properly pay off its earlier dialogue.",
        quote="Aria reveals",
        source_node_id="junction",
        witness_choices=["help_aria", "good_ending"],
        provenance="jeeves_model_candidate", creator_approved=False,
    )
    data.update(overrides)
    return route.EndingReviewIn(**data)


@pytest.mark.asyncio
async def test_real_choice_history_and_authored_quote_support_review_receipt(bound):
    compiled, ledger = bound
    result = await route.submit_outcome_review(
        "game", review(compiled), user=USER)
    assert result["ok"] and result["creator_approved"] is False
    assert len(result["review_receipt"]) == 64
    assert (await route.submit_outcome_review(
        "game", review(compiled), user=USER))["replayed"]
    coverage = await route.outcome_matrix_coverage(
        "game", branch_id="main", ending_id="restoration", user=USER)
    assert coverage["coverage"]["required"] == 100000
    assert coverage["coverage"]["missing"] == 99999
    assert coverage["coverage"]["complete"] is False


@pytest.mark.asyncio
async def test_creator_adopts_immutable_model_finding_without_falsifying_failure(bound):
    compiled, ledger = bound
    row = await route.submit_outcome_review("game", review(compiled), user=USER)
    acceptance = route.EndorseEndingReview(
        plan_digest=compiled["source_digest"], ending_id="restoration",
        matrix_id="ending_closure.plot_setup_payoff.ending",
        level=100, review_receipt=row["review_receipt"],
    )
    signed = await route.approve_outcome_review("game", acceptance, user=USER)
    assert signed["creator_approved"] is True
    assert (await route.approve_outcome_review(
        "game", acceptance, user=USER))["replayed"]
    result = await route.outcome_matrix_coverage(
        "game", branch_id="main", ending_id="restoration", user=USER)
    assert result["coverage"]["failed"] == 1
    assert result["coverage"]["complete"] is False
    assert result["coverage"]["missing"] == 99999


@pytest.mark.asyncio
async def test_wrong_ending_path_stale_plan_and_forged_quote_rejected(bound):
    compiled, ledger = bound
    for changes, status in [
        (dict(ending_id="ruin"), 422),
        (dict(witness_choices=["walk_away", "neutral_ending"]), 422),
        (dict(plan_digest="f" * 64), 409),
        (dict(quote="Unwritten author claim"), 422),
        (dict(source_node_id="not_authored"), 422),
    ]:
        with pytest.raises(HTTPException) as exc:
            await route.submit_outcome_review("game", review(compiled, **changes), user=USER)
        assert exc.value.status_code == status
    assert not ledger.entries


@pytest.mark.asyncio
async def test_model_never_self_approves_and_review_provenance_is_conflict_safe(bound):
    compiled, ledger = bound
    with pytest.raises(HTTPException) as exc:
        await route.submit_outcome_review("game",
            review(compiled, creator_approved=True), user=USER)
    assert exc.value.status_code == 409
    await route.submit_outcome_review("game", review(compiled), user=USER)
    with pytest.raises(HTTPException) as exc:
        await route.submit_outcome_review("game",
            review(compiled, verdict="pass", provenance="creator",
                   creator_approved=True), user=USER)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_every_ending_uses_separate_cell_ledger(bound):
    compiled, ledger = bound
    await route.submit_outcome_review("game", review(compiled), user=USER)
    ending = compiled["endings"]["restoration"]
    result = await route.submit_outcome_review("game", review(compiled,
        ending_id="ruin", source_node_id=None, witness_choices=[],
        quote="The epilogue shows that Aria"), user=USER)
    # Earlier route fixture uses a different ending epilogue; the quote above
    # deliberately belongs to both authored consequences and is still scoped
    # to an individual ending ID.
    assert result["ending_id"] == "ruin"
    assert len(ledger.entries) == 2
