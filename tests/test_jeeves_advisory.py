"""Multimodal input is explicitly approved, locally stored advisory *text*.

Exercises the real authenticated localhost server and real native transformer.
The source artifact hash is correctly labelled as caller-asserted: neither
image nor audio decoder is faked by the tests or the application.
"""
from __future__ import annotations

from hashlib import sha256
from http.client import HTTPConnection
import json
from pathlib import Path
import threading

import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.ai.runtime.inference.local import LocalInferenceEngine
from skeleton.app.offline_http import OfflineHTTPApplication, LocalOnlyHTTPServer
from skeleton.app.jeeves_advisory import (
    SCHEMA, AdvisoryRejected, prepare_advisory,
)
from skeleton.cortex.transformer import TinyTransformer


_TOKEN = "t" * 64


def advisory(**changes):
    observation = "The local rasterizer uses integer edge equations for coverage."
    result = {
        "schema_version": SCHEMA,
        "modality": "video-frames",
        "title": "Local graphics recording",
        "observation": observation,
        "observation_sha256": sha256(observation.encode()).hexdigest(),
        "source_sha256": "a" * 64,
        "reviewed": True,
    }
    result.update(changes)
    return result


@pytest.mark.parametrize("change,phrase", [
    ({"modality": "hosted-ai"}, "modality"),
    ({"modality": ["video-frames"]}, "modality"),
    ({"modality": "openai"}, "modality"),
    ({"title": "../traversal"}, "title"),
    ({"title": "Long " + "x" * 160}, "title"),
    ({"observation": ""}, "observation"),
    ({"observation": "A" * 13_000}, "12 KiB"),
    ({"observation": "bad\x00bytes"}, "observation"),
    ({"observation": "local rasterizer changed"}, "differs"),
    ({"observation_sha256": "bad"}, "SHA-256"),
    ({"source_sha256": "a" * 63}, "SHA-256"),
    ({"reviewed": False}, "owner review"),
    ({"reviewed": "yes"}, "owner review"),
    ({"schema_version": "skeleton.jeeves.advisory.v0"}, "schema"),
])
def test_advisory_rejects_unreviewed_corrupt_or_hosted_source(change, phrase):
    with pytest.raises(AdvisoryRejected, match=phrase):
        prepare_advisory(advisory(**change))


def test_advisory_provenance_separates_caller_source_claim_from_observation_hash():
    supplied = advisory()
    record = prepare_advisory(supplied)
    assert record["observation_sha256"] == supplied["observation_sha256"]
    assert record["source_sha256"] == "a" * 64
    assert record["advisory_sha256"] == sha256(record["text"].encode()).hexdigest()
    assert "UNTRUSTED JEEVES ADVISORY" in record["text"]
    assert "Caller-declared source SHA-256" in record["text"]
    assert "Verified observation SHA-256" in record["text"]
    assert record["text"].endswith(supplied["observation"])
    assert not any(value in record["text"] for value in ("OPENAI_API_KEY", "REMOTE_PROVIDER_KEY"))


@pytest.fixture
def localhost(tmp_path):
    model = NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "local", "rasterizer",
               "integer", "edge", "equations", "coverage", ".", " "),
        dim=8, ctx=1024, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )))
    app = OfflineHTTPApplication(model, tmp_path / "advisory.sqlite3", token=_TOKEN)
    server = LocalOnlyHTTPServer(app, port=0)
    worker = threading.Thread(target=server.serve_forever,
                              kwargs={"poll_interval": 0.05}, daemon=True)
    worker.start()

    def request(method, path, body=None, authorized=True):
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=20)
        headers = {"Accept": "application/json"}
        if authorized:
            headers["Authorization"] = "Bearer " + _TOKEN
        payload = None if body is None else json.dumps(body).encode()
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            conn.request(method, path, body=payload, headers=headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()
    try:
        yield request
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=6)
        app.close()


def test_advisory_is_authenticated_and_requires_owner_review(localhost):
    status, _ = localhost("POST", "/v1/advisory/ingest", advisory(), authorized=False)
    assert status == 401
    status, denied = localhost("POST", "/v1/advisory/ingest", advisory(reviewed=False))
    assert status == 403
    assert "owner review" in denied["error"]
    status, listed = localhost("GET", "/v1/knowledge/documents")
    assert status == 200 and listed["documents"] == []


def test_advisory_uses_real_sqlite_custody_and_never_becomes_primary_model(localhost):
    status, capabilities = localhost("GET", "/v1/advisory/status")
    assert status == 200 and capabilities["advisory_never_primary_model"] is True
    assert capabilities["raw_media_decoding"] is False
    assert capabilities["network_provider_dispatch"] is False
    status, admitted = localhost("POST", "/v1/advisory/ingest", advisory())
    assert status == 201
    assert admitted["source_digest_authority"] == "caller-declared-not-media-verified"
    assert admitted["observation_digest_authority"] == "server-verified-exact-text"
    assert admitted["primary_model_unchanged"] is True
    assert admitted["generation_performed"] is False
    assert admitted["remote_provider_called"] is False
    assert admitted["grounding_requires_explicit_turn"] is True
    assert len(admitted["advisory_sha256"]) == 64
    status, repeated = localhost("POST", "/v1/advisory/ingest", advisory())
    assert status == 200
    assert repeated["reused"] is True
    assert repeated["document_id"] == admitted["document_id"]
    status, document = localhost("GET", "/v1/knowledge/documents/" + admitted["document_id"])
    assert status == 200
    assert document["sha256"] == admitted["advisory_sha256"]
    assert "UNTRUSTED JEEVES ADVISORY" in document["text"]
    status, docs = localhost("GET", "/v1/knowledge/documents")
    assert status == 200 and len(docs["documents"]) == 1


def test_explicit_grounded_turn_keeps_reviewed_multimodal_observation_out_of_system_role(localhost, monkeypatch):
    status, admitted = localhost("POST", "/v1/advisory/ingest", advisory())
    assert status == 201
    st, created = localhost("POST", "/v1/sessions", {})
    assert st == 201
    sid = created["session_id"]
    captured = []
    original = LocalInferenceEngine.generate

    async def observing(engine, request, **kwargs):
        captured.append(request)
        return await original(engine, request, **kwargs)

    monkeypatch.setattr(LocalInferenceEngine, "generate", observing)
    st, answer = localhost("POST", "/v1/sessions/" + sid + "/turn", {
        "message": "How does rasterizer integer edge coverage work?",
        "request_id": "explicit-advisory-grounding-1",
        "max_output_tokens": 2,
        "grounded": True,
    })
    assert st == 200, answer
    assert answer["replayed"] is False
    assert answer["evidence"]["claim"] == "source_passages_supplied_not_answer_verification"
    assert captured and captured[0].instructions == ""
    assert captured[0].prompt.startswith("How does rasterizer integer edge coverage work?")
    assert "UNTRUSTED LOCAL REFERENCES" in captured[0].prompt
    assert admitted["document_id"] == answer["evidence"]["citations"][0]["document_id"]
    st, session = localhost("GET", "/v1/sessions/" + sid)
    assert st == 200
    assert session["revision"] == 1
    assert session["messages"][0]["content"] == "How does rasterizer integer edge coverage work?"
    assert session["evidence"][0] == answer["evidence"]
