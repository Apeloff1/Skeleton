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
    assert names == {"app.capabilities", "app.concepts", "creator.operations", "creator.propose"}
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


def test_explicit_host_authorization_and_high_impact_grant_are_both_required():
    from skeleton.jeeves.app_capability_bridge import register_authorized_creator_tool

    registry = Jeeves().app_tool_registry()
    called = []
    approved = set()

    def handler(command):
        called.append(command.digest)
        return {"status": "validated", "project": command.project_id}

    def authorize(command, context):
        return (command.digest, context.user_id, context.run_id) in approved

    register_authorized_creator_tool(registry, handlers={"preview": handler}, authorize=authorize)
    executor = ToolExecutor(registry)
    ctx = ToolExecutionContext(run_id="run-002", user_id="user-002", trace_id="trace-002")
    args = {"operation": "preview", "project_id": "studio",
            "payload": {"scopes": ["world:start"], "mode": "static"}}
    grant = ToolGrant(tool_name="creator.execute_authorized",
                      allowed_risks=(RiskTier.HIGH_IMPACT,), max_calls=1)
    with pytest.raises(ToolDenied):
        executor.execute(
            ToolCall(call_id="attempt-no-grant", name="creator.execute_authorized", arguments=args),
            ctx, grants=[])
    assert not called
    denied = executor.execute(
        ToolCall(call_id="attempt-unapproved", name="creator.execute_authorized", arguments=args),
        ctx, grants=[grant])
    assert denied.ok is False
    assert not called

    # Approval alone cannot overcome an exhausted exact-run ToolGrant.
    cmd = creator_proposal("preview", "studio", args["payload"])["command"]
    approved.add((cmd["digest"], ctx.user_id, ctx.run_id))
    with pytest.raises(ToolDenied):
        executor.execute(
            ToolCall(call_id="attempt-exhausted", name="creator.execute_authorized", arguments=args),
            ctx, grants=[grant])
    assert not called

    # Fresh run and host-approved exact command gets a fresh grant.
    fresh = ToolExecutionContext(run_id="run-003", user_id="user-002", trace_id="trace-003")
    approved.add((cmd["digest"], fresh.user_id, fresh.run_id))
    outcome = executor.execute(
        ToolCall(call_id="attempt-approved", name="creator.execute_authorized", arguments=args),
        fresh, grants=[grant])
    assert outcome.ok is True
    assert called == [cmd["digest"]]
    assert outcome.payload["command_digest"] == cmd["digest"]


def test_authorization_callback_cannot_be_supplied_in_model_arguments():
    from skeleton.jeeves.app_capability_bridge import register_authorized_creator_tool
    registry = Jeeves().app_tool_registry()
    register_authorized_creator_tool(
        registry, handlers={"preview": lambda command: {}},
        authorize=lambda command, context: False)
    spec = registry.get("creator.execute_authorized").spec
    from skeleton.jeeves.agent.tools import ToolValidationError
    with pytest.raises(ToolValidationError):
        spec.validate_arguments({
            "operation": "preview", "project_id": "game",
            "payload": {"scopes": ["scene"], "mode": "static"},
            "authorize": True,
        })


def test_authorized_tool_requires_explicit_host_handlers():
    from skeleton.jeeves.app_capability_bridge import register_authorized_creator_tool
    with pytest.raises(TypeError):
        register_authorized_creator_tool(
            Jeeves().app_tool_registry(), handlers={}, authorize=lambda *_: True)


def test_capability_taxonomy_is_paged_and_never_claims_runtime_verification():
    from skeleton.jeeves.app_capability_bridge import capability_concepts
    first = capability_concepts(limit=12)
    again = capability_concepts(limit=12)
    assert first == again
    assert first["total_declared"] >= 1000
    assert first["execution_authority"] == "none"
    assert all(item["implementation_verified"] is False for item in first["concepts"])
    other = capability_concepts(limit=12, offset=12)
    assert not {x["concept_id"] for x in first["concepts"]} & {
        x["concept_id"] for x in other["concepts"]}
    assert Jeeves().app_capability_concepts(limit=1)["concepts"]
    for bad in ({"limit": False}, {"limit": 0}, {"limit": 65}, {"query": "q"*161}):
        with pytest.raises(AppCapabilityBridgeError):
            capability_concepts(**bad)


def test_capability_concept_tool_is_host_granted_and_nonexecuting():
    registry = Jeeves().app_tool_registry()
    executor = ToolExecutor(registry)
    ctx = ToolExecutionContext(run_id="concept-001", user_id="user-003", trace_id="trace-003")
    call = ToolCall(call_id="concept-call", name="app.concepts", arguments={"limit": 3})
    with pytest.raises(ToolDenied):
        executor.execute(call, ctx, grants=[])
    result = executor.execute(call, ctx, grants=[ToolGrant(tool_name="app.concepts")])
    assert result.ok is True
    assert len(result.payload["concepts"]) == 3
    assert result.payload["validation"].startswith("taxonomy declaration")
