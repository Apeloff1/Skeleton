"""Runtime trust epoch regression and adversarial coverage."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from skeleton.shells.ai.assurance import (
    AIExecutionAssuranceInspector,
    AIExecutionAssurancePolicy,
    AssuranceLevel,
)
from skeleton.shells.ai.model_admission import (
    AIModelAdmission,
    ModelAdmissionRequirement,
)
from skeleton.shells.ai.model_port import ModelCapabilities
from skeleton.shells.ai.model_registry import AIModelRegistry
from skeleton.shells.ai.provider_attestation import (
    AttestationRequirement,
    ProviderAttestation,
)
from skeleton.shells.ai.risk import RiskBand
from skeleton.shells.ai.runtime_trust import (
    AIRuntimeTrustGuard,
    RuntimeModelBinding,
    RuntimeTrustEpoch,
    RuntimeTrustSurface,
)
from skeleton.shells.ai.startup_release import (
    RuntimeReleaseExpectation,
    StartupReleaseReport,
)


def fp(char: str) -> str:\n    return hashlib.sha256(char.encode()).hexdigest()


def surface(
    *,
    assurance_policy_digest: str = "",
    code_revision: str = "abc123",
    policy_fingerprint: str = fp("p"),
    tool_catalog_digest: str = fp("t"),
    effect_digest: str = fp("e"),
    workspace_manifest_digest: str = "",
) -> RuntimeTrustSurface:
    return RuntimeTrustSurface(
        code_revision,
        policy_fingerprint,
        tool_catalog_digest,
        effect_digest,
        assurance_policy_digest,
        workspace_manifest_digest,
    )


def attestation(
    provider: str = "provider-a",
    model: str = "model-a",
    *,
    model_version: str = "2026-09",
    adapter_version: str = "adapter-1",
    tool_catalog_digest: str = fp("t"),
) -> ProviderAttestation:
    return ProviderAttestation(
        provider,
        model,
        model_version,
        adapter_version,
        ModelCapabilities(
            structured_output=True,
            tool_use=True,
            critique=True,
            parallel_candidates=True,
            max_input_bytes=100_000,
            max_output_bytes=50_000,
        ),
        (1, 2),
        tool_catalog_digest,
    )


def requirement(
    provider: str = "provider-a",
    model: str = "model-a",
    *,
    tool_catalog_digest: str = fp("t"),
    expected_attestation_digest: str = "",
) -> ModelAdmissionRequirement:
    return ModelAdmissionRequirement(
        provider,
        model,
        tool_catalog_digest,
        AttestationRequirement(
            require_structured_output=True,
            require_tool_use=True,
            require_critique=True,
            protocol_version=1,
        ),
        expected_attestation_digest=expected_attestation_digest,
    )


class MutableReleaseGuard:
    def __init__(self, report: StartupReleaseReport) -> None:
        self.report = report

    def inspect(self, expectation):
        return self.report


def release_expectation() -> RuntimeReleaseExpectation:
    return RuntimeReleaseExpectation(
        "production",
        "abc123",
        fp("p"),
        fp("t"),
        fp("e"),
    )


def release_report(
    *,
    evidence_digest: str = fp("r"),
    release_id: str = "release-1",
    release_revision: int = 1,
    channel_revision: int = 1,
    allowed: bool = True,
    reasons: tuple[str, ...] = (),
) -> StartupReleaseReport:
    return StartupReleaseReport(
        allowed,
        reasons,
        channel_revision=channel_revision,
        release_id=release_id,
        release_revision=release_revision,
        evidence_digest=evidence_digest,
    )


def model_guard(
    *,
    model_version: str = "2026-09",
    expected_digest: bool = False,
):
    registry = AIModelRegistry()
    registered = registry.register(attestation(model_version=model_version))
    required = requirement(
        expected_attestation_digest=(
            registered.attestation.digest if expected_digest else ""
        )
    )
    return registry, AIModelAdmission(registry), required


def test_runtime_surface_digest_is_deterministic():
    item = surface()
    assert len(item.digest) == 64
    assert item.digest == item.digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("code_revision", "different"),
        ("policy_fingerprint", fp("q")),
        ("tool_catalog_digest", fp("u")),
        ("effect_digest", fp("f")),
        ("workspace_manifest_digest", fp("w")),
    ],
)
def test_runtime_surface_digest_changes_for_authority_surface(field, value):
    first = surface()
    second = replace(first, **{field: value})
    assert first.digest != second.digest


def test_runtime_surface_digest_binds_assurance_policy():
    policy = AIExecutionAssurancePolicy.production()
    first = surface()
    second = surface(assurance_policy_digest=policy.digest)
    assert first.digest != second.digest


@pytest.mark.parametrize(
    "kwargs",
    [
        {"code_revision": ""},
        {"policy_fingerprint": "bad"},
        {"tool_catalog_digest": "bad"},
        {"effect_digest": "bad"},
        {"assurance_policy_digest": "bad"},
        {"workspace_manifest_digest": "bad"},
    ],
)
def test_runtime_surface_validation(kwargs):
    with pytest.raises(ValueError):
        surface(**kwargs)


def test_runtime_model_binding_from_admission_report():
    registry, admission, required = model_guard()
    report = admission.require(required)
    binding = RuntimeModelBinding.from_report(report)
    assert binding.registry_id == "provider-a:model-a"
    assert binding.registry_revision == 1
    assert binding.attestation_digest == registry.current(
        "provider-a:model-a"
    ).attestation.digest


def test_runtime_model_binding_rejects_denied_report():
    _, admission, required = model_guard()
    bad = replace(required, exact_model_version="missing")
    report = admission.inspect(bad)
    assert not report.allowed
    with pytest.raises(ValueError, match="denied"):
        RuntimeModelBinding.from_report(report)


def test_runtime_epoch_sorts_models_canonically():
    first = RuntimeModelBinding("z:model", 1, fp("a"))
    second = RuntimeModelBinding("a:model", 2, fp("b"))
    epoch = RuntimeTrustEpoch(1, surface(), (first, second))
    assert [item.registry_id for item in epoch.models] == [
        "a:model",
        "z:model",
    ]


def test_runtime_epoch_rejects_duplicate_model_identity():
    with pytest.raises(ValueError, match="duplicate"):
        RuntimeTrustEpoch(
            1,
            surface(),
            (
                RuntimeModelBinding("a:model", 1, fp("a")),
                RuntimeModelBinding("a:model", 2, fp("b")),
            ),
        )


def test_runtime_epoch_digest_changes_with_model_revision():
    first = RuntimeTrustEpoch(
        1,
        surface(),
        (RuntimeModelBinding("a:model", 1, fp("a")),),
    )
    second = RuntimeTrustEpoch(
        1,
        surface(),
        (RuntimeModelBinding("a:model", 2, fp("a")),),
    )
    assert first.digest != second.digest


def test_runtime_epoch_digest_changes_with_attestation_digest():
    first = RuntimeTrustEpoch(
        1,
        surface(),
        (RuntimeModelBinding("a:model", 1, fp("a")),),
    )
    second = RuntimeTrustEpoch(
        1,
        surface(),
        (RuntimeModelBinding("a:model", 1, fp("b")),),
    )
    assert first.digest != second.digest


def test_runtime_epoch_digest_changes_with_release_evidence():
    first = RuntimeTrustEpoch(
        1,
        surface(),
        release_evidence_digest=fp("a"),
        release_id="r",
        release_revision=1,
        release_channel_revision=1,
    )
    second = RuntimeTrustEpoch(
        1,
        surface(),
        release_evidence_digest=fp("b"),
        release_id="r",
        release_revision=1,
        release_channel_revision=1,
    )
    assert first.digest != second.digest


def test_runtime_epoch_digest_changes_with_release_revision():
    first = RuntimeTrustEpoch(
        1,
        surface(),
        release_evidence_digest=fp("a"),
        release_id="r",
        release_revision=1,
        release_channel_revision=1,
    )
    second = RuntimeTrustEpoch(
        1,
        surface(),
        release_evidence_digest=fp("a"),
        release_id="r",
        release_revision=2,
        release_channel_revision=1,
    )
    assert first.digest != second.digest


def test_runtime_trust_guard_without_external_dependencies_pins_surface():
    guard = AIRuntimeTrustGuard(surface())
    report = guard.pin()
    assert report.allowed
    assert report.epoch is not None
    assert guard.expected_epoch_digest == report.epoch.digest
    assert guard.require_current().allowed


def test_runtime_trust_guard_expected_epoch_can_be_preconfigured():
    initial = AIRuntimeTrustGuard(surface())
    pinned = initial.pin()
    guard = AIRuntimeTrustGuard(
        surface(),
        expected_epoch_digest=pinned.epoch_digest,
    )
    assert guard.require_current().epoch_digest == pinned.epoch_digest


def test_runtime_trust_guard_wrong_expected_epoch_fails_closed():
    guard = AIRuntimeTrustGuard(
        surface(),
        expected_epoch_digest=fp("f"),
    )
    with pytest.raises(RuntimeError, match="drift"):
        guard.require_current()


def test_runtime_trust_requires_model_admission_when_models_configured():
    with pytest.raises(ValueError, match="model_admission"):
        AIRuntimeTrustGuard(
            surface(),
            model_requirements=(requirement(),),
        )


def test_runtime_trust_rejects_duplicate_model_requirements():
    registry, admission, required = model_guard()
    with pytest.raises(ValueError, match="duplicate"):
        AIRuntimeTrustGuard(
            surface(),
            model_admission=admission,
            model_requirements=(required, required),
        )


def test_runtime_trust_rejects_model_tool_surface_mismatch():
    registry, admission, _ = model_guard()
    with pytest.raises(ValueError, match="tool catalog"):
        AIRuntimeTrustGuard(
            surface(),
            model_admission=admission,
            model_requirements=(
                requirement(tool_catalog_digest=fp("x")),
            ),
        )


def test_runtime_trust_model_happy_path_is_bound_into_epoch():
    registry, admission, required = model_guard()
    guard = AIRuntimeTrustGuard(
        surface(),
        model_admission=admission,
        model_requirements=(required,),
    )
    report = guard.pin()
    assert report.allowed
    assert report.epoch is not None
    assert len(report.epoch.models) == 1
    assert report.epoch.models[0].registry_revision == 1


def test_runtime_trust_model_deactivation_after_pin_is_blocked():
    registry, admission, required = model_guard()
    guard = AIRuntimeTrustGuard(
        surface(),
        model_admission=admission,
        model_requirements=(required,),
    )
    guard.pin()
    registry.deactivate("provider-a:model-a")
    report = guard.inspect()
    assert not report.allowed
    assert any("inactive" in reason for reason in report.reasons)
    with pytest.raises(RuntimeError, match="inactive"):
        guard.require_current()


def test_runtime_trust_model_revision_drift_changes_epoch():
    registry, admission, required = model_guard()
    guard = AIRuntimeTrustGuard(
        surface(),
        model_admission=admission,
        model_requirements=(required,),
    )
    first = guard.pin()
    current = registry.current("provider-a:model-a")
    registry.register(
        attestation(model_version="2026-10"),
        expected_revision=current.revision,
    )
    report = guard.inspect()
    assert not report.allowed
    assert any("epoch drift" in reason for reason in report.reasons)
    assert report.epoch is not None
    assert report.epoch.digest != first.epoch_digest


def test_runtime_trust_pinned_attestation_rejects_revision_content_drift():
    registry, admission, required = model_guard(expected_digest=True)
    guard = AIRuntimeTrustGuard(
        surface(),
        model_admission=admission,
        model_requirements=(required,),
    )
    guard.pin()
    current = registry.current("provider-a:model-a")
    registry.register(
        attestation(model_version="2026-10"),
        expected_revision=current.revision,
    )
    report = guard.inspect()
    assert not report.allowed
    assert any("attestation digest" in reason for reason in report.reasons)


def test_runtime_trust_multiple_models_are_canonical_and_all_required():
    registry = AIModelRegistry()
    a = registry.register(attestation("provider-b", "model-b"))
    b = registry.register(attestation("provider-a", "model-a"))
    admission = AIModelAdmission(registry)
    guard = AIRuntimeTrustGuard(
        surface(),
        model_admission=admission,
        model_requirements=(
            requirement("provider-b", "model-b"),
            requirement("provider-a", "model-a"),
        ),
    )
    report = guard.pin()
    assert report.allowed
    assert [item.registry_id for item in report.epoch.models] == [
        "provider-a:model-a",
        "provider-b:model-b",
    ]
    registry.deactivate(a.registry_id)
    assert not guard.inspect().allowed


def test_runtime_trust_assurance_policy_happy_path():
    assurance = AIExecutionAssuranceInspector()
    guard = AIRuntimeTrustGuard(
        surface(assurance_policy_digest=assurance.policy.digest),
        assurance=assurance,
    )
    assert guard.pin().allowed


def test_runtime_trust_requires_assurance_digest_when_inspector_configured():
    assurance = AIExecutionAssuranceInspector()
    with pytest.raises(ValueError, match="bind configured assurance"):
        AIRuntimeTrustGuard(surface(), assurance=assurance)


def test_runtime_trust_rejects_surface_assurance_without_inspector():
    policy = AIExecutionAssurancePolicy.production()
    with pytest.raises(ValueError, match="no inspector"):
        AIRuntimeTrustGuard(
            surface(assurance_policy_digest=policy.digest)
        )


def test_runtime_trust_assurance_policy_drift_after_pin_is_blocked():
    first = AIExecutionAssuranceInspector()
    guard = AIRuntimeTrustGuard(
        surface(assurance_policy_digest=first.policy.digest),
        assurance=first,
    )
    guard.pin()
    guard.assurance = AIExecutionAssuranceInspector(
        AIExecutionAssurancePolicy(
            low=AssuranceLevel.SEALED,
            medium=AssuranceLevel.SEALED,
            high=AssuranceLevel.SANDBOXED,
            critical=AssuranceLevel.DENIED,
        )
    )
    report = guard.inspect()
    assert not report.allowed
    assert "assurance policy drift detected" in report.reasons


def test_runtime_trust_release_happy_path_bound_into_epoch():
    release = MutableReleaseGuard(release_report())
    guard = AIRuntimeTrustGuard(
        surface(),
        release_guard=release,
        release_expectation=release_expectation(),
    )
    report = guard.pin()
    assert report.allowed
    assert report.epoch.release_evidence_digest == fp("r")
    assert report.epoch.release_id == "release-1"
    assert report.epoch.release_revision == 1
    assert report.epoch.release_channel_revision == 1


def test_runtime_trust_release_denial_is_fail_closed():
    release = MutableReleaseGuard(
        release_report(
            allowed=False,
            reasons=("signature invalid",),
        )
    )
    guard = AIRuntimeTrustGuard(
        surface(),
        release_guard=release,
        release_expectation=release_expectation(),
    )
    report = guard.inspect()
    assert not report.allowed
    assert "release: signature invalid" in report.reasons


def test_runtime_trust_release_promotion_after_pin_is_drift():
    release = MutableReleaseGuard(release_report())
    guard = AIRuntimeTrustGuard(
        surface(),
        release_guard=release,
        release_expectation=release_expectation(),
    )
    first = guard.pin()
    release.report = release_report(
        evidence_digest=fp("s"),
        release_id="release-2",
        release_revision=2,
        channel_revision=2,
    )
    report = guard.inspect()
    assert not report.allowed
    assert report.epoch is not None
    assert report.epoch.digest != first.epoch_digest
    assert "runtime trust epoch drift detected" in report.reasons


def test_runtime_trust_release_guard_configuration_is_atomic():
    with pytest.raises(ValueError, match="configured together"):
        AIRuntimeTrustGuard(
            surface(),
            release_guard=MutableReleaseGuard(release_report()),
        )
    with pytest.raises(ValueError, match="configured together"):
        AIRuntimeTrustGuard(
            surface(),
            release_expectation=release_expectation(),
        )


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("code_revision", "different", "code revision"),
        ("policy_fingerprint", fp("x"), "policy"),
        ("tool_catalog_digest", fp("x"), "tools"),
        ("effect_digest", fp("x"), "effects"),
    ],
)
def test_runtime_trust_release_expectation_must_match_surface(
    field,
    value,
    message,
):
    values = release_expectation().__dict__.copy()
    values[field] = value
    expectation = RuntimeReleaseExpectation(**values)
    with pytest.raises(ValueError, match=message):
        AIRuntimeTrustGuard(
            surface(),
            release_guard=MutableReleaseGuard(release_report()),
            release_expectation=expectation,
        )


def test_runtime_trust_workspace_expectation_must_match_surface():
    expectation = RuntimeReleaseExpectation(
        "production",
        "abc123",
        fp("p"),
        fp("t"),
        fp("e"),
        workspace_manifest_digest=fp("x"),
    )
    with pytest.raises(ValueError, match="workspace"):
        AIRuntimeTrustGuard(
            surface(workspace_manifest_digest=fp("y")),
            release_guard=MutableReleaseGuard(release_report()),
            release_expectation=expectation,
        )


def test_runtime_trust_report_is_json_shaped():
    guard = AIRuntimeTrustGuard(surface())
    report = guard.pin()
    data = report.to_dict()
    assert data["allowed"] is True
    assert data["epoch_digest"] == report.epoch_digest
    assert data["epoch"]["surface"]["code_revision"] == "abc123"
    assert data["expected_epoch_digest"] == report.epoch_digest


def test_runtime_trust_epoch_is_stable_under_requirement_order():
    registry = AIModelRegistry()
    registry.register(attestation("provider-a", "model-a"))
    registry.register(attestation("provider-b", "model-b"))
    admission = AIModelAdmission(registry)
    first = AIRuntimeTrustGuard(
        surface(),
        model_admission=admission,
        model_requirements=(
            requirement("provider-a", "model-a"),
            requirement("provider-b", "model-b"),
        ),
    ).pin()
    second = AIRuntimeTrustGuard(
        surface(),
        model_admission=admission,
        model_requirements=(
            requirement("provider-b", "model-b"),
            requirement("provider-a", "model-a"),
        ),
    ).pin()
    assert first.epoch_digest == second.epoch_digest


def test_runtime_trust_epoch_changes_if_model_set_changes():
    registry = AIModelRegistry()
    registry.register(attestation("provider-a", "model-a"))
    registry.register(attestation("provider-b", "model-b"))
    admission = AIModelAdmission(registry)
    one = AIRuntimeTrustGuard(
        surface(),
        model_admission=admission,
        model_requirements=(requirement("provider-a", "model-a"),),
    ).pin()
    two = AIRuntimeTrustGuard(
        surface(),
        model_admission=admission,
        model_requirements=(
            requirement("provider-a", "model-a"),
            requirement("provider-b", "model-b"),
        ),
    ).pin()
    assert one.epoch_digest != two.epoch_digest


def test_runtime_trust_surface_to_dict_has_no_secrets():
    data = surface().to_dict()
    assert set(data) == {
        "code_revision",
        "policy_fingerprint",
        "tool_catalog_digest",
        "effect_digest",
        "assurance_policy_digest",
        "workspace_manifest_digest",
    }


def test_runtime_trust_epoch_schema_validation():
    with pytest.raises(ValueError, match="schema"):
        RuntimeTrustEpoch(2, surface())


@pytest.mark.parametrize("revision", [0, -1, True])
def test_runtime_model_binding_revision_validation(revision):
    with pytest.raises(ValueError, match="revision"):
        RuntimeModelBinding("provider:model", revision, fp("a"))


@pytest.mark.parametrize("digest", ["", "bad", "g" * 64])
def test_runtime_model_binding_digest_validation(digest):
    with pytest.raises(ValueError, match="attestation_digest"):
        RuntimeModelBinding("provider:model", 1, digest)


def test_runtime_epoch_rejects_too_many_models():
    models = tuple(
        RuntimeModelBinding(f"p{i}:m", 1, fp("a"))
        for i in range(129)
    )
    with pytest.raises(ValueError, match="bound"):
        RuntimeTrustEpoch(1, surface(), models)


def test_runtime_guard_rejects_too_many_requirements():
    registry = AIModelRegistry(max_models=256)
    requirements = []
    for index in range(129):
        provider = f"p{index}"
        registry.register(attestation(provider, "m"))
        requirements.append(requirement(provider, "m"))
    with pytest.raises(ValueError, match="bound"):
        AIRuntimeTrustGuard(
            surface(),
            model_admission=AIModelAdmission(registry),
            model_requirements=requirements,
        )


def test_runtime_trust_assurance_production_profile_changes_epoch():
    default = AIExecutionAssuranceInspector()
    production = AIExecutionAssuranceInspector(
        AIExecutionAssurancePolicy.production()
    )
    first = AIRuntimeTrustGuard(
        surface(assurance_policy_digest=default.policy.digest),
        assurance=default,
    ).pin()
    second = AIRuntimeTrustGuard(
        surface(assurance_policy_digest=production.policy.digest),
        assurance=production,
    ).pin()
    assert first.epoch_digest != second.epoch_digest
