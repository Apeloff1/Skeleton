"""Research plans must not manufacture acquisition or promotion evidence."""
import json
import subprocess
import sys
from itertools import repeat

import pytest

from skeleton.ai.game_builder.game_niche_catalog import NICHES, niche_catalog
from skeleton.ai.game_builder.game_niche_research import plan_niche_research, plan_niche_hybrid


def plan(ids=("precision_platformer", "deckbuilder_roguelike"), **kwargs):
    return plan_niche_research(ids, platform="game_boy", title="Original research", **kwargs)


def test_catalog_has_substantive_distinct_profiles():
    assert len(NICHES) == 84
    assert len({n.family for n in NICHES}) == 21
    assert len({n.proposed_measurement for n in NICHES}) == len(NICHES)
    assert len({n.failure_probe for n in NICHES}) == len(NICHES)
    assert all(len(n.mechanics) == 3 and n.original_design_prompt for n in NICHES)
    assert not niche_catalog()["empirically_validated"]


def test_query_budget_fairness_and_deferred_work():
    result = plan(max_queries=3)
    assert [q["niche_id"] for q in result["queries"]] == [
        "precision_platformer", "deckbuilder_roguelike", "precision_platformer"]
    assert result["query_pairs_total"] == 30
    assert result["query_pairs_deferred"] == 27
    assert sum(d["deferred_queries"] for d in result["dossiers"]) == 27


def test_full_budget_does_not_claim_any_evidence():
    result = plan(max_queries=2048)
    assert result["query_pairs_deferred"] == 0
    assert result["acquired_sources"] == 0
    assert all(not result[k] for k in ("network_executed", "empirically_validated",
        "training_authorized", "memory_promotion_authorized", "release_authorized"))
    for d in result["dossiers"]:
        assert all(lane["state"] == "not_acquired" and lane["citations"] == []
                   for lane in d["evidence_lanes"].values())
    roles = {q["target_id"]: q["evidence_role"] for q in result["queries"]}
    assert roles["angry_video_game_nerd"] == "comedy_criticism"
    assert roles["news_engagement"] == "engagement_signal"
    assert roles["lets_play"] == "observed_play"


def test_platform_binding_and_determinism():
    result = plan()
    assert result == plan()
    assert result["platform"]["id"] == "game_boy"
    assert "D-pad" in result["dossiers"][0]["platform_questions"][0]
    assert result["plan_digest"] != plan(max_queries=1)["plan_digest"]
    with pytest.raises(ValueError):
        plan_niche_research(["precision_platformer"], platform="imaginary_console", title="x")


@pytest.mark.parametrize("ids", [[], ["unknown"], ["precision_platformer"] * 2, repeat("precision_platformer")])
def test_bad_or_unbounded_niches_rejected(ids):
    with pytest.raises(ValueError):
        plan(ids)


@pytest.mark.parametrize("kwargs", [{"max_queries": True}, {"max_queries": 0},
    {"max_queries": 2049}, {"target_ids": []}, {"target_ids": ["unknown"]},
    {"target_ids": ["lets_play", "lets_play"]}, {"target_ids": repeat("lets_play")}])
def test_invalid_budgets_and_targets_rejected(kwargs):
    with pytest.raises(ValueError):
        plan(**kwargs)


def test_custom_source_selection_preserves_context():
    result = plan(target_ids=["lets_play"])
    assert len(result["queries"]) == 2
    assert all("timecode" in q["required_context"] for q in result["queries"])


def test_hybrid_never_inherits_clearance():
    result = plan_niche_hybrid([n.niche_id for n in NICHES[:4]], premise="A new weather station")
    assert len(result["pair_reviews"]) == 6
    assert len(result["prototype_tests"]) == 4
    assert all(not result[k] for k in ("rights_inherited", "originality_verified",
                                      "product_built", "release_authorized"))
    for count in (1, 5):
        with pytest.raises(ValueError):
            plan_niche_hybrid([n.niche_id for n in NICHES[:count]], premise="Original")


def test_cli_emits_reviewable_json():
    run = subprocess.run([sys.executable, "-m", "skeleton.ai.game_builder.game_niche_research",
        "--niche", "precision_platformer", "--platform", "nes", "--title", "Prototype",
        "--max-queries", "2"], capture_output=True, text=True, check=True)
    result = json.loads(run.stdout)
    assert result["platform"]["id"] == "nes"
    assert len(result["queries"]) == 2
