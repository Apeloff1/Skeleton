"""Alternative route exploration must not overclaim bounded completeness."""
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_route_coverage import (
    explore_quest_routes,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


@pytest.mark.parametrize("project", [
    "studio_puzzle_expedition_copper_mesa",
    "studio_arena_fighting_glacial_fjord",
])
def test_both_quest_source_families_enumerate_eight_choices(project):
    documents = read_blueprint(project)
    report = explore_quest_routes(documents, authorized=True)
    assert report["terminal_routes_examined"] == 8
    assert report["unique_terminal_routes"] == 8
    assert report["coverage_complete"]
    assert not report["truncated_by_resource_budget"]
    assert report["sample_replay"]["project_id"] == project
    assert report["release_certified"] is False


def test_resource_limit_marks_partial_coverage_instead_of_silent_pass():
    docs = read_blueprint("studio_arena_fighting_glacial_fjord")
    limited = explore_quest_routes(docs, authorized=True, max_terminal_routes=2)
    assert limited["terminal_routes_examined"] == 2
    assert not limited["coverage_complete"]
    assert limited["truncated_by_resource_budget"]
    with pytest.raises(StudioQuestError):
        explore_quest_routes(docs, authorized=True, max_terminal_routes=True)
    with pytest.raises(PermissionError):
        explore_quest_routes(docs, authorized=False)
