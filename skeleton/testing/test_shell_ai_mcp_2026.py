"""MCP-2026 AI shell tool surface, authorization, tasks, and gateway tests."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.manifest import build_manifest
from skeleton.shells.ai.mcp import (
    MCP_PROTOCOL_REVISION,
    MCPRequestEnvelope,
    MCPResponseEnvelope,
    MCPToolSurface,
)
from skeleton.shells.ai.mcp_authz import MCPAuthorization, MCPPrincipalPolicy
from skeleton.shells.ai.mcp_gateway import MCPAIShellGateway
from skeleton.shells.ai.mcp_tasks import MCPTaskRegistry, MCPTaskState
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.registry import ExecutableSpec


def catalog():
    return CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec(
                    "python",
                    sys.executable,
                    tags=frozenset({"inspect", "test"}),
                ),
                ArgumentPolicy.allow_any(),
                description="Bounded Python tool.",
            ),
        )
    )


def effects():
    return EffectRegistry(
        (
            EffectContract(
                "python",
                frozenset({EffectKind.READ_FILESYSTEM}),
                idempotent=True,
                reversible=True,
            ),
        )
    )


def surface():
    return MCPToolSurface(build_manifest(AIToolCatalog(catalog()), effects()))


def test_mcp_revision_is_current_2026_surface():
    assert MCP_PROTOCOL_REVISION == "2026-07-28"


def test_mcp_tool_list_is_deterministic():
    tools = surface()
    first = tools.list_tools()
    second = tools.list_tools()
    assert first.digest == second.digest
    assert [item.name for item in first.tools] == ["python"]


def test_mcp_tool_list_has_cache_hints():
    tools = MCPToolSurface(
        build_manifest(AIToolCatalog(catalog()), effects()),
        ttl_ms=5000,
        cache_scope="private",
    )
    listing = tools.list_tools()
    assert listing.ttl_ms == 5000
    assert listing.cache_scope == "private"


def test_mcp_tool_descriptor_omits_host_path():
    listing = surface().list_tools()
    assert sys.executable not in str(listing.to_dict())


def test_mcp_tool_descriptor_uses_object_input_schema():
    descriptor = surface().descriptors()[0]
    assert descriptor.input_schema["type"] == "object"
    assert descriptor.output_schema["type"] == "object"


def test_mcp_tool_descriptor_contains_effect_annotations():
    descriptor = surface().descriptors()[0]
    assert descriptor.annotations["effects"] == ["read_filesystem"]
    assert descriptor.annotations["idempotent"] is True
    assert descriptor.annotations["reversible"] is True


def test_mcp_request_routing_headers():
    request = MCPRequestEnvelope(
        "r",
        "tools/call",
        "python",
        {"args": ["-V"]},
    )
    assert request.routing_headers == {
        "Mcp-Method": "tools/call",
        "Mcp-Name": "python",
    }


def test_mcp_request_copies_arguments():
    args = {"args": ["-V"]}
    request = MCPRequestEnvelope("r", "tools/call", "python", args)
    args["args"] = ["changed"]
    assert request.arguments["args"] == ["-V"]


def test_mcp_response_success_cannot_contain_error():
    with pytest.raises(ValueError):
        MCPResponseEnvelope(
            "r",
            True,
            {},
            error_code="bad",
        )


def test_mcp_auth_unknown_principal_denied():
    auth = MCPAuthorization()
    decision = auth.inspect("unknown", "python")
    assert not decision.allowed


def test_mcp_auth_allowlist():
    auth = MCPAuthorization()
    auth.set(
        MCPPrincipalPolicy(
            "alice",
            allowed_tools=frozenset({"python"}),
        )
    )
    assert auth.inspect("alice", "python").allowed
    assert not auth.inspect("alice", "git").allowed


def test_mcp_auth_denylist_precedes_open_allowlist():
    auth = MCPAuthorization()
    auth.set(
        MCPPrincipalPolicy(
            "alice",
            denied_tools=frozenset({"python"}),
        )
    )
    assert not auth.inspect("alice", "python").allowed


def test_mcp_auth_timeout_ceiling():
    auth = MCPAuthorization()
    auth.set(
        MCPPrincipalPolicy(
            "alice",
            allowed_tools=frozenset({"python"}),
            max_timeout_seconds=2,
        )
    )
    assert auth.inspect("alice", "python", timeout_seconds=2).allowed
    assert not auth.inspect("alice", "python", timeout_seconds=3).allowed


def test_mcp_auth_require_raises():
    auth = MCPAuthorization()
    with pytest.raises(PermissionError):
        auth.require("alice", "python")


def test_mcp_gateway_prepares_structured_action_only():
    auth = MCPAuthorization()
    auth.set(
        MCPPrincipalPolicy(
            "alice",
            allowed_tools=frozenset({"python"}),
        )
    )
    gateway = MCPAIShellGateway(surface(), auth)
    request = MCPRequestEnvelope(
        "call-1",
        "tools/call",
        "python",
        {
            "args": ["-V"],
            "cwd": None,
            "environmentRefs": {},
            "timeoutSeconds": 1,
            "purpose": "inspect runtime",
        },
    )
    prepared = gateway.prepare_call(request, principal="alice")
    assert prepared.action.command == "python"
    assert prepared.action.args == ("-V",)
    assert prepared.principal == "alice"


def test_mcp_gateway_rejects_unknown_tool():
    auth = MCPAuthorization()
    auth.set(MCPPrincipalPolicy("alice"))
    gateway = MCPAIShellGateway(surface(), auth)
    request = MCPRequestEnvelope(
        "call-1",
        "tools/call",
        "missing",
        {},
    )
    with pytest.raises(KeyError):
        gateway.prepare_call(request, principal="alice")


def test_mcp_gateway_rejects_wrong_method():
    auth = MCPAuthorization()
    auth.set(MCPPrincipalPolicy("alice"))
    gateway = MCPAIShellGateway(surface(), auth)
    request = MCPRequestEnvelope(
        "call-1",
        "resources/read",
        "python",
        {},
    )
    with pytest.raises(ValueError):
        gateway.prepare_call(request, principal="alice")


def test_mcp_gateway_rejects_protocol_mismatch():
    auth = MCPAuthorization()
    auth.set(MCPPrincipalPolicy("alice"))
    gateway = MCPAIShellGateway(surface(), auth)
    request = MCPRequestEnvelope(
        "call-1",
        "tools/call",
        "python",
        {},
        protocol_revision="2025-01-01",
    )
    with pytest.raises(ValueError):
        gateway.prepare_call(request, principal="alice")


def test_mcp_gateway_list_tools_is_response_only():
    auth = MCPAuthorization()
    gateway = MCPAIShellGateway(surface(), auth)
    response = gateway.list_tools()
    assert response.ok
    assert response.result["protocolRevision"] == MCP_PROTOCOL_REVISION
    assert response.result["tools"]


def test_mcp_task_create_is_pending():
    registry = MCPTaskRegistry()
    task = registry.create(
        request_id="r",
        principal="alice",
        tool="python",
        correlation_id="c",
    )
    assert task.state is MCPTaskState.PENDING
    assert task.progress == 0


def test_mcp_task_running_to_success():
    registry = MCPTaskRegistry()
    task = registry.create(
        request_id="r",
        principal="alice",
        tool="python",
    )
    running = registry.update(
        task.task_id,
        state=MCPTaskState.RUNNING,
        progress=0.5,
    )
    assert running.state is MCPTaskState.RUNNING
    done = registry.update(
        task.task_id,
        state=MCPTaskState.SUCCEEDED,
    )
    assert done.state is MCPTaskState.SUCCEEDED
    assert done.progress == 1.0


def test_mcp_task_terminal_is_immutable():
    registry = MCPTaskRegistry()
    task = registry.create(
        request_id="r",
        principal="alice",
        tool="python",
    )
    registry.update(task.task_id, state=MCPTaskState.CANCELLED)
    with pytest.raises(RuntimeError):
        registry.update(task.task_id, progress=0.5)


def test_mcp_task_invalid_pending_to_success():
    registry = MCPTaskRegistry()
    task = registry.create(
        request_id="r",
        principal="alice",
        tool="python",
    )
    with pytest.raises(RuntimeError):
        registry.update(task.task_id, state=MCPTaskState.SUCCEEDED)


def test_mcp_tasks_do_not_start_background_work():
    registry = MCPTaskRegistry()
    task = registry.create(
        request_id="r",
        principal="alice",
        tool="python",
    )
    assert registry.get(task.task_id).state is MCPTaskState.PENDING
    assert len(registry.snapshot()) == 1
