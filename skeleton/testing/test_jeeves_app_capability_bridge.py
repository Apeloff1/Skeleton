"""Jeeves can index the real app and propose creator actions without bypassing grants."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.jeeves.app_capability_bridge import (
    AppCapabilityBridgeError, capability_catalog, creator_operation_catalog,
    creator_proposal, register_app_tools,
)
from skeleton.jeeves.agent.tools import ToolDenied, ToolExecutor, ToolExecutionContext, ToolGrant
from skeleton.jeeves.agent.types import RiskTier, ToolCall
from skeleton.jeeves.core import Jeeves


def test_index_is_deterministic_paged_and_non_authoritative():
    a = capability_catalog(limit=7)
    b = capability_catalog(limit=7)
    assert a == b
    assert a["total_indexed"] >= 100
    assert a["interface_contracts"] > 0
    assert a["execution_authority"] == "none"
    assert len(a["capabilities"]) == 7
    assert len({item["id"] for item in a["capabilities"]}) == 7
    next_page = capability_catalog(limit=7, offset=7)
    assert not {item["id"] for item in a["capabilities"]} & {
        item["id"] for item in next_page["capabilities"]
    }
    narrowed = capability_catalog(query="skeleton/jeeves", limit=15)
    assert narrowed["total_matched"] >= 1
    assert all("jeeves" in (row["source"] + row["destination"]) for row in narrowed["capabilities"])


@pytest.mark.parametrize("inputs", [
    {"limit": 0}, {"limit": 100000}, {"limit": True},
    {"offset": -1}, {"offset": 10**9}, {"query": "x"*161},
])
def test_index_fails_closed_on_unbounded_requests(inputs):
    with pytest.raises(AppCapabilityBridgeError):
        capability_catalog(**inputs)


def test_creator_proposal_is_typed_and_nonexecuting():
    proposal = creator_proposal(
        "edit", "quest-studio", {"target_id": "npc:merchant",
        "expected_revision": 2, "patch": {"dialogue": "Welcome"}}
    )
    assert proposal["command"]["operation"] == "edit"
    assert len(proposal["command"]["digest"]) == 64
    assert proposal["dispatch_performed"] is False
    assert proposal == creator_proposal(
        "edit", "quest-studio", {"target_id": "npc:merchant",
        "expected_revision": 2, "patch": {"dialogue": "Welcome"}}
    )
    catalog = creator_operation_catalog()
    assert catalog["execution_authority"] == "none"
    assert len(catalog["catalog"]["operations"]) == 5


def test_jeeves_host_registry_exposes_only_read_only_tools():
    jeeves = Jeeves()
    registry = jeeves.app_tool_registry()
    names = {s.name for s in registry.specs()}
    assert names == {"app.capabilities", "creator.operations", "creator.propose"}
    assert all(s.risk is RiskTier.READ_ONLY for s in registry.specs())
    assert jeeves.app_capability_catalog(limit=1)["capabilities"]
    assert jeeves.creator_proposal("preview", "quest-studio", {
        "scopes": ["npc:merchant"], "mode": "static"})["execution_authority"] == "none"

    executor = ToolExecutor(registry)
    context = ToolExecutionContext(run_id="run-001", user_id="user-001", trace_id="trace-001")
    call = ToolCall(call_id="call-001", name="app.capabilities", arguments={"limit": 1})
    with pytest.raises(ToolDenied):
        executor.execute(call, context, grants=[])
    outcome = executor.execute(call, context, grants=[
        ToolGrant(tool_name="app.capabilities", allowed_risks=(RiskTier.READ_ONLY,))
    ])
    assert outcome.ok
    assert outcome.payload["limit"] == 1
    # Even an explicit high-risk grant cannot install an absent file editor.
    with pytest.raises(ToolDenied):
        executor.execute(
            ToolCall(call_id="call-002", name="app.write_file",
                     arguments={"path": "docs/PRODUCT.md", "content": "evil"}),
            context, grants=[ToolGrant(tool_name="app.write_file",
                                      allowed_risks=(RiskTier.HIGH_IMPACT,))],
        )


def test_repo_root_is_host_selected_not_a_model_path(tmp_path):
    with pytest.raises(AppCapabilityBridgeError):
        capability_catalog(root=tmp_path)
    registry = Jeeves().app_tool_registry()
    with pytest.raises(Exception):
        # ToolSpec does not accept unknown parameters such as "root".
        registry.get("app.capabilities").spec.validate_arguments({"root": "/etc"})
