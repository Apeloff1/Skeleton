from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.extensions import (
    MediaMetadata,
    MediaTransform,
    MultimodalAsset,
    MultimodalHit,
    MultimodalQuery,
    MultimodalRegistry,
    PluginGrant,
    PluginManifest,
    PluginRegistry,
    ResourceLimits,
    SpeechSession,
    ToolDefinition,
    ToolInvocation,
    ToolRegistry,
    TranscriptSegment,
    VideoAsset,
    sample_video_timestamps,
)


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _tool() -> ToolDefinition:
    return ToolDefinition(
        name="mutate-record",
        version="1",
        input_schema={"type": "object", "properties": {"value": {"type": "integer"}}},
        output_schema={"type": "object"},
        authority_scope=frozenset({"records.write"}),
        side_effect_class="write",
        idempotency="non_idempotent",
        timeout_seconds=1.0,
    )


def _call(
    tool: ToolDefinition,
    *,
    invocation_id: str,
    key: str,
    value: int = 1,
) -> ToolInvocation:
    return ToolInvocation(
        invocation_id=invocation_id,
        tool_digest=tool.digest,
        arguments={"value": value},
        requested_scope=frozenset({"records.write"}),
        idempotency_key=key,
    )


def _plugin(*, package: str = "package-a", entrypoint: str = "demo:plugin") -> PluginManifest:
    return PluginManifest(
        plugin_id="demo",
        version="1.0.0",
        entrypoint=entrypoint,
        capabilities=frozenset({"documents"}),
        permissions=frozenset({"docs.read"}),
        compatible_api_versions=frozenset({"v1"}),
        package_digest=_d(package),
    )


def test_non_idempotent_replay_executes_side_effect_once() -> None:
    tool = _tool()
    executions: list[int] = []
    authorizations: list[str] = []
    registry = ToolRegistry()
    registry.register(
        tool,
        lambda args: executions.append(int(args["value"])) or {"value": args["value"]},
    )

    first = registry.invoke(
        _call(tool, invocation_id="call-1", key="effect-1"),
        authorize=lambda _definition, invocation: authorizations.append(invocation.invocation_id) or True,
        now=iter((1.0, 1.1)).__next__,
    )
    replay = registry.invoke(
        _call(tool, invocation_id="call-2", key="effect-1"),
        authorize=lambda _definition, invocation: authorizations.append(invocation.invocation_id) or True,
        now=lambda: (_ for _ in ()).throw(AssertionError("replay must not execute or sample time")),
    )

    assert replay == first
    assert executions == [1]
    assert authorizations == ["call-1", "call-2"]
    assert registry.idempotency_record_count == 1


def test_idempotency_key_is_bound_to_semantic_invocation() -> None:
    tool = _tool()
    executions: list[int] = []
    registry = ToolRegistry()
    registry.register(
        tool,
        lambda args: executions.append(int(args["value"])) or {"value": args["value"]},
    )
    registry.invoke(
        _call(tool, invocation_id="call-1", key="effect-1", value=1),
        authorize=lambda *_: True,
        now=iter((1.0, 1.1)).__next__,
    )

    with pytest.raises(ValueError, match="different semantic invocation"):
        registry.invoke(
            _call(tool, invocation_id="call-2", key="effect-1", value=2),
            authorize=lambda *_: True,
        )
    assert executions == [1]


def test_idempotent_replay_still_rechecks_current_authority() -> None:
    tool = _tool()
    executions = 0

    def execute(_args):
        nonlocal executions
        executions += 1
        return {"ok": True}

    registry = ToolRegistry()
    registry.register(tool, execute)
    invocation = _call(tool, invocation_id="call-1", key="effect-1")
    registry.invoke(
        invocation,
        authorize=lambda *_: True,
        now=iter((10.0, 10.1)).__next__,
    )

    with pytest.raises(PermissionError, match="external authority"):
        registry.invoke(
            _call(tool, invocation_id="call-2", key="effect-1"),
            authorize=lambda *_: False,
        )
    assert executions == 1


def test_idempotency_ledger_capacity_fails_closed_without_eviction() -> None:
    tool = _tool()
    executions: list[int] = []
    registry = ToolRegistry(max_idempotency_records=1)
    registry.register(
        tool,
        lambda args: executions.append(int(args["value"])) or {"value": args["value"]},
    )
    registry.invoke(
        _call(tool, invocation_id="call-1", key="effect-1"),
        authorize=lambda *_: True,
        now=iter((1.0, 1.1)).__next__,
    )

    with pytest.raises(BufferError, match="capacity exhausted"):
        registry.invoke(
            _call(tool, invocation_id="call-2", key="effect-2"),
            authorize=lambda *_: True,
        )
    assert executions == [1]


@pytest.mark.parametrize("capacity", [True, 0, -1, 1.5])
def test_tool_registry_rejects_invalid_idempotency_capacity(capacity) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        ToolRegistry(max_idempotency_records=capacity)


def test_tool_invocation_rejects_blank_idempotency_key() -> None:
    tool = _tool()
    with pytest.raises(ValueError, match="idempotency_key"):
        ToolInvocation(
            invocation_id="call",
            tool_digest=tool.digest,
            arguments={},
            requested_scope=frozenset({"records.write"}),
            idempotency_key="   ",
        )


