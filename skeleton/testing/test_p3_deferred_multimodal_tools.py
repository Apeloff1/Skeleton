from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.extensions import (
    AudioAsset,
    AudioSegment,
    ConnectorDefinition,
    ConnectorRegistry,
    ImageAsset,
    ImageRegion,
    MarketplacePackage,
    MarketplaceVerifier,
    MediaMetadata,
    MediaTransform,
    MultimodalAsset,
    MultimodalHit,
    MultimodalQuery,
    MultimodalRegistry,
    OCRSpan,
    PackageAttestation,
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
    detect_document_text_conflict,
    fuse_scores,
    sample_video_timestamps,
)


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _asset(label: str = "asset", *, size: int = 12) -> MultimodalAsset:
    return MultimodalAsset(
        asset_id=label,
        media_type="image/png",
        source_digest=_d(label),
        byte_size=size,
        trust_label="trusted",
        classification="internal",
        metadata={"source": "fixture"},
    )


def test_multimodal_asset_identity_is_deterministic() -> None:
    assert _asset().digest == _asset().digest
    assert _asset("a").digest != _asset("b").digest


def test_media_metadata_requires_coherent_dimensions_and_finite_duration() -> None:
    metadata = MediaMetadata("image/png", "png", width=640, height=480)
    assert len(metadata.digest) == 64
    with pytest.raises(ValueError, match="supplied together"):
        MediaMetadata("image/png", "png", width=640)
    with pytest.raises(ValueError, match="duration"):
        MediaMetadata("audio/wav", "wav", duration_seconds=float("inf"))


def test_multimodal_registry_rejects_byte_bomb_before_decode() -> None:
    registry = MultimodalRegistry(limits=ResourceLimits(max_bytes=8))
    with pytest.raises(ValueError, match="byte limit"):
        registry.register_asset(_asset(size=9))


def test_image_budget_and_region_geometry_fail_closed() -> None:
    registry = MultimodalRegistry(limits=ResourceLimits(max_pixels=100))
    with pytest.raises(ValueError, match="pixel limit"):
        registry.register_image(ImageAsset(_d("huge"), 11, 10, "png"))

    image = ImageAsset(_d("image"), 20, 10, "png")
    ImageRegion(image.asset_digest, 0, 0, 20, 10).validate_within(image)
    with pytest.raises(ValueError, match="beyond source image"):
        ImageRegion(image.asset_digest, 19, 0, 2, 2).validate_within(image)


def test_ocr_confidence_is_bounded() -> None:
    with pytest.raises(ValueError, match="confidence"):
        OCRSpan(_d("doc"), 1, "hello", 0, 0, 10, 10, 1.01)


def test_document_vision_detects_ocr_text_layer_conflict() -> None:
    assert detect_document_text_conflict("same   text", "same text") is False
    assert detect_document_text_conflict("invoice total 10", "invoice total 100") is True


def test_audio_segment_preserves_source_time_bounds() -> None:
    asset = AudioAsset(_d("audio"), 48_000, 2, 10.0)
    AudioSegment(asset.asset_digest, 1.0, 2.0).validate_within(asset)
    with pytest.raises(ValueError, match="exceeds"):
        AudioSegment(asset.asset_digest, 9.0, 11.0).validate_within(asset)


def test_audio_and_video_resource_budgets_reject_oversize_media() -> None:
    registry = MultimodalRegistry(
        limits=ResourceLimits(max_audio_seconds=2.0, max_video_seconds=2.0, max_frames=30)
    )
    with pytest.raises(ValueError, match="audio exceeds"):
        registry.register_audio(AudioAsset(_d("long-audio"), 16_000, 1, 2.1))
    with pytest.raises(ValueError, match="video exceeds configured duration"):
        registry.register_video(VideoAsset(_d("long-video"), 320, 240, 2.1, 10.0))
    with pytest.raises(ValueError, match="frame budget"):
        registry.register_video(VideoAsset(_d("dense-video"), 320, 240, 2.0, 16.0))


def test_transform_lineage_is_content_addressed_and_ordered() -> None:
    registry = MultimodalRegistry()
    source = _d("source")
    middle = _d("middle")
    output = _d("output")
    t1 = MediaTransform("decode", source, middle, "image", {"codec": "png"})
    t2 = MediaTransform("crop", middle, output, "image", {"x": 0, "y": 0})
    registry.register_transform(t1)
    registry.register_transform(t2)
    assert registry.lineage(output) == (t1, t2)


