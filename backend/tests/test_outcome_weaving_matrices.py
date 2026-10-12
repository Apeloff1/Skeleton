"""1,000 nonduplicated outcome-weaving rubrics, 100 scrutiny levels apiece."""
import pytest

from core.outcome_weaving_matrices import (
    OUTCOME_DOMAINS, PERSPECTIVES, catalog, matrix, instruction, coverage_summary,
)


def test_exact_multiplicity_and_nonduplicated_craft_skills():
    assert len(OUTCOME_DOMAINS) == 20
    assert all(len(skills) == 10 and len(set(skills)) == 10
               for skills in OUTCOME_DOMAINS.values())
    assert len(PERSPECTIVES) == 5
    pages = [catalog(start=i, limit=100)["matrices"] for i in range(0, 1000, 100)]
    ids = [r["id"] for page in pages for r in page]
    assert len(ids) == len(set(ids)) == 1000
    assert catalog()["total_review_cells"] == 100000
    assert catalog()["status"] == "catalog_only_not_automatically_executed"
    assert len({r["rubric"] for page in pages for r in page}) == 1000


def test_storyline_dimensions_cover_moral_neutral_quests_law_gangs_and_lore():
    for domain in (
        "quest_completion", "quest_failure", "missed_quests", "karma",
        "regions", "cities", "people", "factions", "gangs", "government_law",
        "dialogue", "character_arcs", "place_lore", "world_reactivity",
        "ending_choice", "ending_closure", "postgame", "mystery_reveals",
        "replayability", "literary_quality",
    ):
        assert domain in OUTCOME_DOMAINS
        assert len(OUTCOME_DOMAINS[domain]) == 10
    chosen = "missed_quests.missed_ally_response.ending"
    assert matrix(chosen)["domain"] == "missed_quests"
    assertion = instruction(chosen, 100, ending_id="heroic_peace",
                            player_history_digest="a" * 64)
    assert assertion["review_status"] == "unexecuted"
    assert assertion["creator_signoff_required"]
    assert "independent_recheck" in assertion["prompt"]
    assert "government/law" in assertion["prompt"]
    assert len(assertion["instruction_receipt"]) == 64


def test_wrong_matrix_bad_range_and_unbounded_paging_fail_closed():
    for key in ("not-real", "karma.mercy_consequences.fake",
                "dialogue.non_existent_skill.ending"):
        with pytest.raises(ValueError):
            matrix(key)
    for start, limit in [(-1, 10), (1001, 2), (0, 101), (0, 0)]:
        with pytest.raises(ValueError):
            catalog(start=start, limit=limit)
    for level in (0, -1, 101):
        with pytest.raises(ValueError):
            instruction("dialogue.choice_clarity.immediate", level,
                        ending_id="neutral", player_history_digest="b" * 64)


def test_100_thousand_distinct_review_cells_require_human_approved_evidence():
    ids = [row["id"] for start in range(0, 1000, 100)
           for row in catalog(start=start, limit=100)["matrices"]]
    # Only the 100x100 outcome review lattice can claim complete, not a count
    # of repeated hashes or a model response not checked by a creator.
    approvals = [{
        "matrix_id": mid, "level": level, "creator_approved": True,
        "plan_digest": "a" * 64, "ending_id": "neutral", "verdict": "pass",
    } for mid in ids for level in range(1, 101)]
    report = coverage_summary(approvals, plan_digest="a" * 64, ending_id="neutral")
    assert report["complete"] is True
    assert report["required"] == 100000
    assert report["passed"] == 100000
    assert report["artistic_perfection_guaranteed"] is False
    approvals[-1]["creator_approved"] = False
    assert coverage_summary(approvals, plan_digest="a" * 64,
                            ending_id="neutral")["complete"] is False
    approvals[-1]["creator_approved"] = True
    approvals[-1]["plan_digest"] = "b" * 64
    assert coverage_summary(approvals, plan_digest="a" * 64,
                            ending_id="neutral")["complete"] is False


def test_incomplete_and_duplicated_result_will_not_certify_quality():
    one = {
        "matrix_id": "dialogue.choice_clarity.immediate", "level": 1,
        "creator_approved": True, "plan_digest": "a" * 64,
        "ending_id": "bad", "verdict": "fail",
    }
    result = coverage_summary([one, one], plan_digest="a" * 64, ending_id="bad")
    assert result["duplicate_cells"] == 1
    assert result["failed"] == 1
    assert result["missing"] == 99999
    assert result["complete"] is False
