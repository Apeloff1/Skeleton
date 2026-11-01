"""Adversarial source-provenance and receipt custody for Jeeves world batches."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_world_batch_provenance import (
    compile_world_batch_provenance, replay_world_batch_provenance,
    verify_world_batch_step,
)
from skeleton.ai.game_builder.studio_world_batch import (
    compile_world_batch_plan, execute_world_batch,
    replay_world_batch_execution, replay_world_batch_plan,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
from skeleton.ai.agents.jeeves.studio_walk_tool import faction_reputation_tool_schema
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source


PROJECT = "studio_arena_fighting_glacial_fjord"


def _fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    descriptor = faction_reputation_tool_schema()
    request = {
        "tool": descriptor["name"],
        "arguments": {
            "schema": descriptor["parameters"]["properties"]["schema"]["const"],
            "project_id": PROJECT, "expected_source_digest": source,
            "decisions": [],
        },
    }
    return request, world_tool_catalog()["catalog_digest"]


def test_manifest_binds_original_source_before_and_after_tool_execution():
    request, catalog = _fixture()
    manifest = compile_world_batch_provenance([request], authorized=True)
    assert manifest["project_count"] == 1
    assert manifest["step_bindings"][0]["source_digest"] == request["arguments"]["expected_source_digest"]
    assert replay_world_batch_provenance(manifest, [request], authorized=True) == manifest
    plan = compile_world_batch_plan([request], authorized=True,
                                    expected_catalog_digest=catalog)
    assert plan["provenance"] == manifest
    assert replay_world_batch_plan(plan, authorized=True) == plan
    execution = execute_world_batch(plan, authorized=True)
    assert execution["provenance"] == manifest
    assert replay_world_batch_execution(execution, authorized=True) == execution
    assert execution["file_write_performed"] is False
    assert execution["release_certified"] is False


def test_multiple_steps_share_source_without_conflating_request_identity():
    request, catalog = _fixture()
    second = deepcopy(request)
    second["arguments"]["decisions"] = []
    plan = compile_world_batch_plan([request, second], authorized=True,
                                    expected_catalog_digest=catalog)
    assert plan["provenance"]["project_count"] == 1
    assert plan["provenance"]["step_count"] == 2
    assert plan["provenance"]["step_bindings"][0]["ordinal"] == 0
    assert plan["provenance"]["step_bindings"][1]["ordinal"] == 1


def test_stale_source_and_mutated_manifest_fail_before_any_tool_runs():
    request, catalog = _fixture()
    forged = deepcopy(request)
    forged["arguments"]["expected_source_digest"] = "0" * 64
    with pytest.raises(StudioQuestError):
        compile_world_batch_provenance([forged], authorized=True)
    with pytest.raises(StudioQuestError):
        compile_world_batch_plan([forged], authorized=True,
                                 expected_catalog_digest=catalog)
    manifest = compile_world_batch_provenance([request], authorized=True)
    for mutation in (
        {"project_count": 0},
        {"manifest_digest": "0" * 64},
        {"source_replay_required": False},
        {"projects": []},
        {"step_bindings": []},
    ):
        altered = {**manifest, **mutation}
        with pytest.raises(StudioQuestError):
            replay_world_batch_provenance(altered, [request], authorized=True)


def test_router_and_result_forgery_are_rejected():
    request, _ = _fixture()
    manifest = compile_world_batch_provenance([request], authorized=True)
    binding = manifest["step_bindings"][0]
    receipt = route_world_tool(request, authorized=True)
    verify_world_batch_step(request, receipt, binding, authorized=True)
    mutations = (
        {"request_digest": "0" * 64},
        {"receipt_digest": "0" * 64},
        {"result_digest": "0" * 64},
        {"file_write_performed": True},
        {"release_certified": True},
    )
    for mutation in mutations:
        with pytest.raises(StudioQuestError):
            verify_world_batch_step(request, {**receipt, **mutation},
                                    binding, authorized=True)
    for mutation in (
        {"project_id": "another_world"},
        {"file_write_performed": True},
        {"release_certified": True},
        {"source_replay_verified": False},
    ):
        altered = deepcopy(receipt)
        altered["result"].update(mutation)
        with pytest.raises(StudioQuestError):
            verify_world_batch_step(request, altered, binding, authorized=True)


def test_permissions_and_malformed_identity_fail_closed():
    request, _ = _fixture()
    for invalid in (
        None, [], {}, {"tool": request["tool"], "arguments": {}},
        {"tool": request["tool"], "arguments": {
            **request["arguments"], "project_id": "\x00bad"}},
    ):
        with pytest.raises((StudioQuestError, TypeError, ValueError)):
            compile_world_batch_provenance([invalid], authorized=True)
    with pytest.raises(PermissionError):
        compile_world_batch_provenance([request], authorized=False)
    with pytest.raises(PermissionError):
        replay_world_batch_provenance({}, [request], authorized=False)
    with pytest.raises(PermissionError):
        verify_world_batch_step(request, {}, {}, authorized=False)
