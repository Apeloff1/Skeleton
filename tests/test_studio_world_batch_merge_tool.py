"""Jeeves typed world workflow merge routing and authority regression."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.ai.agents.jeeves.studio_world_batch_merge_tool import (
    REQUEST_SCHEMA, RESULT_SCHEMA, execute_world_batch_merge_tool,
    world_batch_merge_tool_schema,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_world_batch import compile_world_batch_plan
from skeleton.ai.game_builder.studio_world_batch_merge import replay_world_batch_merge
from tests.test_studio_world_batch_merge import fixture


def request():
    item, catalog = fixture()
    baseline = compile_world_batch_plan(
        [item], authorized=True, expected_catalog_digest=catalog)
    return {
        "schema": REQUEST_SCHEMA, "expected_catalog_digest": catalog,
        "baseline": baseline, "left": baseline, "right": baseline,
    }


def test_tool_is_statically_registered_and_not_a_write_permission():
    catalog = world_tool_catalog()
    descriptor = world_batch_merge_tool_schema()
    entry = next(row for row in catalog["tools"]
                 if row["name"] == descriptor["name"])
    assert entry["descriptor"] == descriptor
    assert entry["explicit_authoring_permission_required"] is False
    assert descriptor["parameters"]["additionalProperties"] is False


def test_typed_router_returns_source_replayed_merge_plan():
    args = request()
    direct = execute_world_batch_merge_tool(args, authorized=True)
    envelope = route_world_tool({
        "tool": "studio_original_world_batch_merge",
        "arguments": args,
    }, authorized=True, allow_authoring=False)
    assert envelope["result"] == direct
    assert envelope["file_write_performed"] is False
    assert direct["schema"] == RESULT_SCHEMA
    assert direct["release_certified"] is False
    assert replay_world_batch_merge(
        direct["merge"], args["baseline"], args["left"], args["right"],
        authorized=True,
    ) == direct["merge"]


def test_forged_authority_and_stale_catalog_are_rejected():
    args = request()
    with pytest.raises(PermissionError):
        execute_world_batch_merge_tool(args, authorized=False)
    with pytest.raises(StudioQuestError):
        execute_world_batch_merge_tool(
            {**args, "expected_catalog_digest": "0" * 64},
            authorized=True,
        )
    with pytest.raises(StudioQuestError):
        execute_world_batch_merge_tool(
            {**args, "allow_authoring": True}, authorized=True,
        )
    with pytest.raises(StudioQuestError):
        route_world_tool({
            "tool": "studio_original_world_batch_merge",
            "arguments": {**args, "authorized": True},
        }, authorized=True)


def test_forged_source_and_ancestor_edits_rejected():
    args = request()
    forged = deepcopy(args)
    forged["left"]["plan_digest"] = "0" * 64
    with pytest.raises(StudioQuestError):
        execute_world_batch_merge_tool(forged, authorized=True)
    forged = deepcopy(args)
    forged["baseline"]["provenance"]["projects"] = []
    with pytest.raises(StudioQuestError):
        execute_world_batch_merge_tool(forged, authorized=True)