def test_transform_cannot_claim_identity_transform() -> None:
    registry = MultimodalRegistry()
    same = _d("same")
    with pytest.raises(ValueError, match="distinct output"):
        registry.register_transform(MediaTransform("noop", same, same, "image"))


def test_speech_provisional_text_is_not_authoritative() -> None:
    session = SpeechSession("speech-1")
    session.transition("active")
    session.append(TranscriptSegment("speech-1", 0, "provisional", 0.0, 0.5, False))
    assert session.authoritative_text == ""
    session.append(TranscriptSegment("speech-1", 1, "final", 0.0, 0.7, True))
    assert session.authoritative_text == "final"


def test_speech_state_machine_reconnect_and_barge_in_are_explicit() -> None:
    session = SpeechSession("speech-2")
    with pytest.raises(ValueError, match="invalid speech transition"):
        session.transition("closed")
    session.transition("active")
    session.transition("reconnecting")
    session.transition("active")
    session.transition("barge_in")
    session.transition("active")
    session.transition("closed")
    with pytest.raises(ValueError, match="invalid speech transition"):
        session.transition("active")


def test_speech_sequence_mismatch_fails_closed() -> None:
    session = SpeechSession("speech-3")
    session.transition("active")
    with pytest.raises(ValueError, match="sequence"):
        session.append(TranscriptSegment("speech-3", 2, "late", 0.0, 0.1, False))


def test_speech_backpressure_and_timestamp_regression_fail_closed() -> None:
    session = SpeechSession("speech-4", max_segments=1)
    session.transition("active")
    session.append(TranscriptSegment("speech-4", 0, "one", 1.0, 1.1, False))
    with pytest.raises(BufferError, match="backpressure"):
        session.append(TranscriptSegment("speech-4", 1, "two", 1.1, 1.2, False))

    ordered = SpeechSession("speech-5")
    ordered.transition("active")
    ordered.append(TranscriptSegment("speech-5", 0, "one", 2.0, 2.1, False))
    with pytest.raises(ValueError, match="monotonic"):
        ordered.append(TranscriptSegment("speech-5", 1, "two", 1.0, 1.1, False))


def test_video_sampling_plan_is_bounded_before_decode() -> None:
    video = VideoAsset(_d("sample-video"), 640, 360, 5.0, 30.0)
    assert sample_video_timestamps(video, interval_seconds=2.0, max_samples=3) == (0.0, 2.0, 4.0)
    with pytest.raises(ValueError, match="max_samples"):
        sample_video_timestamps(video, interval_seconds=1.0, max_samples=3)


def _hit(
    label: str,
    *,
    score: float,
    tenant: str = "tenant-a",
    classification: str = "internal",
    trust: str = "trusted",
    modality: str = "image",
    epoch: int = 1,
) -> MultimodalHit:
    return MultimodalHit(
        asset_digest=_d(label),
        modality=modality,
        tenant_id=tenant,
        classification=classification,
        trust_label=trust,
        score=score,
        indexed_epoch=epoch,
        evidence_digest=_d(label + "-evidence"),
    )


def test_retrieval_filters_security_boundaries_before_ranking() -> None:
    registry = MultimodalRegistry()
    allowed = _hit("allowed", score=0.5)
    registry.index(allowed)
    registry.index(_hit("wrong-tenant", score=999.0, tenant="tenant-b"))
    registry.index(_hit("secret", score=999.0, classification="secret"))
    registry.index(_hit("untrusted", score=999.0, trust="untrusted"))
    registry.index(_hit("future", score=999.0, epoch=10))
    registry.index(_hit("audio", score=999.0, modality="audio"))

    evidence = registry.retrieve(
        MultimodalQuery(
            text="find it",
            modalities=("image",),
            tenant_id="tenant-a",
            allowed_classifications=frozenset({"internal"}),
            allowed_trust_labels=frozenset({"trusted"}),
            as_of_epoch=2,
        )
    )
    assert evidence.hits == (allowed,)


