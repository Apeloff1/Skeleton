"""Dragon's second-adversary review of real original game playthroughs."""
from copy import deepcopy
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile,author_archipelago,
)
from skeleton.jeeves.game_frontier_expedition_campaign import original_campaign_player
from skeleton.jeeves.game_frontier_expedition_dragon import observe_original_games
from skeleton.jeeves.game_frontier_expedition_dragon_review import (
    DragonAdversaryPolicy,adversarial_dragon_review,adversarial_attack_matrix,
)


def sources(n=2):
    return tuple(author_archipelago(
        "dragon_"+str(i),"f"*64,
        ArchipelagoProfile(seed=42+i,islands=5),
    ) for i in range(n))


def test_second_adversary_reexecutes_four_objectives_per_original_game():
    games=sources(2)
    player=original_campaign_player()
    first=observe_original_games(games,player)
    report=adversarial_dragon_review(first,games,player)
    assert report["independent_playthroughs"]==8
    assert len(report["replayed_route_evidence"])==8
    assert report["approved_for_verified_learning_notes"]
    assert not report["model_weights_updated"]
    assert not report["native_games_executed"]
    assert not report["external_peer_review_satisfied"]


def test_dragon_six_adversarial_receipt_and_authority_attacks_fail_closed():
    games=sources(1)
    player=original_campaign_player()
    first=observe_original_games(games,player)
    checked=adversarial_attack_matrix(first,games,player)
    assert checked["all_attacks_rejected"]
    assert len(checked["attacks"])==6
    assert set(checked["attacks"].values())=={"rejected"}
    assert len(checked["receipt_digest"])==64


def test_dragon_cannot_claim_a_foreign_or_more_positive_game_outcome():
    games=sources(1)
    player=original_campaign_player()
    original=observe_original_games(games,player)
    altered=deepcopy(original)
    altered["game_evidence"][0]["objective_outcomes"][0]["duration_s"]=0
    with pytest.raises(ExpeditionError,match="differs"):
        adversarial_dragon_review(altered,games,player)


def test_dragon_adversary_enforces_unique_game_source_isolation():
    games=sources(2)
    other=sources(1)
    player=original_campaign_player()
    report=observe_original_games(games,player)
    with pytest.raises(ExpeditionError):
        adversarial_dragon_review(report,other,player)


@pytest.mark.parametrize("params",(
    {"max_games":0},{"min_objectives":5},
    {"min_route_alternatives":0},{"require_source_isolation":"false"},
))
def test_invalid_dragon_opponent_policy_fails_closed(params):
    with pytest.raises(ExpeditionError):
        DragonAdversaryPolicy(**params)


def test_same_original_game_has_repeatable_two_pass_adversarial_receipts():
    games=sources(1)
    player=original_campaign_player()
    first=observe_original_games(games,player)
    a=adversarial_dragon_review(first,games,player)
    b=adversarial_dragon_review(first,games,player)
    assert a==b
    assert all(x["source_digest"]==games[0].digest for x in a["replayed_route_evidence"])
