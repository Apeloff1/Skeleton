"""Tenant- and version-scoped branching plan persistence and non-executing replay."""
from __future__ import annotations
from copy import deepcopy
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from routes import story_outcomes as routes
from core.branching_narrative import SCHEMA

ACTOR = {"email": "author@example.org", "tenant_id": "studio", "role": "editor"}
OTHER = {"email": "stranger@example.org", "tenant_id": "studio", "role": "editor"}


class Collection:
    def __init__(self):
        self.items = {}

    async def find_one(self, query):
        for row in self.items.values():
            if all(row.get(k) == v for k, v in query.items()):
                return deepcopy(row)
        return None

    async def insert_one(self, item):
        if item["_id"] in self.items:
            raise DuplicateKeyError("already exists")
        self.items[item["_id"]] = deepcopy(item)

    async def replace_one(self, query, item):
        for key, row in self.items.items():
            if all(row.get(k) == v for k, v in query.items()):
                self.items[key] = deepcopy(item)
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


def opt(key, tone):
    return {
        "id": key, "label": "Choose " + tone,
        "dialogue": "Tell the narrator to select " + tone,
        "intent": "Make an intentional choice that changes the story.",
        "emotional_consequence": "The ending has a distinct emotional texture.",
        "guard": {"op": "always"},
        "effects": [{"op": "meter_delta", "kind": "karma",
                     "delta": 40 if tone == "good" else -40}],
        "next_node": None, "ending": tone,
    }


def simple_plan():
    return {
        "schema_version": SCHEMA, "title": "City of Alternate Fates",
        "branch_id": "main", "entry_node": "opening",
        "initial_state": {}, "characters": [], "places": [],
        "nodes": [{
            "id": "opening", "chapter": 1, "act": 1, "scene": 1,
            "kind": "quest", "speaker": None, "place": None,
            "text": "The council offers two rival destinies for the player.",
            "plot_points": [{"id": "choice", "anchor": "two rival destinies"}],
            "options": [opt("mercy", "good"), opt("violence", "evil")],
        }],
        "endings": [{
            "id": tone, "title": "The " + tone + " ending", "tone": tone,
            "epilogue": "The world settles after the choice and remembers it for generations.",
            "consequences": "Political relationships and the future world are permanently altered.",
            "required_lore": [], "quest_conclusions": {}, "faction_conclusions": {},
            "character_conclusions": {}, "place_conclusions": {},
        } for tone in ("good", "evil")],
    }


@pytest.fixture
def db(monkeypatch):
    data = Collection()
    async def existing_game(pid, scope):
        if pid != "game_1":
            raise HTTPException(status_code=404, detail="missing game")
    monkeypatch.setattr(routes, "_db", SimpleNamespace(game_story_outcome_plans=data))
    monkeypatch.setattr(routes, "_existing_game", existing_game)
    return data


@pytest.mark.asyncio
async def test_save_replay_revision_and_conflicting_creator_writes(db):
    value = routes.SavePlan(expected_revision=0, plan=simple_plan())
    one = await routes.save_outcome_plan("game_1", value, user=ACTOR)
    assert one["ok"] and one["revision"] == 1
    assert one["replayed"] is False
    assert len(one["plan_digest"]) == 64
    retry = await routes.save_outcome_plan("game_1", value, user=ACTOR)
    assert retry["replayed"] is True
    changed = simple_plan()
    changed["title"] = "New title for the city story"
    with pytest.raises(HTTPException) as error:
        await routes.save_outcome_plan(
            "game_1", routes.SavePlan(expected_revision=0, plan=changed), user=ACTOR)
    assert error.value.status_code == 409
    updated = await routes.save_outcome_plan(
        "game_1", routes.SavePlan(expected_revision=1, plan=changed), user=ACTOR)
    assert updated["revision"] == 2
    assert updated["plan_digest"] != one["plan_digest"]