def test_retrieval_order_is_deterministic_for_equal_scores() -> None:
    registry = MultimodalRegistry()
    left = _hit("left", score=0.7)
    right = _hit("right", score=0.7)
    registry.index(right)
    registry.index(left)
    query = MultimodalQuery(
        "x",
        ("image",),
        "tenant-a",
        frozenset({"internal"}),
        frozenset({"trusted"}),
    )
    first = registry.retrieve(query)
    second = registry.retrieve(query)
    assert first.digest == second.digest
    assert [h.asset_digest for h in first.hits] == sorted([left.asset_digest, right.asset_digest])


def test_cross_modal_fusion_deduplicates_evidence_at_max_score() -> None:
    weak = _hit("same", score=0.1)
    strong = _hit("same", score=0.9)
    fused = fuse_scores(((weak,), (strong,)))
    assert fused == (strong,)


def _tool(*, side_effect: str = "write", idempotency: str = "non_idempotent") -> ToolDefinition:
    return ToolDefinition(
        name="write-record",
        version="1",
        input_schema={"type": "object", "properties": {"value": {"type": "integer"}}},
        output_schema={"type": "object"},
        authority_scope=frozenset({"records.write"}),
        side_effect_class=side_effect,
        idempotency=idempotency,
        timeout_seconds=1.0,
    )


def test_tool_definition_rejects_non_object_schema() -> None:
    with pytest.raises(ValueError, match="object schema"):
        ToolDefinition(
            name="bad",
            version="1",
            input_schema={"type": "string"},
            output_schema={"type": "object"},
            authority_scope=frozenset({"read"}),
            side_effect_class="read",
            idempotency="idempotent",
            timeout_seconds=1.0,
        )


def test_tool_registry_cannot_self_authorize() -> None:
    registry = ToolRegistry()
    definition = _tool(idempotency="idempotent")
    registry.register(definition, lambda args: {"value": args["value"]})
    invocation = ToolInvocation(
        "call-1",
        definition.digest,
        {"value": 7},
        frozenset({"records.write"}),
    )
    with pytest.raises(PermissionError, match="external authority"):
        registry.invoke(invocation, authorize=lambda _definition, _invocation: False)


def test_tool_scope_escalation_is_rejected_before_execution() -> None:
    called = False

    def execute(_args):
        nonlocal called
        called = True
        return {}

    registry = ToolRegistry()
    definition = _tool(idempotency="idempotent")
    registry.register(definition, execute)
    invocation = ToolInvocation(
        "call-2",
        definition.digest,
        {},
        frozenset({"records.write", "admin"}),
    )
    with pytest.raises(PermissionError, match="outside tool declaration"):
        registry.invoke(invocation, authorize=lambda _definition, _invocation: True)
    assert called is False


def test_non_idempotent_tool_requires_idempotency_key() -> None:
    registry = ToolRegistry()
    definition = _tool()
    registry.register(definition, lambda _args: {"ok": True})
    invocation = ToolInvocation(
        "call-3",
        definition.digest,
        {},
        frozenset({"records.write"}),
    )
    with pytest.raises(ValueError, match="idempotency_key"):
        registry.invoke(invocation, authorize=lambda _definition, _invocation: True)


def test_authorized_tool_execution_emits_bounded_receipt() -> None:
    registry = ToolRegistry()
    definition = _tool(idempotency="idempotent")
    registry.register(definition, lambda args: {"echo": args["value"]})
    invocation = ToolInvocation(
        "call-4",
        definition.digest,
        {"value": 3},
        frozenset({"records.write"}),
    )
    times = iter((10.0, 10.25))
    result = registry.invoke(
        invocation,
        authorize=lambda _definition, _invocation: True,
        now=lambda: next(times),
    )
    assert result.status == "succeeded"
    assert result.output == {"echo": 3}
    assert result.finished_at - result.started_at == pytest.approx(0.25)


def _connector() -> ConnectorDefinition:
    return ConnectorDefinition(
        connector_id="docs",
        version="1",
        read_scopes=frozenset({"docs.read"}),
        write_scopes=frozenset({"docs.write"}),
        page_size_limit=100,
        requests_per_minute=60,
        error_semantics={"rate_limited": "retry_after", "unauthorized": "reauth"},
    )


def test_connector_scope_escalation_is_rejected() -> None:
    registry = ConnectorRegistry()
    definition = _connector()
    digest = registry.register(definition)
    with pytest.raises(PermissionError, match="exceeds connector declaration"):
        registry.open_session(
            digest,
            session_id="s1",
            credential_handle="vault://connector/docs",
            read_scopes=("docs.read", "admin"),
        )


