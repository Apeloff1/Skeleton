"""Factions update from exact authored social rules, not inferred consequences."""
import pytest
from copy import deepcopy
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_social import compile_factions, replay_factions
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

@pytest.mark.parametrize("pid,choice,affected",[
    ("studio_aerial_traversal_amber_highlands", "disclose_proof", "settlers"),
    ("studio_puzzle_expedition_copper_mesa", "publish_records", "residents"),
    ("studio_arena_fighting_glacial_fjord", "publish_ledger", "residents"),
])
def test_replay_three_authored_social_contracts(pid,choice,affected):
    docs = read_blueprint(pid)
    base = dict(compile_factions(docs).factions)
    result = replay_factions(docs,[choice],authorized=True)
    assert result["reputation"][affected] == base[affected]+2
    assert result == replay_factions(docs,[choice],authorized=True)
    assert result["release_certified"] is False
    with pytest.raises(StudioQuestError):
        replay_factions(docs,["unregistered"],authorized=True)
    with pytest.raises(PermissionError):
        replay_factions(docs,[choice],authorized=False)

def test_social_source_tamper_and_boolean_delta_rejected():
    docs = deepcopy(read_blueprint("studio_arena_fighting_glacial_fjord"))
    docs["cast"]["social_rules"][0]["reputation_delta"]["residents"] = True
    with pytest.raises(StudioQuestError):
        compile_factions(docs)
