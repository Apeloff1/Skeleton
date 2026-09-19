"""Distributed seal/idempotency and MCP discovery/transport tests."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.distributed_idempotency import DistributedAIIdempotencyRegistry
from skeleton.shells.ai.distributed_seal import DistributedExecutionSealRegistry
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.execution_seal import ExecutionSealAuthority
from skeleton.shells.ai.idempotency import AIIdempotencyConflict
from skeleton.shells.ai.manifest import build_manifest
from skeleton.shells.ai.mcp import MCPRequestEnvelope, MCPToolSurface
from skeleton.shells.ai.mcp_authz import MCPAuthorization, MCPPrincipalPolicy
from skeleton.shells.ai.mcp_discovery import MCPPrincipalDiscovery
from skeleton.shells.ai.mcp_transport import MCPTransportPolicy, MCPTransportValidator
from skeleton.shells.ai.seal_registry import SealReplay
from skeleton.shells.ai.stale_guard import PlanPin
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.registry import ExecutableSpec


def fp(char):
    return char * 64


def pin():
    return PlanPin(
        fp("a"),
        fp("b"),
        fp("c"),
        fp("d"),
        fp("e"),
        fp("f"),
        fp("1"),
    )


def surface():
    commands = CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec("python", sys.executable),
                ArgumentPolicy.allow_any(),
                description="python",
            ),
            CommandDefinition(
                ExecutableSpec("inspect", sys.executable),
                ArgumentPolicy.allow_any(),
                description="inspect",
            ),
        )
    )
    effects = EffectRegistry(
        (
            EffectContract(
                "python",
                frozenset({EffectKind.PROCESS_CONTROL}),
                reversible=True,
            ),
            EffectContract(
                "inspect",
                frozenset({EffectKind.READ_FILESYSTEM}),
                reversible=True,
            ),
        )
    )
    return MCPToolSurface(build_manifest(AIToolCatalog(commands), effects))


def test_distributed_seal_consumed_globally_across_instances():
    backend = InMemoryFencedStore()
    authority = ExecutionSealAuthority(b"k" * 32)
    left = DistributedExecutionSealRegistry(authority, backend)
    right = DistributedExecutionSealRegistry(authority, backend)
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
    )
    left.consume(
        seal,
        principal="alice",
        session_id="s",
        plan_pin=pin(),
    )
    with pytest.raises(SealReplay):
        right.consume(
            seal,
            principal="alice",
            session_id="s",
            plan_pin=pin(),
        )


def test_distributed_seal_used_visible_cross_instance():
    backend = InMemoryFencedStore()
    authority = ExecutionSealAuthority(b"k" * 32)
    left = DistributedExecutionSealRegistry(authority, backend)
    right = DistributedExecutionSealRegistry(authority, backend)
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
    )
    assert not right.used(seal.seal_id)
    left.consume(
        seal,
        principal="alice",
        session_id="s",
        plan_pin=pin(),
    )
    assert right.used(seal.seal_id)


def test_distributed_seal_invalid_binding_does_not_consume():
    backend = InMemoryFencedStore()
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = DistributedExecutionSealRegistry(authority, backend)
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
    )
    with pytest.raises(Exception):
        registry.consume(
            seal,
            principal="bob",
            session_id="s",
            plan_pin=pin(),
        )
    assert not registry.used(seal.seal_id)


def test_distributed_idempotency_same_request_cross_instance():
    backend = InMemoryFencedStore()
    left = DistributedAIIdempotencyRegistry(backend)
    right = DistributedAIIdempotencyRegistry(backend)
    first = left.register(
        "key",
        request_digest=fp("a"),
        proposal_fingerprint=fp("b"),
    )
    second = right.register(
        "key",
        request_digest=fp("a"),
        proposal_fingerprint=fp("b"),
    )
    assert first.request_digest == second.request_digest
    assert first.proposal_fingerprint == second.proposal_fingerprint


def test_distributed_idempotency_conflicting_request():
    backend = InMemoryFencedStore()
    left = DistributedAIIdempotencyRegistry(backend)
    right = DistributedAIIdempotencyRegistry(backend)
    left.register(
        "key",
        request_digest=fp("a"),
        proposal_fingerprint=fp("b"),
    )
    with pytest.raises(AIIdempotencyConflict):
        right.register(
            "key",
            request_digest=fp("c"),
            proposal_fingerprint=fp("b"),
        )


def test_distributed_idempotency_conflicting_proposal():
    backend = InMemoryFencedStore()
    registry = DistributedAIIdempotencyRegistry(backend)
    registry.register(
        "key",
        request_digest=fp("a"),
        proposal_fingerprint=fp("b"),
    )
    with pytest.raises(AIIdempotencyConflict):
        registry.register(
            "key",
            request_digest=fp("a"),
            proposal_fingerprint=fp("c"),
        )


def test_distributed_idempotency_expired_record_replaced():
    now = [0.0]
    backend = InMemoryFencedStore(clock=lambda: now[0])
    registry = DistributedAIIdempotencyRegistry(
        backend,
        clock=lambda: now[0],
    )
    first = registry.register(
        "key",
        request_digest=fp("a"),
        proposal_fingerprint=fp("b"),
        ttl_seconds=1,
    )
    now[0] = 1
    second = registry.register(
        "key",
        request_digest=fp("c"),
        proposal_fingerprint=fp("d"),
        ttl_seconds=1,
    )
    assert first.request_digest != second.request_digest
    assert registry.get("key") == second


def test_mcp_discovery_filters_tools_per_principal():
    auth = MCPAuthorization()
    auth.set(
        MCPPrincipalPolicy(
            "alice",
            allowed_tools=frozenset({"inspect"}),
        )
    )
    listing = MCPPrincipalDiscovery(surface(), auth).list_tools("alice")
    assert [item.name for item in listing.tools] == ["inspect"]
    assert listing.cache_scope == "private"


def test_mcp_discovery_unknown_principal_gets_empty_list():
    auth = MCPAuthorization()
    listing = MCPPrincipalDiscovery(surface(), auth).list_tools("unknown")
    assert listing.tools == ()


def test_mcp_discovery_digest_bound_to_principal():
    auth = MCPAuthorization()
    auth.set(MCPPrincipalPolicy("alice", allowed_tools=frozenset({"inspect"})))
    auth.set(MCPPrincipalPolicy("bob", allowed_tools=frozenset({"inspect"})))
    discovery = MCPPrincipalDiscovery(surface(), auth)
    assert discovery.list_tools("alice").digest != discovery.list_tools("bob").digest


def request():
    return MCPRequestEnvelope(
        "r",
        "tools/call",
        "python",
        {"args": ["-V"]},
    )


def test_mcp_transport_accepts_matching_routing_headers():
    decision = MCPTransportValidator().inspect(
        request(),
        {
            "Mcp-Method": "tools/call",
            "Mcp-Name": "python",
        },
    )
    assert decision.allowed


def test_mcp_transport_header_lookup_case_insensitive():
    decision = MCPTransportValidator().inspect(
        request(),
        {
            "mcp-method": "tools/call",
            "MCP-NAME": "python",
        },
    )
    assert decision.allowed


def test_mcp_transport_rejects_method_mismatch():
    decision = MCPTransportValidator().inspect(
        request(),
        {
            "Mcp-Method": "resources/read",
            "Mcp-Name": "python",
        },
    )
    assert not decision.allowed
    assert any("Method" in reason for reason in decision.reasons)


def test_mcp_transport_rejects_name_mismatch():
    decision = MCPTransportValidator().inspect(
        request(),
        {
            "Mcp-Method": "tools/call",
            "Mcp-Name": "other",
        },
    )
    assert not decision.allowed


def test_mcp_transport_requires_routing_headers_by_default():
    decision = MCPTransportValidator().inspect(request(), {})
    assert not decision.allowed
    assert len(decision.reasons) == 2


def test_mcp_transport_can_disable_header_requirement():
    validator = MCPTransportValidator(
        MCPTransportPolicy(require_routing_headers=False)
    )
    assert validator.inspect(request(), {}).allowed


def test_mcp_transport_header_count_limit():
    validator = MCPTransportValidator(
        MCPTransportPolicy(max_headers=1)
    )
    decision = validator.inspect(
        request(),
        {
            "Mcp-Method": "tools/call",
            "Mcp-Name": "python",
        },
    )
    assert not decision.allowed
    assert any("too many" in reason for reason in decision.reasons)


def test_mcp_transport_header_name_byte_limit():
    validator = MCPTransportValidator(
        MCPTransportPolicy(max_header_name_bytes=3)
    )
    decision = validator.inspect(
        request(),
        {
            "Mcp-Method": "tools/call",
            "Mcp-Name": "python",
        },
    )
    assert not decision.allowed


def test_mcp_transport_header_value_byte_limit():
    validator = MCPTransportValidator(
        MCPTransportPolicy(max_header_value_bytes=3)
    )
    decision = validator.inspect(
        request(),
        {
            "Mcp-Method": "tools/call",
            "Mcp-Name": "python",
        },
    )
    assert not decision.allowed


def test_mcp_transport_require_raises():
    with pytest.raises(ValueError):
        MCPTransportValidator().require(
            request(),
            {
                "Mcp-Method": "wrong",
                "Mcp-Name": "python",
            },
        )


def test_distributed_idempotency_preserves_logical_key():
    backend = InMemoryFencedStore()
    registry = DistributedAIIdempotencyRegistry(backend)
    record = registry.register(
        "request-slot",
        request_digest=fp("a"),
        proposal_fingerprint=fp("b"),
    )
    assert record.key == "request-slot"
