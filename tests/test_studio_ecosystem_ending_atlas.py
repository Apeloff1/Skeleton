"""Canonical ending atlas: exact source/session custody, replay and typed parity."""
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_ending_atlas import (
    ENDING_ATLAS_SCHEMA, build_ending_atlas,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, replay_quest,
)
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    ENDING_ATLAS_REQUEST_SCHEMA, execute_ending_atlas_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    digest = audit_canon_source(docs, authorized=True)["source_digest"]
    return docs, digest


def test_atlas_replays_every_authored_ending_without_claiming_delivery():
    docs, source = fixture()
    before = json.dumps(docs, sort_keys=True)
    session = replay_quest(docs, [], authorized=True)
    atlas = build_ending_atlas(
        docs, [], authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest)
    assert atlas["schema"] == ENDING_ATLAS_SCHEMA
    assert atlas["ending_count"] == len(docs["narrative"]["endings"])
    assert atlas["ending_count"] > 0
    assert atlas["simulatable_count"] + atlas["external_hold_count"] == atlas["ending_count"]
    assert all(not card["choice_to_ending_causality_verified"] for card in atlas["endings"])
    assert all(not card["external_evidence_verified"] for card in atlas["endings"])
    assert atlas["release_certified"] is False
    assert atlas["file_write_performed"] is False
    assert atlas == build_ending_atlas(
        docs, [], authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest)
    assert json.dumps(docs, sort_keys=True) == before


def test_pairwise_routes_are_symmetric_and_never_invent_branch_causality():
    docs, source = fixture()
    atlas = build_ending_atlas(
        docs, [], authorized=True, expected_source_digest=source)
    cards = {c["ending_id"]: c for c in atlas["endings"]}
    assert len(atlas["route_overlap"]) == len(cards) * (len(cards) - 1) // 2
    for row in atlas["route_overlap"]:
        left = set(cards[row["left_ending_id"]]["stage_route"])
        right = set(cards[row["right_ending_id"]]["stage_route"])
        assert set(row["shared_required_stages"]) == left & right
        assert set(row["left_only_stages"]) == left - right
        assert set(row["right_only_stages"]) == right - left
        assert row["choice_alternative_causality_verified"] is False


@pytest.mark.parametrize("override", [
    {"expected_source_digest": "0" * 64},
    {"expected_source_digest": True},
    {"expected_source_digest": "Z" * 64},
    {"expected_session_digest": "0" * 64},
    {"expected_session_digest": True},
    {"actions": [["forged", "not-authored"]]},
    {"actions": [True]},
])
def test_invalid_leases_and_actions_fail_closed(override):
    docs, source = fixture()
    args = dict(authorized=True, expected_source_digest=source)
    actions = override.pop("actions", [])
    args.update(override)
    with pytest.raises(StudioQuestError):
        build_ending_atlas(docs, actions, **args)


def test_operator_authority_required():
    docs, source = fixture()
    with pytest.raises(PermissionError):
        build_ending_atlas(
            docs, [], authorized=False, expected_source_digest=source)


def test_typed_jeeves_and_cli_emit_identical_canonical_atlas(capsys):
    from scripts.studio_ecosystem_cli import main
    docs, source = fixture()
    request = {
        "schema": ENDING_ATLAS_REQUEST_SCHEMA,
        "project_id": PROJECT, "expected_source_digest": source,
        "actions": [],
    }
    typed = execute_ending_atlas_tool(request, authorized=True)
    assert main([
        "--project", PROJECT, "--ending-atlas",
        "--ending-atlas-expected-source", source,
        "--quest-actions", "[]",
    ]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_ending_atlas_tool({**request, "forged": 1}, authorized=True)
    with pytest.raises(PermissionError):
        execute_ending_atlas_tool(request, authorized=False)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--ending-atlas"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--ending-atlas",
              "--ending-atlas-expected-source", source, "--ending-plan"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--ending-atlas",
              "--ending-atlas-expected-source", source,
              "--quest-actions", '{"forged":true}'])