def test_connector_session_rejects_inline_secret_material() -> None:
    registry = ConnectorRegistry()
    definition = _connector()
    digest = registry.register(definition)
    with pytest.raises(ValueError, match="opaque handle"):
        registry.open_session(
            digest,
            session_id="s2",
            credential_handle="Bearer not-a-handle",
            read_scopes=("docs.read",),
        )


def _plugin(*, api: str = "v1") -> PluginManifest:
    return PluginManifest(
        plugin_id="example",
        version="1.0.0",
        entrypoint="example:plugin",
        capabilities=frozenset({"documents"}),
        permissions=frozenset({"docs.read"}),
        compatible_api_versions=frozenset({api}),
        package_digest=_d("plugin-package"),
    )


def test_plugin_incompatible_api_is_rejected() -> None:
    registry = PluginRegistry(api_version="v1")
    with pytest.raises(ValueError, match="incompatible"):
        registry.install(_plugin(api="v2"))


def test_plugin_grant_cannot_exceed_manifest_permissions() -> None:
    registry = PluginRegistry(api_version="v1")
    manifest = _plugin()
    registry.install(manifest)
    with pytest.raises(PermissionError, match="exceeds manifest"):
        registry.enable(PluginGrant(manifest.digest, frozenset({"docs.read", "admin"}), "operator"))


def test_plugin_must_disable_before_removal_and_leave_no_residue() -> None:
    registry = PluginRegistry(api_version="v1")
    manifest = _plugin()
    registry.install(manifest)
    registry.enable(PluginGrant(manifest.digest, frozenset({"docs.read"}), "operator"))
    with pytest.raises(ValueError, match="disable"):
        registry.remove(manifest.digest)
    registry.disable(manifest.digest)
    with pytest.raises(ValueError, match="residue"):
        registry.remove(manifest.digest, residue_keys=("plugin.cache",))
    removed = registry.remove(manifest.digest)
    assert removed.state == "removed"


def _package(*, permissions=frozenset({"docs.read"})) -> MarketplacePackage:
    return MarketplacePackage(
        package_id="example",
        version="1.0.0",
        content_digest=_d("package-content"),
        manifest_digest=_d("package-manifest"),
        provenance={"builder": "fixture", "source": "git:test"},
        requested_permissions=permissions,
    )


def test_marketplace_attestation_accepts_known_key_and_policy() -> None:
    package = _package()
    key = b"test-key-material"
    verifier = MarketplaceVerifier({"root": key}, allowed_permissions=("docs.read",))
    signature = verifier.sign_for_test(package, key=key)
    attestation = PackageAttestation(package.digest, "root", "test-ca", signature)
    assert verifier.verify(package, attestation) is True
    assert verifier.quarantine_reason(package.digest) is None


def test_marketplace_bad_signature_is_quarantined() -> None:
    package = _package()
    verifier = MarketplaceVerifier({"root": b"right-key"}, allowed_permissions=("docs.read",))
    bad = PackageAttestation(package.digest, "root", "test-ca", "0" * 64)
    assert verifier.verify(package, bad) is False
    assert verifier.quarantine_reason(package.digest) == "invalid package attestation"


def test_marketplace_permission_overreach_is_quarantined() -> None:
    package = _package(permissions=frozenset({"docs.read", "admin"}))
    key = b"test-key-material"
    verifier = MarketplaceVerifier({"root": key}, allowed_permissions=("docs.read",))
    attestation = PackageAttestation(
        package.digest,
        "root",
        "test-ca",
        verifier.sign_for_test(package, key=key),
    )
    assert verifier.verify(package, attestation) is False
    assert "permission" in (verifier.quarantine_reason(package.digest) or "")


def test_marketplace_revocation_overrides_valid_attestation() -> None:
    package = _package()
    key = b"test-key-material"
    verifier = MarketplaceVerifier({"root": key}, allowed_permissions=("docs.read",))
    attestation = PackageAttestation(
        package.digest,
        "root",
        "test-ca",
        verifier.sign_for_test(package, key=key),
    )
    assert verifier.verify(package, attestation) is True
    verifier.revoke(package.digest, reason="security incident", revoked_by="security")
    assert verifier.is_revoked(package.digest) is True
    assert verifier.verify(package, attestation) is False