@pytest.mark.asyncio
async def test_simulator_only_replays_proven_choices_and_does_not_write_plan(db):
    saved = await routes.save_outcome_plan(
        "game_1", routes.SavePlan(expected_revision=0, plan=simple_plan()), user=ACTOR)
    before = deepcopy(db.items)
    start = await routes.simulate_outcomes("game_1", routes.SimulateIn(
        choices=[]), user=ACTOR)
    assert len(start["simulation"]["available_options"]) == 2
    done = await routes.simulate_outcomes("game_1", routes.SimulateIn(
        choices=["mercy"]), user=ACTOR)
    assert done["simulation"]["ending_id"] == "good"
    assert done["simulation"]["ending_accepted"]
    assert done["simulated_not_applied_to_game"] is True
    assert before == db.items
    with pytest.raises(HTTPException) as error:
        await routes.simulate_outcomes("game_1", routes.SimulateIn(
            choices=["choose_the_inaccessible_path"]), user=ACTOR)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_named_user_and_branch_are_isolated(db):
    await routes.save_outcome_plan("game_1",
        routes.SavePlan(expected_revision=0, plan=simple_plan()), user=ACTOR)
    with pytest.raises(HTTPException) as error:
        await routes.get_outcome_plan("game_1", branch_id="main", user=OTHER)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await routes.get_outcome_plan("game_1", branch_id="alternate", user=ACTOR)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await routes.save_outcome_plan(
            "other_game", routes.SavePlan(expected_revision=0, plan=simple_plan()),
            user=ACTOR)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_bounded_adversarial_path_audit_and_matrix_instruction(db):
    await routes.save_outcome_plan("game_1",
        routes.SavePlan(expected_revision=0, plan=simple_plan()), user=ACTOR)
    result = await routes.audit_branch_outcomes(
        "game_1", branch_id="main", path_budget=100, user=ACTOR)
    assert result["audit"]["all_paths_verified"] is True
    assert result["audit"]["reachable_endings"] == ["evil", "good"]
    listing = await routes.list_outcome_matrices(
        "game_1", start=0, limit=100, user=ACTOR)
    assert listing["catalog"]["matrix_count"] == 1000
    rubric = await routes.get_outcome_matrix_instruction(
        "game_1", branch_id="main", matrix_id="dialogue.choice_clarity.immediate",
        level=100, ending_id="good", user=ACTOR)
    assert rubric["plan_digest"] == result["plan_digest"]
    assert "Jeeves" not in rubric["instruction"]["prompt"]
    assert rubric["instruction"]["creator_signoff_required"] is True


@pytest.mark.asyncio
async def test_broken_graph_and_forged_choice_guard_fail_before_persistence(db):
    broken = simple_plan()
    broken["nodes"][0]["options"][0]["next_node"] = "missing"
    broken["nodes"][0]["options"][0]["ending"] = None
    with pytest.raises(HTTPException) as error:
        await routes.save_outcome_plan(
            "game_1", routes.SavePlan(expected_revision=0, plan=broken), user=ACTOR)
    assert error.value.status_code == 422
    assert not db.items



@pytest.mark.asyncio
async def test_unwitnessed_matrix_instruction_cannot_claim_a_real_player_history(db):
    await routes.save_outcome_plan("game_1",
        routes.SavePlan(expected_revision=0, plan=simple_plan()), user=ACTOR)
    plan_level = await routes.get_outcome_matrix_instruction(
        "game_1", branch_id="main",
        matrix_id="dialogue.choice_clarity.immediate",
        level=100, ending_id="good", user=ACTOR)
    assert plan_level["instruction"]["history_witnessed"] is False
    assert plan_level["instruction"]["player_history_digest"] is None
    assert "NO PLAYER PATH WITNESS" in plan_level["instruction"]["prompt"]


@pytest.mark.asyncio
async def test_witnessed_matrix_prompt_requires_authentic_successful_ending(db):
    await routes.save_outcome_plan("game_1",
        routes.SavePlan(expected_revision=0, plan=simple_plan()), user=ACTOR)
    body = routes.WitnessedMatrixPromptIn(
        branch_id="main", matrix_id="dialogue.choice_clarity.immediate",
        level=100, ending_id="good", choices=["mercy"])
    witnessed = await routes.get_witnessed_matrix_instruction(
        "game_1", body, user=ACTOR)
    assert witnessed["instruction"]["history_witnessed"] is True
    assert witnessed["instruction"]["player_history_digest"] == witnessed["playthrough_receipt"]
    assert len(witnessed["playthrough_receipt"]) == 64
    with pytest.raises(HTTPException) as exc:
        await routes.get_witnessed_matrix_instruction(
            "game_1", routes.WitnessedMatrixPromptIn(
                branch_id="main", matrix_id="dialogue.choice_clarity.immediate",
                level=100, ending_id="good", choices=["violence"]), user=ACTOR)
    assert exc.value.status_code == 409
