"""Model admission, admitted ensemble, and MCP replay boundary tests."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.admitted_ensemble import AdmittedEnsembleAIPlanner
from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.candidates import CandidateSelector
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.ensemble_planner import EnsembleAIPlanner, EnsembleMember
from skeleton.shells.ai.manifest import build_manifest
from skeleton.shells.ai.mcp import MCPRequestEnvelope, MCPToolSurface
from skeleton.shells.ai.mcp_authz import MCPAuthorization, MCPPrincipalPolicy
from skeleton.shells.ai.mcp_gateway import MCPAIShellGateway
from skeleton.shells.ai.mcp_replay import MCPReplayGuard, MCPRequestReplay
from skeleton.shells.ai.model_admission import (
    AIModelAdmission,
    ModelAdmissionRequirement,
)
from skeleton.shells.ai.model_port import CallableAIModelPort, ModelCapabilities
from skeleton.shells.ai.model_registry import AIModelRegistry
from skeleton.shells.ai.planner import AIPlanner
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.protocol import AIModelResponse
from skeleton.shells.ai.provider_attestation import (
    AttestationRequirement,
    ProviderAttestation,
)
from skeleton.shells.ai.router import AIToolRouter
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.registry import ExecutableSpec


def fp(char):
    return char * 64


def command_catalog():
    return CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec("python", sys.executable),
                ArgumentPolicy.allow_any(),
                description="python",
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


def tool_catalog():
    return AIToolCatalog(command_catalog())


def shell_policy():
    return AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
        min_confidence=0.5,
        max_uncertainty=0.5,
    )


def attestation(
    provider="provider-a",
    model="model-a",
    *,
    model_version="2026-09",
    adapter_version="adapter-1",
    digest=None,
    capabilities=None,
    protocols=(1,),
):
    return ProviderAttestation(
        provider,
        model,
        model_version,
        adapter_version,
        capabilities or ModelCapabilities(
            structured_output=True,
            tool_use=True,
            critique=True,
            parallel_candidates=True,
        ),
        protocols,
        digest or tool_catalog().digest,
    )


def requirement(
    provider="provider-a",
    model="model-a",
    **changes,
):
    values = dict(
        provider_id=provider,
        model_id=model,
        tool_catalog_digest=tool_catalog().digest,
        attestation=AttestationRequirement(),
    )
    values.update(changes)
    return ModelAdmissionRequirement(**values)


def test_model_admission_registered_active_model_allowed():
    registry = AIModelRegistry()
    registered = registry.register(attestation())
    report = AIModelAdmission(registry).inspect(requirement())
    assert report.allowed
    assert report.registry_id == registered.registry_id
    assert report.registry_revision == 1
    assert report.attestation_digest == registered.attestation.digest


def test_model_admission_unknown_identity_denied():
    registry = AIModelRegistry()
    report = AIModelAdmission(registry).inspect(requirement())
    assert not report.allowed
    assert report.registry_revision is None
    assert any("not registered" in reason for reason in report.reasons)


def test_model_admission_inactive_identity_denied():
    registry = AIModelRegistry()
    registered = registry.register(attestation())
    registry.deactivate(registered.registry_id)
    report = AIModelAdmission(registry).inspect(requirement())
    assert not report.allowed
    assert any("inactive" in reason for reason in report.reasons)


def test_model_admission_exact_model_version():
    registry = AIModelRegistry()
    registry.register(attestation(model_version="v1"))
    assert AIModelAdmission(registry).inspect(
        requirement(exact_model_version="v1")
    ).allowed
    report = AIModelAdmission(registry).inspect(
        requirement(exact_model_version="v2")
    )
    assert not report.allowed
    assert any("model version" in reason for reason in report.reasons)


def test_model_admission_exact_adapter_version():
    registry = AIModelRegistry()
    registry.register(attestation(adapter_version="a1"))
    assert AIModelAdmission(registry).inspect(
        requirement(exact_adapter_version="a1")
    ).allowed
    report = AIModelAdmission(registry).inspect(
        requirement(exact_adapter_version="a2")
    )
    assert not report.allowed
    assert any("adapter version" in reason for reason in report.reasons)


def test_model_admission_attestation_digest_pin():
    registry = AIModelRegistry()
    registered = registry.register(attestation())
    assert AIModelAdmission(registry).inspect(
        requirement(expected_attestation_digest=registered.attestation.digest)
    ).allowed
    report = AIModelAdmission(registry).inspect(
        requirement(expected_attestation_digest=fp("x"))
    )
    assert not report.allowed
    assert any("attestation digest" in reason for reason in report.reasons)


def test_model_admission_tool_catalog_mismatch():
    registry = AIModelRegistry()
    registry.register(attestation(digest=fp("a")))
    report = AIModelAdmission(registry).inspect(
        requirement(tool_catalog_digest=fp("b"))
    )
    assert not report.allowed
    assert any("tool catalog" in reason for reason in report.reasons)


def test_model_admission_structured_output_requirement():
    registry = AIModelRegistry()
    registry.register(
        attestation(
            capabilities=ModelCapabilities(
                structured_output=False,
                tool_use=True,
            )
        )
    )
    report = AIModelAdmission(registry).inspect(requirement())
    assert not report.allowed
    assert any("structured output" in reason for reason in report.reasons)


def test_model_admission_tool_use_requirement():
    registry = AIModelRegistry()
    registry.register(
        attestation(
            capabilities=ModelCapabilities(
                structured_output=True,
                tool_use=False,
            )
        )
    )
    report = AIModelAdmission(registry).inspect(requirement())
    assert not report.allowed
    assert any("tool use" in reason for reason in report.reasons)


def test_model_admission_optional_critique_requirement():
    registry = AIModelRegistry()
    registry.register(
        attestation(
            capabilities=ModelCapabilities(
                structured_output=True,
                tool_use=True,
                critique=False,
            )
        )
    )
    report = AIModelAdmission(registry).inspect(
        requirement(
            attestation=AttestationRequirement(require_critique=True)
        )
    )
    assert not report.allowed
    assert any("critique" in reason for reason in report.reasons)


def test_model_admission_parallel_candidate_requirement():
    registry = AIModelRegistry()
    registry.register(
        attestation(
            capabilities=ModelCapabilities(
                structured_output=True,
                tool_use=True,
                parallel_candidates=False,
            )
        )
    )
    report = AIModelAdmission(registry).inspect(
        requirement(
            attestation=AttestationRequirement(
                require_parallel_candidates=True
            )
        )
    )
    assert not report.allowed
    assert any("parallel" in reason for reason in report.reasons)


def test_model_admission_protocol_requirement():
    registry = AIModelRegistry()
    registry.register(attestation(protocols=(2,)))
    report = AIModelAdmission(registry).inspect(
        requirement(
            attestation=AttestationRequirement(protocol_version=1)
        )
    )
    assert not report.allowed
    assert any("protocol" in reason for reason in report.reasons)


def test_model_admission_input_capacity_requirement():
    registry = AIModelRegistry()
    registry.register(
        attestation(
            capabilities=ModelCapabilities(
                max_input_bytes=100,
                max_output_bytes=1000,
            )
        )
    )
    report = AIModelAdmission(registry).inspect(
        requirement(
            attestation=AttestationRequirement(min_input_bytes=101)
        )
    )
    assert not report.allowed
    assert any("input byte" in reason for reason in report.reasons)


def test_model_admission_output_capacity_requirement():
    registry = AIModelRegistry()
    registry.register(
        attestation(
            capabilities=ModelCapabilities(
                max_input_bytes=1000,
                max_output_bytes=100,
            )
        )
    )
    report = AIModelAdmission(registry).inspect(
        requirement(
            attestation=AttestationRequirement(min_output_bytes=101)
        )
    )
    assert not report.allowed
    assert any("output byte" in reason for reason in report.reasons)


def test_model_admission_require_raises():
    registry = AIModelRegistry()
    with pytest.raises(RuntimeError, match="not registered"):
        AIModelAdmission(registry).require(requirement())


@pytest.mark.parametrize(
    "changes",
    [
        {"provider_id": ""},
        {"model_id": ""},
        {"tool_catalog_digest": "bad"},
        {"expected_attestation_digest": "bad"},
    ],
)
def test_model_admission_requirement_validation(changes):
    values = dict(
        provider_id="provider-a",
        model_id="model-a",
        tool_catalog_digest=fp("t"),
    )
    values.update(changes)
    with pytest.raises(ValueError):
        ModelAdmissionRequirement(**values)


def planner(provider, model):
    catalog = tool_catalog()
    item_effects = effects()
    item_policy = shell_policy()

    def propose(request):
        return AIModelResponse(
            request.request_id,
            AIPlanProposal(
                f"proposal-{provider}-{model}",
                request.intent.intent_id,
                (AIAction("a", "python", ("-V",)),),
                confidence=0.9,
                uncertainty=0.1,
                model_id=model,
            ),
        )

    return AIPlanner(
        CallableAIModelPort(model, propose),
        catalog,
        AIToolRouter(catalog, item_effects),
        policy_fingerprint=item_policy.fingerprint,
    )


def admitted_ensemble():
    members = (
        EnsembleMember(planner("provider-a", "model-a"), "provider-a"),
        EnsembleMember(planner("provider-b", "model-b"), "provider-b"),
    )
    selector = CandidateSelector(
        AIPlanCritic(effects(), shell_policy())
    )
    ensemble = EnsembleAIPlanner(members, selector)
    registry = AIModelRegistry()
    first = registry.register(attestation("provider-a", "model-a"))
    second = registry.register(attestation("provider-b", "model-b"))
    admission = AIModelAdmission(registry)
    requirements = (
        requirement(
            "provider-a",
            "model-a",
            expected_attestation_digest=first.attestation.digest,
        ),
        requirement(
            "provider-b",
            "model-b",
            expected_attestation_digest=second.attestation.digest,
        ),
    )
    return AdmittedEnsembleAIPlanner(
        ensemble,
        admission,
        requirements,
    ), registry


def test_admitted_ensemble_happy_path():
    service, _ = admitted_ensemble()
    result = service.propose(AIIntent("i", "inspect python"))
    assert result.planning.consensus.reached
    assert len(result.admissions) == 2
    assert all(item.allowed for item in result.admissions)


def test_admitted_ensemble_inactive_member_blocks_before_model_calls():
    service, registry = admitted_ensemble()
    registry.deactivate("provider-b:model-b")
    with pytest.raises(RuntimeError, match="inactive"):
        service.propose(AIIntent("i", "inspect python"))


def test_admitted_ensemble_attestation_revision_drift_blocks():
    service, registry = admitted_ensemble()
    current = registry.current("provider-a:model-a")
    registry.register(
        attestation(
            "provider-a",
            "model-a",
            model_version="2026-10",
        ),
        expected_revision=current.revision,
    )
    with pytest.raises(RuntimeError, match="attestation digest"):
        service.propose(AIIntent("i", "inspect python"))


def test_admitted_ensemble_requirements_must_match_members():
    members = (
        EnsembleMember(planner("provider-a", "model-a"), "provider-a"),
        EnsembleMember(planner("provider-b", "model-b"), "provider-b"),
    )
    ensemble = EnsembleAIPlanner(
        members,
        CandidateSelector(AIPlanCritic(effects(), shell_policy())),
    )
    with pytest.raises(ValueError, match="do not match"):
        AdmittedEnsembleAIPlanner(
            ensemble,
            AIModelAdmission(AIModelRegistry()),
            (requirement("provider-a", "model-a"),),
        )


def test_admitted_ensemble_duplicate_requirement_rejected():
    members = (
        EnsembleMember(planner("provider-a", "model-a"), "provider-a"),
        EnsembleMember(planner("provider-b", "model-b"), "provider-b"),
    )
    ensemble = EnsembleAIPlanner(
        members,
        CandidateSelector(AIPlanCritic(effects(), shell_policy())),
    )
    duplicate = requirement("provider-a", "model-a")
    with pytest.raises(ValueError, match="duplicate"):
        AdmittedEnsembleAIPlanner(
            ensemble,
            AIModelAdmission(AIModelRegistry()),
            (duplicate, duplicate),
        )


def mcp_request(
    request_id="request-1",
    *,
    name="python",
    args=None,
    metadata=None,
):
    return MCPRequestEnvelope(
        request_id,
        "tools/call",
        name,
        {
            "args": ["-V"] if args is None else args,
            "purpose": "inspect",
        },
        metadata={} if metadata is None else metadata,
    )


def test_mcp_replay_digest_is_deterministic():
    request = mcp_request()
    one = MCPReplayGuard.request_digest(request, principal="alice")
    two = MCPReplayGuard.request_digest(request, principal="alice")
    assert one == two
    assert len(one) == 64


def test_mcp_replay_digest_is_principal_bound():
    request = mcp_request()
    assert (
        MCPReplayGuard.request_digest(request, principal="alice")
        != MCPReplayGuard.request_digest(request, principal="bob")
    )


def test_mcp_replay_digest_changes_with_arguments():
    first = mcp_request(args=["-V"])
    second = mcp_request(args=["--help"])
    assert (
        MCPReplayGuard.request_digest(first, principal="alice")
        != MCPReplayGuard.request_digest(second, principal="alice")
    )


def test_mcp_replay_first_admission_succeeds():
    guard = MCPReplayGuard(InMemoryFencedStore())
    request = mcp_request()
    admission = guard.admit(request, principal="alice")
    assert admission.request_id == request.request_id
    assert admission.principal == "alice"
    assert guard.seen(request, principal="alice")
    assert guard.remaining_seconds(request, principal="alice") > 0


def test_mcp_replay_identical_second_admission_rejected():
    guard = MCPReplayGuard(InMemoryFencedStore())
    request = mcp_request()
    guard.admit(request, principal="alice")
    with pytest.raises(MCPRequestReplay, match="already admitted"):
        guard.admit(request, principal="alice")


def test_mcp_replay_same_id_different_content_rejected():
    guard = MCPReplayGuard(InMemoryFencedStore())
    guard.admit(mcp_request(args=["-V"]), principal="alice")
    with pytest.raises(MCPRequestReplay):
        guard.admit(
            mcp_request(args=["--help"]),
            principal="alice",
        )


def test_mcp_replay_same_request_id_different_principal_is_separate_scope():
    guard = MCPReplayGuard(InMemoryFencedStore())
    request = mcp_request()
    guard.admit(request, principal="alice")
    guard.admit(request, principal="bob")
    assert guard.seen(request, principal="alice")
    assert guard.seen(request, principal="bob")


def test_mcp_replay_expiry_allows_new_admission():
    now = [0.0]
    backend = InMemoryFencedStore(clock=lambda: now[0])
    guard = MCPReplayGuard(
        backend,
        default_ttl_seconds=1,
        clock=lambda: now[0],
    )
    request = mcp_request()
    first = guard.admit(request, principal="alice")
    now[0] = 1
    assert not guard.seen(request, principal="alice")
    second = guard.admit(request, principal="alice")
    assert second.admitted_at == 1
    assert second.expires_at > first.expires_at


def test_mcp_replay_remaining_zero_after_expiry():
    now = [0.0]
    guard = MCPReplayGuard(
        InMemoryFencedStore(clock=lambda: now[0]),
        default_ttl_seconds=1,
        clock=lambda: now[0],
    )
    request = mcp_request()
    guard.admit(request, principal="alice")
    now[0] = 2
    assert guard.remaining_seconds(request, principal="alice") == 0


@pytest.mark.parametrize("ttl", [0, -1, 11])
def test_mcp_replay_ttl_validation(ttl):
    guard = MCPReplayGuard(
        InMemoryFencedStore(),
        max_ttl_seconds=10,
    )
    with pytest.raises(ValueError):
        guard.admit(
            mcp_request(),
            principal="alice",
            ttl_seconds=ttl,
        )


def test_mcp_replay_invalid_principal_rejected():
    with pytest.raises(ValueError):
        MCPReplayGuard.request_digest(
            mcp_request(),
            principal="",
        )


def gateway_with_replay():
    catalog = tool_catalog()
    surface = MCPToolSurface(build_manifest(catalog, effects()))
    authorization = MCPAuthorization()
    authorization.set(
        MCPPrincipalPolicy(
            "alice",
            allowed_tools=frozenset({"python"}),
            max_timeout_seconds=5,
        )
    )
    guard = MCPReplayGuard(InMemoryFencedStore())
    return MCPAIShellGateway(
        surface,
        authorization,
        replay_guard=guard,
    ), guard


def test_mcp_gateway_replay_guard_first_call_prepares():
    gateway, guard = gateway_with_replay()
    request = mcp_request()
    prepared = gateway.prepare_call(
        request,
        principal="alice",
    )
    assert prepared.action.command == "python"
    assert guard.seen(request, principal="alice")


def test_mcp_gateway_replay_guard_second_call_rejected():
    gateway, _ = gateway_with_replay()
    request = mcp_request()
    gateway.prepare_call(request, principal="alice")
    with pytest.raises(MCPRequestReplay):
        gateway.prepare_call(request, principal="alice")


def test_mcp_gateway_unauthorized_call_does_not_burn_replay_slot():
    catalog = tool_catalog()
    surface = MCPToolSurface(build_manifest(catalog, effects()))
    authorization = MCPAuthorization()
    authorization.set(
        MCPPrincipalPolicy(
            "alice",
            denied_tools=frozenset({"python"}),
        )
    )
    guard = MCPReplayGuard(InMemoryFencedStore())
    gateway = MCPAIShellGateway(
        surface,
        authorization,
        replay_guard=guard,
    )
    request = mcp_request()
    with pytest.raises(PermissionError):
        gateway.prepare_call(request, principal="alice")
    assert not guard.seen(request, principal="alice")


def test_mcp_gateway_invalid_arguments_do_not_burn_replay_slot():
    gateway, guard = gateway_with_replay()
    request = MCPRequestEnvelope(
        "request-1",
        "tools/call",
        "python",
        {"args": "not-a-list"},
    )
    with pytest.raises(ValueError, match="list"):
        gateway.prepare_call(request, principal="alice")
    assert not guard.seen(request, principal="alice")


def test_mcp_gateway_unknown_tool_does_not_burn_replay_slot():
    gateway, guard = gateway_with_replay()
    request = mcp_request(name="missing")
    with pytest.raises(KeyError):
        gateway.prepare_call(request, principal="alice")
    assert not guard.seen(request, principal="alice")


def test_mcp_gateway_timeout_denial_does_not_burn_replay_slot():
    catalog = tool_catalog()
    surface = MCPToolSurface(build_manifest(catalog, effects()))
    authorization = MCPAuthorization()
    authorization.set(
        MCPPrincipalPolicy(
            "alice",
            allowed_tools=frozenset({"python"}),
            max_timeout_seconds=1,
        )
    )
    guard = MCPReplayGuard(InMemoryFencedStore())
    gateway = MCPAIShellGateway(
        surface,
        authorization,
        replay_guard=guard,
    )
    request = MCPRequestEnvelope(
        "request-1",
        "tools/call",
        "python",
        {"args": ["-V"], "timeoutSeconds": 2},
    )
    with pytest.raises(PermissionError, match="timeout"):
        gateway.prepare_call(request, principal="alice")
    assert not guard.seen(request, principal="alice")