def test_plugin_reinstall_does_not_reset_enabled_lifecycle() -> None:
    registry = PluginRegistry(api_version="v1")
    manifest = _plugin()
    installed = registry.install(manifest)
    enabled = registry.enable(
        PluginGrant(
            plugin_digest=manifest.digest,
            granted_permissions=frozenset({"docs.read"}),
            issued_by="operator",
        )
    )
    replay = registry.install(manifest)

    assert installed.state == "installed"
    assert enabled.state == "enabled"
    assert replay == enabled
    assert registry.state(manifest.digest).state == "enabled"


def test_plugin_id_version_cannot_be_rebound_to_different_content() -> None:
    registry = PluginRegistry(api_version="v1")
    registry.install(_plugin(package="package-a"))
    with pytest.raises(ValueError, match="immutable content"):
        registry.install(_plugin(package="package-b"))


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"max_bytes": True}, "max_bytes"),
        ({"max_pixels": False}, "max_pixels"),
        ({"max_frames": 1.5}, "max_frames"),
        ({"max_audio_seconds": float("inf")}, "max_audio_seconds"),
        ({"max_video_seconds": float("nan")}, "max_video_seconds"),
    ],
)
def test_resource_limits_reject_ambiguous_or_nonfinite_numbers(kwargs, field: str) -> None:
    with pytest.raises(ValueError, match=field):
        ResourceLimits(**kwargs)


def test_media_metadata_rejects_boolean_dimensions_and_rates() -> None:
    with pytest.raises(ValueError, match="width"):
        MediaMetadata("image/png", "png", width=True, height=10)
    with pytest.raises(ValueError, match="sample_rate_hz"):
        MediaMetadata("audio/wav", "wav", sample_rate_hz=True)


def test_multimodal_asset_rejects_boolean_byte_size() -> None:
    with pytest.raises(ValueError, match="byte_size"):
        MultimodalAsset(
            asset_id="asset",
            media_type="image/png",
            source_digest=_d("asset"),
            byte_size=True,
            trust_label="trusted",
            classification="internal",
        )


def test_query_requires_unique_modalities_and_explicit_security_filters() -> None:
    with pytest.raises(ValueError, match="unique"):
        MultimodalQuery(
            "q",
            ("image", "image"),
            "tenant",
            frozenset({"internal"}),
            frozenset({"trusted"}),
        )
    with pytest.raises(ValueError, match="filters"):
        MultimodalQuery(
            "q",
            ("image",),
            "tenant",
            frozenset(),
            frozenset({"trusted"}),
        )
    with pytest.raises(ValueError, match="as_of_epoch"):
        MultimodalQuery(
            "q",
            ("image",),
            "tenant",
            frozenset({"internal"}),
            frozenset({"trusted"}),
            as_of_epoch=True,
        )


def test_transform_output_identity_cannot_be_rebound_to_second_lineage() -> None:
    registry = MultimodalRegistry()
    output = _d("output")
    first = MediaTransform("decode", _d("source-a"), output, "image")
    second = MediaTransform("decode", _d("source-b"), output, "image")
    registry.register_transform(first)

    with pytest.raises(ValueError, match="different lineage"):
        registry.register_transform(second)
    assert registry.lineage(output) == (first,)


def test_retrieval_evidence_identity_is_immutable_and_duplicate_safe() -> None:
    registry = MultimodalRegistry()
    hit = MultimodalHit(
        asset_digest=_d("asset"),
        modality="image",
        tenant_id="tenant",
        classification="internal",
        trust_label="trusted",
        score=-0.25,
        indexed_epoch=1,
        evidence_digest=_d("evidence"),
    )
    registry.index(hit)
    registry.index(hit)
    conflicting = MultimodalHit(
        asset_digest=hit.asset_digest,
        modality=hit.modality,
        tenant_id=hit.tenant_id,
        classification=hit.classification,
        trust_label=hit.trust_label,
        score=0.9,
        indexed_epoch=hit.indexed_epoch,
        evidence_digest=hit.evidence_digest,
    )
    with pytest.raises(ValueError, match="already bound"):
        registry.index(conflicting)

    result = registry.retrieve(
        MultimodalQuery(
            "q",
            ("image",),
            "tenant",
            frozenset({"internal"}),
            frozenset({"trusted"}),
        )
    )
    assert result.hits == (hit,)


def test_speech_provisional_can_be_atomically_finalized_without_new_sequence() -> None:
    session = SpeechSession("speech")
    session.transition("active")
    session.append(TranscriptSegment("speech", 0, "hel", 0.0, 0.3, False))
    assert session.authoritative_text == ""

    session.finalize_provisional(
        TranscriptSegment("speech", 0, "hello", 0.0, 0.5, True)
    )
    assert len(session.segments) == 1
    assert session.segments[0].final is True
    assert session.authoritative_text == "hello"


def test_speech_finalization_rejects_nonfinal_replacement() -> None:
    session = SpeechSession("speech")
    session.transition("active")
    session.append(TranscriptSegment("speech", 0, "draft", 0.0, 0.1, False))
    with pytest.raises(ValueError, match="same provisional segment"):
        session.finalize_provisional(
            TranscriptSegment("speech", 0, "still draft", 0.0, 0.2, False)
        )


def test_video_sampling_rejects_boolean_sample_budget() -> None:
    video = VideoAsset(_d("video"), 320, 240, 1.0, 30.0)
    with pytest.raises(ValueError, match="max_samples"):
        sample_video_timestamps(video, interval_seconds=0.5, max_samples=True)
