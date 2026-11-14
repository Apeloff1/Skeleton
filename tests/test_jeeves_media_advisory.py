"""Executable source-byte attestation for Jeeves media advisory, not fake OCR.

The temporary attachment is verified through the authenticated localhost
boundary. The exact raw payload must never enter SQLite, conversation
history, remote providers, a second model or a durable file.
"""
from __future__ import annotations

import base64
from hashlib import sha256
from http.client import HTTPConnection
import json
from pathlib import Path
import threading

import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.jeeves_media_advisory import (
    MAX_MEDIA_BYTES, MAX_MEDIA_REQUEST_BYTES, MediaAdvisoryRejected,
    verify_transient_media,
)
from skeleton.app.jeeves_advisory import (
    SCHEMA, AdvisoryRejected, prepare_advisory,
)
from skeleton.app.offline_http import OfflineHTTPApplication, LocalOnlyHTTPServer
from skeleton.cortex.transformer import TinyTransformer


_TOKEN = "m" * 64
_SECRET_MARKER = b"LOCAL_ONLY_MEDIA_SECRET_DO_NOT_STORE_" + b"z" * 96


def samples() -> list[tuple[str, str, bytes]]:
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" +
           (8).to_bytes(4, "big") + (8).to_bytes(4, "big") +
           b"\x08\x06\x00\x00\x00" + _SECRET_MARKER)
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + _SECRET_MARKER + b"\xff\xd9"
    webp_payload = b"WEBPVP8 " + _SECRET_MARKER
    webp = (b"RIFF" + len(webp_payload).to_bytes(4, "little") + webp_payload)
    wav_payload = b"WAVEfmt " + b"\x10\x00\x00\x00" + b"\x01\x00\x01\x00" + b"\x80\xbb\x00\x00" + b"\x00\xee\x02\x00" + b"\x02\x00\x10\x00" + b"data" + len(_SECRET_MARKER).to_bytes(4, "little") + _SECRET_MARKER
    wav = b"RIFF" + len(wav_payload).to_bytes(4, "little") + wav_payload
    flac = b"fLaC\x80\x00\x00\x00" + _SECRET_MARKER
    mp4 = (24).to_bytes(4, "big") + b"ftypisom" + b"\x00\x00\x02\x00" + b"isom" + _SECRET_MARKER
    return [
        ("image/png", "image-caption", png),
        ("image/jpeg", "image-caption", jpeg),
        ("image/webp", "image-caption", webp),
        ("audio/wav", "audio-transcript", wav),
        ("audio/flac", "audio-transcript", flac),
        ("video/mp4", "video-frames", mp4),
    ]


def reviewed_payload(media_type: str, modality: str, raw: bytes):
    observation = "Owner-reviewed source: this is untrusted, user-written text only."
    return {
        "schema_version": SCHEMA,
        "modality": modality,
        "title": "Reviewed local media specimen",
        "observation": observation,
        "observation_sha256": sha256(observation.encode("utf-8")).hexdigest(),
        "source_sha256": sha256(raw).hexdigest(),
        "media_type": media_type,
        "media_base64": base64.b64encode(raw).decode("ascii"),
        "reviewed": True,
    }


@pytest.mark.parametrize("media_type,modality,raw", samples())
def test_exact_media_bytes_and_container_header_are_verified_but_not_decoded(
    media_type, modality, raw,
):
    supplied = reviewed_payload(media_type, modality, raw)
    attestation = verify_transient_media(supplied)
    assert attestation == {
        "media_type": media_type,
        "media_size_bytes": len(raw),
        "source_sha256": sha256(raw).hexdigest(),
        "media_digest_authority": "server-verified-transient-source-bytes",
        "media_header_authority": "container-header-only-not-decoded",
        "media_bytes_persisted": False,
    }
    prepared = prepare_advisory(supplied)
    assert prepared["source_sha256"] == supplied["source_sha256"]
    assert prepared["media_attestation"] == attestation
    assert "Server-verified transient media SHA-256" in prepared["text"]
    assert "Media bytes inspected, not saved:" in prepared["text"]
    assert "Verified observation SHA-256" in prepared["text"]
    assert "UNTRUSTED JEEVES ADVISORY" in prepared["text"]
    assert supplied["media_base64"] not in prepared["text"]
    assert _SECRET_MARKER.decode("ascii") not in prepared["text"]
    assert prepared["advisory_sha256"] == sha256(prepared["text"].encode("utf-8")).hexdigest()


def test_legacy_crawler_and_text_advisory_never_gain_false_media_authority():
    source = reviewed_payload(*samples()[0])
    source.pop("media_type")
    source.pop("media_base64")
    source["modality"] = "text-reference"
    record = prepare_advisory(source)
    assert "media_attestation" not in record
    assert "Caller-declared source SHA-256" in record["text"]
    assert "Server-verified transient media SHA-256" not in record["text"]
    assert verify_transient_media(source) is None


