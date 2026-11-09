from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.ai.integrations.xai_oss import (
    GROK1_ARCHITECTURE,
    PUBLIC_SURFACES,
    DelegationMode,
    Grok1ModelMaterialization,
    Grok1WeightArtifact,
    GrokDelegationRequest,
    LicenseDisposition,
    XAIOptionalDependencyError,
    source,
)
from skeleton.ai.integrations.xai_oss.optional import load_optional


def test_grok1_architecture_matches_pinned_release_shape() -> None:
    architecture = GROK1_ARCHITECTURE
    assert architecture.parameters_billions == 314.0
    assert architecture.experts == 8
    assert architecture.active_experts_per_token == 2
    assert architecture.layers == 64
    assert architecture.query_heads == 48
    assert architecture.key_value_heads == 8
    assert architecture.embedding_size == 6144
    assert architecture.vocabulary_size == 131072
    assert architecture.maximum_context_tokens == 8192


def test_grok1_materialization_never_downloads_implicitly(tmp_path: Path) -> None:
    artifact = Grok1WeightArtifact(tmp_path)
    materialization = Grok1ModelMaterialization(artifact)
    with pytest.raises(RuntimeError, match="implicit network download is disabled"):
        materialization.require_local_or_explicit_network()

    (tmp_path / "ckpt-0").mkdir()
    materialization.require_local_or_explicit_network()


def test_grok1_network_materialization_requires_explicit_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source_uri"):
        Grok1ModelMaterialization(
            Grok1WeightArtifact(tmp_path),
            allow_network_download=True,
        )


def test_non_admitted_xai_sources_cannot_be_loaded_as_runtime_dependencies() -> None:
    prompts = source("grok-prompts")
    assert prompts.disposition is LicenseDisposition.METADATA_ONLY
    with pytest.raises(XAIOptionalDependencyError, match="not admitted"):
        load_optional(prompts, "grok_prompts", importer=lambda _: object())


def test_delegation_digest_is_deterministic_and_path_bounded() -> None:
    first = GrokDelegationRequest(
        objective="Review the execution plane",
        workspace_id="repo-1",
        mode="review",
        effort="high",
        allowed_paths=("skeleton/ai", "scripts"),
        metadata={"b": "2", "a": "1"},
    )
    second = GrokDelegationRequest(
        objective="Review the execution plane",
        workspace_id="repo-1",
        mode=DelegationMode.REVIEW,
        effort="high",
        allowed_paths=("skeleton/ai", "scripts"),
        metadata={"a": "1", "b": "2"},
    )
    assert first.digest == second.digest

    with pytest.raises(ValueError, match="relative"):
        GrokDelegationRequest(
            objective="x",
            workspace_id="repo-1",
            mode="review",
            allowed_paths=("/etc",),
        )


def test_public_proto_inventory_includes_chat_compaction_and_streaming() -> None:
    chat = next(surface for surface in PUBLIC_SURFACES if surface.service == "Chat")
    assert "GetCompletionChunk" in chat.operations
    assert "StartDeferredCompletion" in chat.operations
    assert "CompactContext" in chat.operations
