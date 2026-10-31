"""Dragon original game comparative and adversarial gameplay evidence."""
from copy import deepcopy
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile,author_archipelago,
)
from skeleton.jeeves.game_frontier_expedition_dragon import (
    observe_original_games,verify_dragon_report,
)
from skeleton.jeeves.game_frontier_expedition_campaign import original_campaign_player

SOURCE="f"*64


def worlds(count=4):
    return tuple(
        author_archipelago("game_"+str(i),SOURCE,ArchipelagoProfile(
            seed=70+i,islands=5,caverns=0,
        )) for i in range(count)
    )


def test_dragon_really_executes_four_objective_routes_per_game():
    games=worlds(3)
    player=original_campaign_player()
    report=observe_original_games(games,player)
    assert report["metrics"]["games_replayed"]==3
    assert report["metrics"]["verified_objective_routes"]==12
    assert report["metrics"]["route_alternatives"]>=3
    assert len(report["game_evidence"])==3
    for game in report["game_evidence"]:
        assert len(game["objective_outcomes"])==4
        assert all(
            route["first_reviewer"]==route["second_reviewer"]
            for route in game["objective_outcomes"]
        )
        assert not game["weight_training_completed"]
        assert not game["live_video_observed"]
    assert not report["training_weight_promotion_allowed"]
    assert not report["copyright_clearance_inferred"]


def test_dragon_independent_replay_and_exact_source_digest_repeat():
    games=worlds(2)
    player=original_campaign_player()
    first=observe_original_games(games,player)
    second=observe_original_games(games,player)
    assert first==second
    verify_dragon_report(first,games,player)


def test_dragon_rejects_forged_grades_and_modified_playthrough():
    games=worlds(1)
    player=original_campaign_player()
    report=observe_original_games(games,player)
    broken=deepcopy(report)
    broken["game_evidence"][0]["objective_outcomes"][0]["damage"]=777
    with pytest.raises(ExpeditionError,match="differs"):
        verify_dragon_report(broken,games,player)


@pytest.mark.parametrize("n",(0,11))
def test_dragon_never_exceeds_ten_original_games_per_batch(n):
    with pytest.raises(ExpeditionError,match="one to ten"):
        observe_original_games(worlds(n),original_campaign_player())


def test_dragon_rejects_duplicate_game_source_in_multiworld_comparison():
    base=worlds(1)[0]
    with pytest.raises(ExpeditionError,match="unique"):
        observe_original_games((base,base),original_campaign_player())


def test_actual_world_changes_invalidate_dragon_learning_receipt():
    games=worlds(1)
    report=observe_original_games(games,original_campaign_player())
    with pytest.raises(ExpeditionError,match="differs"):
        verify_dragon_report(report,worlds(2),original_campaign_player())


def test_dragon_evidence_does_not_claim_model_weight_training():
    report=observe_original_games(worlds(1),original_campaign_player())
    assert report["homebrew_only"]
    assert not report["training_weight_promotion_allowed"]
    assert not report["peer_review_satisfied"]
