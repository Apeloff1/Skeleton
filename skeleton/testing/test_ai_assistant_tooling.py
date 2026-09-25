from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.ai.assistant import (
    AssistantRequest,
    CapabilityDescriptor,
    CapabilityGrant,
    CapabilityKind,
    CapabilityRegistry,
    SideEffectClass,
    ToolCoordinator,
    ToolCoordinatorError,
    ToolProposal,
)


NOW = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)


def _write_descriptor() -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id="external.send",
        kind=CapabilityKind.EXTERNAL_APP,
        side_effect=SideEffectClass.EXTERNAL_WRITE,
        required_scopes=frozenset({"message:send"}),
        requires_explicit_user_action=True,
    )


@pytest.mark.asyncio
async def test_external_write_needs_explicit_action_and_request_bound_grant() -> None:
    registry = CapabilityRegistry()
    descriptor = _write_descriptor()
    registry.register(descriptor)
    coordinator = ToolCoordinator(registry)

    calls = {"count": 0}

    async def handler(arguments):
        calls["count"] += 1
        return {"output_ref": "message:42", "accepted": arguments["text"]}

    coordinator.bind(descriptor.capability_id, handler)
    request = AssistantRequest(request_id="tool-1", text="Send hello.")
    proposal = ToolProposal(
        proposal_id="proposal-1",
        capability_id=descriptor.capability_id,
        arguments={"text": "hello"},
        request_digest=request.digest,
        side_effect=descriptor.side_effect,
        idempotency_key="idem-1",
    )

    blocked = await coordinator.execute(proposal, request)
    assert blocked.receipt.status == "blocked"
    assert blocked.receipt.error_code == "explicit-user-action-required"
    assert calls["count"] == 0

    still_blocked = await coordinator.execute(
        proposal,
        request,
        explicit_user_action=True,
    )
    assert still_blocked.receipt.status == "blocked"
    assert still_blocked.receipt.error_code == "missing-request-bound-grant"
    assert calls["count"] == 0

    grant = CapabilityGrant(
        capability_id=descriptor.capability_id,
        request_digest=request.digest,
        granted_scopes=frozenset({"message:send"}),
        granted_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    executed = await coordinator.execute(
        proposal,
        request,
        grants=(grant,),
        explicit_user_action=True,
        now=NOW,
    )
    assert executed.receipt.status == "succeeded"
    assert executed.replayed is False
    assert calls["count"] == 1

    replay = await coordinator.execute(
        proposal,
        request,
        grants=(grant,),
        explicit_user_action=True,
        now=NOW,
    )
    assert replay.replayed is True
    assert replay.receipt == executed.receipt
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_idempotency_key_conflict_fails_closed_after_execution() -> None:
    registry = CapabilityRegistry()
    descriptor = CapabilityDescriptor(
        capability_id="public.lookup",
        kind=CapabilityKind.PUBLIC_WEB,
        side_effect=SideEffectClass.READ_ONLY,
    )
    registry.register(descriptor)
    coordinator = ToolCoordinator(registry)
    coordinator.bind(descriptor.capability_id, lambda args: {"value": args["q"]})

    request = AssistantRequest(request_id="tool-2", text="Look it up.")
    first = ToolProposal(
        proposal_id="proposal-a",
        capability_id=descriptor.capability_id,
        arguments={"q": "a"},
        request_digest=request.digest,
        side_effect=descriptor.side_effect,
        idempotency_key="same-key",
    )
    second = ToolProposal(
        proposal_id="proposal-b",
        capability_id=descriptor.capability_id,
        arguments={"q": "b"},
        request_digest=request.digest,
        side_effect=descriptor.side_effect,
        idempotency_key="same-key",
    )

    assert (await coordinator.execute(first, request)).receipt.status == "succeeded"
    with pytest.raises(ToolCoordinatorError, match="idempotency"):
        await coordinator.execute(second, request)


@pytest.mark.asyncio
async def test_scoped_read_capability_also_requires_request_bound_grant() -> None:
    registry = CapabilityRegistry()
    descriptor = CapabilityDescriptor(
        capability_id="files.read",
        kind=CapabilityKind.FILES,
        side_effect=SideEffectClass.READ_ONLY,
        required_scopes=frozenset({"files:read"}),
    )
    registry.register(descriptor)
    coordinator = ToolCoordinator(registry)
    coordinator.bind(descriptor.capability_id, lambda args: {"ok": True})

    request = AssistantRequest(request_id="tool-3", text="Read my file.")
    proposal = ToolProposal(
        proposal_id="proposal-files",
        capability_id=descriptor.capability_id,
        arguments={"ref": "file:1"},
        request_digest=request.digest,
        side_effect=descriptor.side_effect,
        idempotency_key="files-key",
    )
    result = await coordinator.execute(proposal, request)
    assert result.receipt.status == "blocked"
    assert result.receipt.error_code == "missing-request-bound-grant"


@pytest.mark.asyncio
async def test_capability_specific_input_bound_is_enforced() -> None:
    registry = CapabilityRegistry()
    descriptor = CapabilityDescriptor(
        capability_id="tiny.lookup",
        kind=CapabilityKind.PUBLIC_WEB,
        side_effect=SideEffectClass.READ_ONLY,
        max_input_bytes=8,
    )
    registry.register(descriptor)
    coordinator = ToolCoordinator(registry)
    coordinator.bind(descriptor.capability_id, lambda args: {"ok": True})
    request = AssistantRequest(request_id="tool-4", text="Lookup.")
    proposal = ToolProposal(
        proposal_id="proposal-tiny",
        capability_id=descriptor.capability_id,
        arguments={"query": "this is too large"},
        request_digest=request.digest,
        side_effect=descriptor.side_effect,
        idempotency_key="tiny-key",
    )
    with pytest.raises(ToolCoordinatorError, match="input exceeds"):
        await coordinator.execute(proposal, request)


@pytest.mark.asyncio
async def test_same_idempotency_text_is_isolated_across_requests() -> None:
    registry = CapabilityRegistry()
    descriptor = CapabilityDescriptor(
        capability_id="public.lookup.shared",
        kind=CapabilityKind.PUBLIC_WEB,
        side_effect=SideEffectClass.READ_ONLY,
    )
    registry.register(descriptor)
    coordinator = ToolCoordinator(registry)
    calls = {"count": 0}

    def handler(args):
        calls["count"] += 1
        return {"value": args["q"]}

    coordinator.bind(descriptor.capability_id, handler)
    first_request = AssistantRequest(request_id="scope-a", text="Lookup a")
    second_request = AssistantRequest(request_id="scope-b", text="Lookup b")
    first = ToolProposal(
        proposal_id="scope-proposal-a",
        capability_id=descriptor.capability_id,
        arguments={"q": "a"},
        request_digest=first_request.digest,
        side_effect=descriptor.side_effect,
        idempotency_key="client-reused-key",
    )
    second = ToolProposal(
        proposal_id="scope-proposal-b",
        capability_id=descriptor.capability_id,
        arguments={"q": "b"},
        request_digest=second_request.digest,
        side_effect=descriptor.side_effect,
        idempotency_key="client-reused-key",
    )
    assert (await coordinator.execute(first, first_request)).receipt.status == "succeeded"
    assert (await coordinator.execute(second, second_request)).receipt.status == "succeeded"
    assert calls["count"] == 2


def test_grant_is_not_valid_before_issuance() -> None:
    request = AssistantRequest(request_id="grant-time", text="Read scoped data")
    grant = CapabilityGrant(
        capability_id="files.read",
        request_digest=request.digest,
        granted_scopes=frozenset({"files:read"}),
        granted_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    assert grant.valid_at(NOW - timedelta(seconds=1)) is False
    assert grant.valid_at(NOW) is True
