"""Workspace manifests, governance artifact signing, cache, and idempotency tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.idempotency import (
    AIIdempotencyConflict,
    AIIdempotencyRegistry,
)
from skeleton.shells.ai.plan_cache import AIPlanCache
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
)
from skeleton.shells.ai.types import AIAction, AIPlanProposal
from skeleton.shells.ai.workspace_manifest import (
    WorkspaceDrift,
    WorkspaceEntry,
    WorkspaceEntryKind,
    WorkspaceManifest,
    WorkspaceManifestComparator,
)


def fp(char):
    return char * 64


def entry(path, digest="a", size=1):
    return WorkspaceEntry(
        path,
        WorkspaceEntryKind.FILE,
        fp(digest),
        size_bytes=size,
        mode=0o644,
    )


def proposal(proposal_id="p"):
    return AIPlanProposal(
        proposal_id,
        "i",
        (AIAction("a", "python"),),
        confidence=0.9,
        uncertainty=0.1,
    )


def test_workspace_manifest_sorts_entries():
    manifest = WorkspaceManifest(
        "m",
        (
            entry("z"),
            entry("a"),
        ),
    )
    assert [item.path for item in manifest.entries] == ["a", "z"]


def test_workspace_manifest_duplicate_path_rejected():
    with pytest.raises(ValueError):
        WorkspaceManifest("m", (entry("a"), entry("a")))


def test_workspace_manifest_digest_stable():
    manifest = WorkspaceManifest("m", (entry("a"),))
    assert len(manifest.digest) == 64
    assert manifest.digest == manifest.digest


def test_workspace_manifest_digest_changes_with_content_digest():
    first = WorkspaceManifest("m", (entry("a", "a"),))
    second = WorkspaceManifest("m", (entry("a", "b"),))
    assert first.digest != second.digest


def test_workspace_manifest_comparator_clean():
    first = WorkspaceManifest("m1", (entry("a"),))
    second = WorkspaceManifest("m2", (entry("a"),))
    drift = WorkspaceManifestComparator().compare(first, second)
    assert drift.clean


def test_workspace_manifest_comparator_added():
    first = WorkspaceManifest("m1", (entry("a"),))
    second = WorkspaceManifest("m2", (entry("a"), entry("b")))
    drift = WorkspaceManifestComparator().compare(first, second)
    assert drift.added == ("b",)
    assert not drift.clean


def test_workspace_manifest_comparator_removed():
    first = WorkspaceManifest("m1", (entry("a"), entry("b")))
    second = WorkspaceManifest("m2", (entry("a"),))
    drift = WorkspaceManifestComparator().compare(first, second)
    assert drift.removed == ("b",)


def test_workspace_manifest_comparator_changed():
    first = WorkspaceManifest("m1", (entry("a", "a"),))
    second = WorkspaceManifest("m2", (entry("a", "b"),))
    drift = WorkspaceManifestComparator().compare(first, second)
    assert drift.changed == ("a",)


def test_artifact_sign_and_verify():
    signer = ArtifactSigner("key-1", b"k" * 32)
    artifact = signer.sign(
        "release-evidence",
        fp("a"),
        metadata={"env": "prod"},
    )
    signer.verify(artifact)
    assert artifact.key_id == "key-1"
    assert artifact.metadata["env"] == "prod"


def test_artifact_signature_detects_digest_tamper():
    signer = ArtifactSigner("key-1", b"k" * 32)
    artifact = signer.sign("release-evidence", fp("a"))
    tampered = replace(artifact, artifact_digest=fp("b"))
    with pytest.raises(ArtifactSignatureError):
        signer.verify(tampered)


def test_artifact_signature_detects_signature_tamper():
    signer = ArtifactSigner("key-1", b"k" * 32)
    artifact = signer.sign("release-evidence", fp("a"))
    tampered = replace(artifact, signature="0" * 64)
    with pytest.raises(ArtifactSignatureError):
        signer.verify(tampered)


def test_artifact_key_id_mismatch():
    first = ArtifactSigner("one", b"k" * 32)
    second = ArtifactSigner("two", b"k" * 32)
    artifact = first.sign("x", fp("a"))
    with pytest.raises(ArtifactSignatureError, match="key_id"):
        second.verify(artifact)


def test_artifact_signer_requires_strong_key():
    with pytest.raises(ValueError):
        ArtifactSigner("key", b"short")


def test_idempotency_request_digest():
    registry = AIIdempotencyRegistry()
    assert len(registry.request_digest("hello")) == 64
    assert registry.request_digest("hello") == registry.request_digest(b"hello")


def test_idempotency_register_same_is_idempotent():
    registry = AIIdempotencyRegistry()
    digest = registry.request_digest("request")
    first = registry.register(
        "key",
        request_digest=digest,
        proposal_fingerprint=fp("p"),
    )
    second = registry.register(
        "key",
        request_digest=digest,
        proposal_fingerprint=fp("p"),
    )
    assert first == second


def test_idempotency_request_conflict():
    registry = AIIdempotencyRegistry()
    registry.register(
        "key",
        request_digest=fp("a"),
        proposal_fingerprint=fp("p"),
    )
    with pytest.raises(AIIdempotencyConflict):
        registry.register(
            "key",
            request_digest=fp("b"),
            proposal_fingerprint=fp("p"),
        )


def test_idempotency_proposal_conflict():
    registry = AIIdempotencyRegistry()
    registry.register(
        "key",
        request_digest=fp("a"),
        proposal_fingerprint=fp("p"),
    )
    with pytest.raises(AIIdempotencyConflict):
        registry.register(
            "key",
            request_digest=fp("a"),
            proposal_fingerprint=fp("q"),
        )


def test_idempotency_expiry():
    now = [0.0]
    registry = AIIdempotencyRegistry(clock=lambda: now[0])
    registry.register(
        "key",
        request_digest=fp("a"),
        proposal_fingerprint=fp("p"),
        ttl_seconds=1,
    )
    now[0] = 1
    assert registry.get("key") is None


def test_plan_cache_hit_requires_matching_surfaces():
    cache = AIPlanCache()
    cache.put(
        "k",
        proposal(),
        policy_fingerprint=fp("a"),
        tool_catalog_digest=fp("b"),
        effect_digest=fp("c"),
    )
    hit = cache.get(
        "k",
        policy_fingerprint=fp("a"),
        tool_catalog_digest=fp("b"),
        effect_digest=fp("c"),
    )
    assert hit is not None
    assert hit.hits == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("policy_fingerprint", "x"),
        ("tool_catalog_digest", "y"),
        ("effect_digest", "z"),
    ],
)
def test_plan_cache_surface_drift_evicts(field, value):
    cache = AIPlanCache()
    cache.put(
        "k",
        proposal(),
        policy_fingerprint="a",
        tool_catalog_digest="b",
        effect_digest="c",
    )
    kwargs = {
        "policy_fingerprint": "a",
        "tool_catalog_digest": "b",
        "effect_digest": "c",
    }
    kwargs[field] = value
    assert cache.get("k", **kwargs) is None
    assert cache.get(
        "k",
        policy_fingerprint="a",
        tool_catalog_digest="b",
        effect_digest="c",
    ) is None


def test_plan_cache_expiry():
    now = [0.0]
    cache = AIPlanCache(default_ttl_seconds=1, clock=lambda: now[0])
    cache.put(
        "k",
        proposal(),
        policy_fingerprint="a",
        tool_catalog_digest="b",
        effect_digest="c",
    )
    now[0] = 1
    assert cache.get(
        "k",
        policy_fingerprint="a",
        tool_catalog_digest="b",
        effect_digest="c",
    ) is None


def test_plan_cache_lru_eviction():
    cache = AIPlanCache(max_items=1)
    cache.put(
        "a",
        proposal("a"),
        policy_fingerprint="p",
        tool_catalog_digest="t",
        effect_digest="e",
    )
    cache.put(
        "b",
        proposal("b"),
        policy_fingerprint="p",
        tool_catalog_digest="t",
        effect_digest="e",
    )
    assert cache.get(
        "a",
        policy_fingerprint="p",
        tool_catalog_digest="t",
        effect_digest="e",
    ) is None
    assert cache.get(
        "b",
        policy_fingerprint="p",
        tool_catalog_digest="t",
        effect_digest="e",
    ) is not None