@pytest.mark.parametrize("alter", [
    lambda p: p.update(media_type="text/plain"),
    lambda p: p.update(media_type="audio/wav"),
    lambda p: p.update(modality="audio-transcript"),
    lambda p: p.update(media_type=None),
    lambda p: p.update(media_base64=None),
    lambda p: p.update(media_base64=[]),
    lambda p: p.update(media_base64="!!!!!!!!"),
    lambda p: p.update(media_base64="AA=A"),
    lambda p: p.update(media_base64=p["media_base64"] + "\n"),
    lambda p: p.update(media_base64=p["media_base64"][:-4] + "AAAA"),
    lambda p: p.update(source_sha256="0" * 64),
    lambda p: p.update(source_sha256="A" * 64),
    lambda p: p.update(media_base64="A" * (MAX_MEDIA_BYTES * 2)),
    lambda p: p.pop("media_type"),
    lambda p: p.pop("media_base64"),
])
def test_media_mismatch_invalid_digest_and_noncanonical_encoding_fail_closed(alter):
    payload = reviewed_payload(*samples()[0])
    alter(payload)
    with pytest.raises((MediaAdvisoryRejected, AdvisoryRejected)):
        prepare_advisory(payload)


@pytest.mark.parametrize("raw", [
    b"\x00" * 64,
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 20,
    b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 8,
    b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" +
        (32769).to_bytes(4, "big") + (1).to_bytes(4, "big") + b"x",
])
def test_header_only_checks_refuse_obviously_invalid_image_signatures(raw):
    payload = reviewed_payload("image/png", "image-caption", raw)
    with pytest.raises(MediaAdvisoryRejected, match="header"):
        verify_transient_media(payload)


def test_zero_and_oversized_payloads_are_never_admitted():
    for raw in (b"", b"\x89PNG\r\n\x1a\n" + b"x" * MAX_MEDIA_BYTES):
        payload = reviewed_payload("image/png", "image-caption", raw)
        with pytest.raises(MediaAdvisoryRejected, match="budget"):
            verify_transient_media(payload)


def test_missing_review_and_changed_observation_deny_without_media_admission():
    media = reviewed_payload(*samples()[0])
    with pytest.raises(AdvisoryRejected, match="owner review"):
        prepare_advisory({**media, "reviewed": False})
    with pytest.raises(AdvisoryRejected, match="differs"):
        prepare_advisory({**media, "observation": "Malicious substituted text"})
    with pytest.raises(AdvisoryRejected, match="unexpected"):
        prepare_advisory({**media, "remote_provider_url": "https://remote.example"})


@pytest.fixture
def local_host(tmp_path: Path):
    model = NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "media", "review", "local",
               "verified", "caption", "answer", ".", " "),
        dim=8, ctx=1024, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )))
    db = tmp_path / "media-local-only.sqlite3"
    app = OfflineHTTPApplication(model, db, token=_TOKEN)
    server = LocalOnlyHTTPServer(app, port=0)
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True,
    )
    worker.start()

    def call(method, path, body=None, *, authorized=True):
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=25)
        headers = {"Accept": "application/json"}
        if authorized:
            headers["Authorization"] = "Bearer " + _TOKEN
        payload = None if body is None else json.dumps(
            body, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            conn.request(method, path, body=payload, headers=headers)
            resp = conn.getresponse()
            return resp.status, json.loads(resp.read().decode("utf-8"))
        finally:
            conn.close()
    call.port = server.server_port
    try:
        yield app, db, call
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=8)
        app.close()


