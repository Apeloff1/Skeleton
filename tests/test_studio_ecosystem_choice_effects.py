"""Optional choice-specific ending predicates are replayed, never forged."""
from copy import deepcopy

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_choice_impact_matrix import page_choice_impacts
from skeleton.ai.game_builder.studio_ecosystem_ending_atlas import build_ending_atlas
from skeleton.ai.game_builder.studio_ecosystem_ending_plan import plan_authored_ending
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def authored():
    docs = deepcopy(read_blueprint(PROJECT))
    stage = docs["quest"]["stage_graph"][0]
    left, right = stage["alternatives"][:2]
    left_token = "choice:" + stage["id"] + ":protect"
    right_token = "choice:" + stage["id"] + ":explore"
    stage["choice_effects"] = {left: [left_token], right: [right_token]}
    docs["narrative"]["endings"][0]["requires"] = [right_token]
    return docs, stage["id"], left, right, left_token, right_token


def test_choice_effect_requires_exact_authored_alternative():
    docs, key, left, right, _, right_token = authored()
    program = compile_quest_program(docs)
    assert dict(program.stages[0].choice_effects)[right] == (right_token,)
    ending = docs["narrative"]["endings"][0]["id"]
    left_session = replay_quest(docs, [[key, left]], authorized=True)
    right_session = replay_quest(docs, [[key, right]], authorized=True)
    assert ending not in quest_progress(left_session, docs)["sandbox_endings_eligible"]
    assert ending in quest_progress(right_session, docs)["sandbox_endings_eligible"]
    assert left_session.digest != right_session.digest
    assert right_session.receipt()["release_certified"] is False


def test_planner_selects_required_choice_and_rejects_conflicts():
    docs, key, left, right, left_token, right_token = authored()
    ending = docs["narrative"]["endings"][0]["id"]
    plan = plan_authored_ending(docs, ending_id=ending, authorized=True)
    assert plan["status"] == "simulatable"
    assert plan["planned_steps"][0]["choice"] == right
    assert plan["sandbox_eligible_after_plan"] is True
    with pytest.raises(StudioQuestError, match="conflicts"):
        plan_authored_ending(docs, ending_id=ending, authorized=True,
                             preferred_choices={key: left})
    wrong = replay_quest(docs, [[key, left]], authorized=True)
    with pytest.raises(StudioQuestError, match="already completed"):
        plan_authored_ending(docs, ending_id=ending, session=wrong,
                             authorized=True)
    docs["narrative"]["endings"][0]["requires"] = [left_token, right_token]
    with pytest.raises(StudioQuestError, match="conflicting"):
        plan_authored_ending(docs, ending_id=ending, authorized=True)


def test_canon_atlas_and_matrix_recognize_real_branch_causality():
    docs, key, left, right, _, right_token = authored()
    proof = audit_canon_source(docs, authorized=True)
    assert proof["canon_consistent"]
    ending = docs["narrative"]["endings"][0]["id"]
    obligation = next(x for x in proof["ending_obligations"] if x["ending_id"] == ending)
    assert right_token not in obligation["unproven_predicates"]
    atlas = build_ending_atlas(
        docs, [], authorized=True, expected_source_digest=proof["source_digest"])
    card = next(x for x in atlas["endings"] if x["ending_id"] == ending)
    assert card["choice_to_ending_causality_verified"] is True
    matrix = page_choice_impacts(
        docs, [], authorized=True, expected_source_digest=proof["source_digest"])
    stage = next(x for x in matrix["stages"] if x["stage_id"] == key)
    assert stage["mechanical_outcomes_diverge"] is True
    assert len({x["mechanical_outcome_digest"] for x in stage["alternatives"]}) >= 2


@pytest.mark.parametrize("bad", [
    {"unknown": ["choice:investigate:valid"]},
    {"Document fracturing ice without entering restricted ground": ["external_verified"]},
    {"Document fracturing ice without entering restricted ground": ["choice:ratify:forged"]},
    {"Document fracturing ice without entering restricted ground": ["choice:investigate:bad-token!"]},
    {"Document fracturing ice without entering restricted ground": ["choice:investigate:dup", "choice:investigate:dup"]},
    {"Document fracturing ice without entering restricted ground": "choice:investigate:wrong_type"},
])
def test_forged_or_malformed_choice_effects_fail_closed(bad):
    docs, *_ = authored()
    docs["quest"]["stage_graph"][0]["choice_effects"] = bad
    with pytest.raises(StudioQuestError):
        compile_quest_program(docs)


def test_same_effect_token_cannot_be_attributed_to_two_alternatives():
    docs, key, left, right, _, token = authored()
    docs["quest"]["stage_graph"][0]["choice_effects"] = {
        left: [token], right: [token],
    }
    with pytest.raises(StudioQuestError, match="ambiguous"):
        compile_quest_program(docs)


def test_unknown_choice_predicate_and_legacy_compatibility():
    docs, *_ = authored()
    docs["narrative"]["endings"][0]["requires"] = ["choice:investigate:forged"]
    with pytest.raises(StudioQuestError, match="undeclared"):
        compile_quest_program(docs)
    original = read_blueprint(PROJECT)
    program = compile_quest_program(original)
    assert all(not any(tokens for _, tokens in stage.choice_effects)
               for stage in program.stages)
    replay_quest(original, [], authorized=True)
