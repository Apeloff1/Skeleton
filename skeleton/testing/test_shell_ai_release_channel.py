"""CAS-pinned AI release channel tests."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.diagnostics import AIDiagnosticsReport
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.eval_runner import AIEvalCaseResult, AIEvalRun
from skeleton.shells.ai.model_port import ModelCapabilities
from skeleton.shells.ai.provider_attestation import AttestationReport, ProviderAttestation
from skeleton.shells.ai.red_team import AIRedTeamResult
from skeleton.shells.ai.release_channel import (
    AIReleaseChannelStore,
    ReleaseChannelConflict,
)
from skeleton.shells.ai.release_evidence import ReleaseEvidenceBuilder
from skeleton.shells.ai.release_registry import AIReleaseRegistry
from skeleton.shells.ai.safety_case import AISafetyCaseBuilder
from skeleton.shells.ai.signed_artifact import ArtifactSigner


def fp(char):
    return char * 64


def evidence(release_id):
    run = AIEvalRun(
        "dataset",
        1,
        fp("d"),
        "model",
        (
            AIEvalCaseResult(
                "c",
                True,
                (),
                fp("p"),
                1,
                False,
                1,
            ),
        ),
    )
    safety = AISafetyCaseBuilder().build(
        diagnostics=AIDiagnosticsReport(()),
        eval_run=run,
        red_team=(AIRedTeamResult("r", True, ("x",), ()),),
        attestation=AttestationReport(True, ()),
    )
    attestation = ProviderAttestation(
        "provider",
        "model",
        "1",
        "adapter",
        ModelCapabilities(),
        (1,),
        fp("t"),
    )
    return ReleaseEvidenceBuilder().build(
        release_id=release_id,
        code_revision="abc",
        policy_fingerprint=fp("q"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        eval_dataset_digest=fp("d"),
        eval_run_payload=run.to_dict(),
        provider_attestation=attestation,
        safety_case=safety,
    )


def active_release(release_id):
    registry = AIReleaseRegistry(ArtifactSigner("key", b"k" * 32))
    registry.register(evidence(release_id))
    return registry.activate(release_id)


def test_release_channel_requires_active_release():
    registry = AIReleaseRegistry(ArtifactSigner("key", b"k" * 32))
    release = registry.register(evidence("r"))
    with pytest.raises(ValueError, match="active"):
        AIReleaseChannelStore.from_release("prod", release)


def test_release_channel_initial_set_revision_one():
    store = AIReleaseChannelStore(InMemoryFencedStore())
    state = store.from_release("prod", active_release("r"))
    revision, current = store.set(state)
    assert revision == 1
    assert current.release_id == "r"


def test_release_channel_current():
    store = AIReleaseChannelStore(InMemoryFencedStore())
    state = store.from_release("prod", active_release("r"))
    store.set(state)
    revision, current = store.current("prod")
    assert revision == 1
    assert current == state


def test_release_channel_cas_update():
    backend = InMemoryFencedStore()
    store = AIReleaseChannelStore(backend)
    first = store.from_release("prod", active_release("r1"))
    store.set(first)
    second = store.from_release("prod", active_release("r2"))
    revision, current = store.set(second, expected_revision=1)
    assert revision == 2
    assert current.release_id == "r2"


def test_release_channel_stale_update_conflict():
    backend = InMemoryFencedStore()
    left = AIReleaseChannelStore(backend)
    right = AIReleaseChannelStore(backend)
    left.set(left.from_release("prod", active_release("r1")))
    left.set(
        left.from_release("prod", active_release("r2")),
        expected_revision=1,
    )
    with pytest.raises(ReleaseChannelConflict):
        right.set(
            right.from_release("prod", active_release("r3")),
            expected_revision=1,
        )


def test_release_channel_signature_is_pinned():
    release = active_release("r")
    state = AIReleaseChannelStore.from_release("prod", release)
    assert state.registry_signature == release.signature.signature
    assert state.evidence_digest == release.evidence.digest


def test_release_channels_are_independent():
    backend = InMemoryFencedStore()
    store = AIReleaseChannelStore(backend)
    release = active_release("r")
    store.set(store.from_release("canary", release))
    store.set(store.from_release("prod", release))
    assert store.current("canary")[0] == 1
    assert store.current("prod")[0] == 1
