"""Quest status must be earned by actual replay, not supplied by a client."""
from skeleton.game.gameplay.ridge_rescue.acceptance import run_acceptance
from skeleton.game.gameplay.ridge_rescue.custody import verify_run
from skeleton.game.gameplay.ridge_rescue.quests import progress

def test_protect_quest_chain_is_earned():
    bundle = run_acceptance("protect")
    verified = verify_run(bundle)
    earned = progress(verified["world"], verified["state"])
    assert earned["earned"]["first_supply"]
    assert earned["earned"]["field_crafting"]
    assert earned["earned"]["first_rescue"]
    assert earned["earned"]["all_rescued"]
    assert earned["earned"]["beacon_lit"]
    assert earned["earned"]["protect_ending"]
    assert not earned["earned"]["salvage_ending"]

def test_salvage_does_not_claim_protection():
    verified = verify_run(run_acceptance("salvage"))
    earned = progress(verified["world"], verified["state"])
    assert earned["earned"]["salvage_ending"]
    assert not earned["earned"]["protect_ending"]
    assert not earned["earned"]["beacon_lit"]
