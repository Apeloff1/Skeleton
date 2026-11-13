"""Actual seeded multi-realm expedition campaign and objective comparisons."""
from copy import deepcopy
import pytest
from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_qa import (
    QA_SCENARIOS, QAScenario, run_expedition_qa, compare_expedition_qa,
)
SOURCE="f"*64


def test_qa_exercises_multiple_original_games_and_actual_scenario_routes():
    report=run_expedition_qa("original",SOURCE,seeds=(7,17),islands=7)
    assert report["schema"]=="skeleton.game.frontier_expedition_qa.v1"
    assert report["seed_count"]==2 and report["scenario_count"]==7
    assert report["cases_executed"]==14
    assert report["executed_game_routes"]>=8
    assert report["physical_engine_playthroughs"]==0
    assert not report["release_approved"]
    # Fog cases intentionally share the *same* weather world: only player
    # equipment differs. Both independent identities are still unique.
    assert len({(row["world_digest"],row["traveler_digest"])
                for row in report["cases"]})==14
    assert all(len(row["receipt_digest"])==64 for row in report["cases"])


def test_qa_replay_repeatable_and_independently_comparable():
    a=run_expedition_qa("original",SOURCE,seeds=(4,5),islands=6)
    b=run_expedition_qa("original",SOURCE,seeds=(4,5),islands=6)
    assert a==b
    compare=compare_expedition_qa(a,b)
    assert compare["route_count_change"]==0
    assert compare["newly_blocked_cases"]==0
    assert compare["same_source"]
    assert len(compare["receipt_digest"])==64


def test_fog_without_instruments_is_explicitly_blocked_not_falsely_passed():
    qa=run_expedition_qa("original",SOURCE,seeds=(3,),islands=5)
    row=next(x for x in qa["cases"] if x["scenario"]=="fog_without_instruments")
    assert row["blocked"]
    assert row["routes_executed"]==0
    assert row["block_reason"]=="unreachable_under_authorized_capabilities"
    safe=next(x for x in qa["cases"] if x["scenario"]=="fog_with_instruments")
    assert not safe["blocked"]
    assert safe["routes_executed"]>=1


def test_different_quality_conditions_produce_objective_evidence():
    qa=run_expedition_qa("original",SOURCE,seeds=(1,),islands=8)
    clear=next(x for x in qa["cases"] if x["scenario"]=="clear")
    rain=next(x for x in qa["cases"] if x["scenario"]=="rain")
    assert clear["world_digest"]!=rain["world_digest"]
    assert clear["route_times_seconds"]!=rain["route_times_seconds"]


@pytest.mark.parametrize("seeds", ((), (1,1), (True,), (-1,), tuple(range(33))))
def test_qa_rejects_unsafe_or_duplicate_seed_matrix(seeds):
    with pytest.raises(ExpeditionError,match="seeds"):
        run_expedition_qa("original",SOURCE,seeds=seeds)


def test_tampered_qa_receipt_fails_comparative_review():
    a=run_expedition_qa("original",SOURCE,seeds=(8,),islands=6)
    altered=deepcopy(a)
    altered["executed_game_routes"]+=1000
    with pytest.raises(ExpeditionError,match="verified original"):
        compare_expedition_qa(a,altered)


def test_comparison_cannot_ignore_different_authoritative_source():
    a=run_expedition_qa("original",SOURCE,seeds=(8,),islands=6)
    b=run_expedition_qa("original","e"*64,seeds=(8,),islands=6)
    with pytest.raises(ExpeditionError,match="unrelated source"):
        compare_expedition_qa(a,b)


def test_nonfinite_weather_and_unbounded_scenario_are_refused():
    with pytest.raises(ExpeditionError,match="bounded weather"):
        QAScenario("bad",float("nan"),0,1,0)
    with pytest.raises(ExpeditionError,match="identity"):
        QAScenario("unscoped scenario",0,0,1,0)
