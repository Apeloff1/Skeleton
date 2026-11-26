"""A source budget cannot mint or spend more than its starting quantity."""
from dataclasses import replace
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_resources import (
    start_resources, transfer_resources, resource_receipt, verify_resources, resource_label,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

@pytest.mark.parametrize("pid", [
 "studio_aerial_traversal_amber_highlands",
 "studio_puzzle_expedition_copper_mesa",
 "studio_arena_fighting_glacial_fjord",
])
def test_source_budget_is_conserved(pid):
    docs=read_blueprint(pid)
    assert resource_label(docs)
    session=start_resources(docs,starting_quantity=8,authorized=True)
    next_session=transfer_resources(session,docs,source="reserve",target="spent",
                                    quantity=3,authorized=True)
    report=resource_receipt(next_session,docs)
    assert report["balances"] == {"reserve":5,"spent":3}
    assert report["initial_supply_externally_verified"] is False
    with pytest.raises(StudioQuestError):
        transfer_resources(next_session,docs,source="reserve",target="spent",
                           quantity=6,authorized=True)
    with pytest.raises(StudioQuestError):
        verify_resources(replace(next_session,digest="0"*64),docs)
    with pytest.raises(PermissionError):
        start_resources(docs,starting_quantity=10,authorized=False)