def test_authenticated_loopback_commits_only_reviewed_text_not_raw_media(local_host):
    app, db, call = local_host
    media_type, modality, raw = samples()[0]
    payload = reviewed_payload(media_type, modality, raw)
    code, ignored = call("POST", "/v1/advisory/ingest", payload, authorized=False)
    assert code == 401
    code, denied = call("POST", "/v1/advisory/ingest", {
        **payload, "reviewed": False,
    })
    assert code == 403
    code, inventory = call("GET", "/v1/knowledge/documents")
    assert code == 200 and inventory["documents"] == []
    code, admitted = call("POST", "/v1/advisory/ingest", payload)
    assert code == 201, admitted
    assert admitted["source_sha256"] == sha256(raw).hexdigest()
    assert admitted["source_digest_authority"] == "server-verified-transient-source-bytes"
    assert admitted["observation_digest_authority"] == "server-verified-exact-text"
    assert admitted["media_attestation"]["media_size_bytes"] == len(raw)
    assert admitted["media_attestation"]["media_bytes_persisted"] is False
    assert admitted["reviewed"] is True
    assert admitted["advisory_only"] is True
    assert admitted["primary_model_unchanged"] is True
    assert admitted["generation_performed"] is False
    assert admitted["remote_provider_called"] is False
    assert admitted["grounding_requires_explicit_turn"] is True
    code, doc = call("GET", "/v1/knowledge/documents/" + admitted["document_id"])
    assert code == 200
    assert doc["sha256"] == admitted["advisory_sha256"]
    assert doc["text"] == prepare_advisory(payload)["text"]
    assert payload["media_base64"] not in doc["text"]
    assert raw not in db.read_bytes()
    assert payload["media_base64"].encode("ascii") not in db.read_bytes()
    code, session = call("POST", "/v1/sessions", {})
    assert code == 201
    code, current = call("GET", "/v1/sessions/" + session["session_id"])
    assert code == 200 and current["revision"] == 0
    assert current["messages"] == [] and current["evidence"] == []
    code, replay = call("POST", "/v1/advisory/ingest", payload)
    assert code == 200 and replay["reused"] is True
    assert replay["document_id"] == admitted["document_id"]
    code, inventory = call("GET", "/v1/knowledge/documents")
    assert code == 200 and len(inventory["documents"]) == 1


def test_http_invalid_mime_and_forged_digest_cannot_write_sqlite(local_host):
    app, db, call = local_host
    supplied = reviewed_payload(*samples()[0])
    for mutated in (
        {**supplied, "media_type": "image/svg+xml"},
        {**supplied, "source_sha256": "e" * 64},
        {**supplied, "media_base64": "AA!!"},
        {**supplied, "media_type": "video/mp4"},
        {**supplied, "reviewed": "true"},
    ):
        code, result = call("POST", "/v1/advisory/ingest", mutated)
        assert code in (400, 403), result
    code, inventory = call("GET", "/v1/knowledge/documents")
    assert code == 200 and inventory["documents"] == []


def test_localhost_media_capability_does_not_claim_ocr_or_secondary_provider(local_host):
    _, _, call = local_host
    code, status = call("GET", "/v1/advisory/status")
    assert code == 200
    assert status["primary_inference"] == "local-model-only"
    assert status["advisory_never_primary_model"] is True
    assert status["transient_media_bytes_verified_locally"] is True
    assert status["raw_media_persisted"] is False
    assert status["raw_media_decoding"] is False
    assert status["media_decoder_or_ocr_called"] is False
    assert status["network_provider_dispatch"] is False
    assert status["explicit_grounded_turn_required"] is True


def test_browser_preview_is_local_blob_only_and_no_remote_media_scripts():
    from skeleton.app.offline_web import HTML, JAVASCRIPT
    assert 'id="media-advisory-panel"' in HTML
    for control in (
        "media-advisory-file", "media-advisory-review",
        "media-advisory-observation", "media-advisory-title",
        "media-advisory-preview", "media-advisory-admit",
        "media-advisory-image", "media-advisory-audio", "media-advisory-video",
    ):
        assert f'id="{control}"' in HTML
    for snippet in (
        "allowedLocalMedia", "clearMediaAdvisory(true)",
        "URL.createObjectURL(file)", "URL.revokeObjectURL(state.mediaAdvisoryUrl)",
        "await localMediaSha256(binary)", "crypto.subtle.digest('SHA-256'",
        "media_base64: localMediaBase64(binary)", "reviewed: true",
        "media_bytes_persisted !== false",
        "primary_model_unchanged !== true", "remote_provider_called !== false",
        "get('media-advisory-review').checked",
    ):
        assert snippet in JAVASCRIPT
    assert "localStorage" not in JAVASCRIPT
    assert "sessionStorage" not in JAVASCRIPT


def test_content_security_policy_only_allows_local_blob_media_not_hosted_urls(local_host):
    from skeleton.app.offline_web import HTML, JAVASCRIPT
    _, _, call = local_host
    conn = HTTPConnection("127.0.0.1", call.port, timeout=12)
    try:
        conn.request("GET", "/")
        response = conn.getresponse()
        policy = response.getheader("Content-Security-Policy")
        assert response.status == 200
        response.read()
    finally:
        conn.close()
    assert "default-src 'none'" in policy
    assert "script-src 'self'" in policy
    assert "style-src 'self'" in policy
    assert "connect-src 'self'" in policy
    assert "img-src 'self' blob:" in policy
    assert "media-src 'self' blob:" in policy
    assert "frame-ancestors 'none'" in policy
    assert "https:" not in policy and "http:" not in policy
    assert 'src="http' not in HTML
    assert "https://" not in JAVASCRIPT
    assert "localStorage" not in JAVASCRIPT
    assert "sessionStorage" not in JAVASCRIPT
