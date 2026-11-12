"""Owner-selected, model-scoped local grounding is real inference, not a spec.

Tests use a genuine tiny native transformer and immutable SQLite evidence.
They do not claim model-quality or operator-owned GGUF/device validation.
"""
from __future__ import annotations

from hashlib import sha256
import time

import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.offline_grounding import (
    normalized_document_scope, grounded_request_digest,
    scoped_grounded_request_digest,
)
from skeleton.app.offline_http import OfflineHTTPApplication, OfflineHTTPError
from skeleton.cortex.transformer import TinyTransformer


def native_model():
    return NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world",
               "answer", "local", "offline", "jeeves", ".", " "),
        dim=8, ctx=1024, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )))


def add_sources(app):
    sources = []
    for title, content in (
        ("Rasterizer A", "The local rasterizer uses integer edge equations for coverage."),
        ("Rasterizer B", "Rasterizer edge coverage can use fixed-point math on a local device."),
    ):
        status, row = app.dispatch("POST", "/v1/knowledge/documents", {
            "title": title, "text": content,
        })
        assert status == 201
        sources.append(row["document_id"])
    return sources


def make_app(tmp_path):
    return OfflineHTTPApplication(
        native_model(), tmp_path / "local-scoped-grounding.sqlite3",
        token="t" * 64,
    )


def test_selected_document_scope_is_canonical_and_domain_separated():
    ids = ("a" * 24, "z" * 24)
    assert normalized_document_scope(list(reversed(ids))) == ids
    assert normalized_document_scope(ids) == ids
    assert normalized_document_scope(None) is None
    root = grounded_request_digest("a" * 64)
    assert scoped_grounded_request_digest(root, None) == root
    scoped = scoped_grounded_request_digest(root, ids)
    assert len(scoped) == 64 and scoped != root
    assert scoped == scoped_grounded_request_digest(root, tuple(reversed(ids)))
    assert scoped != scoped_grounded_request_digest(root, (ids[0],))
    with pytest.raises(RuntimeContractError):
        scoped_grounded_request_digest("not-a-sha", ids)


@pytest.mark.parametrize("scope", [
    [], ["a" * 24, "a" * 24], ["../../escaped"], ["a" * 101],
    ["x" * 7], ["a" * 24] * 9, [5], ["a" * 24, None],
    "a" * 24, {"id": "a" * 24}, True,
])
def test_selected_document_scope_denies_invalid_ids_without_fallback(scope):
    with pytest.raises(RuntimeContractError):
        normalized_document_scope(scope)


def test_local_library_search_restricts_actual_verified_model_scoped_chunks(tmp_path):
    app = make_app(tmp_path)
    try:
        first, second = add_sources(app)
        query = "rasterizer edge coverage"
        ordinary = app.knowledge.search(query, limit=12)
        assert {x["document_id"] for x in ordinary} == {first, second}
        selected = app.knowledge.search(query, limit=12, document_ids=[first])
        assert selected and all(row["document_id"] == first for row in selected)
        assert all(row["document_sha256"] and row["passage"] for row in selected)
        reverse = app.knowledge.search(query, limit=12, document_ids=[second])
        assert reverse and all(row["document_id"] == second for row in reverse)
        with pytest.raises(RuntimeContractError, match="unavailable"):
            app.knowledge.search(query, document_ids=["z" * 24])
        app.dispatch("DELETE", "/v1/knowledge/documents/" + first)
        with pytest.raises(RuntimeContractError, match="unavailable"):
            app.knowledge.search(query, document_ids=[first])
    finally:
        app.close()


def test_scoped_grounding_preview_real_native_generation_and_durable_replay(tmp_path):
    app = make_app(tmp_path)
    try:
        first, second = add_sources(app)
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        question = "How does rasterizer edge coverage work?"
        endpoint = "/v1/sessions/" + sid
        preview_code, preview = app.dispatch("POST", endpoint + "/context-preview", {
            "message": question, "grounded": True,
            "require_full_history": True, "max_output_tokens": 2,
            "document_ids": [first],
        })
        assert preview_code == 200
        assert preview["generation_performed"] is False
        assert preview["document_scope"] == [first]
        assert preview["grounding_preview"]["source_count"] >= 1
        assert all(citation["document_id"] == first
                   for citation in preview["grounding_preview"]["citations"])
        _, saved = app.dispatch("GET", endpoint)
        assert saved["revision"] == 0
        request = {
            "message": question, "grounded": True,
            "max_output_tokens": 2, "require_full_history": True,
            "request_id": "selected-grounding-native-2026",
            "document_ids": [first],
        }
        status, generated = app.dispatch("POST", endpoint + "/turn", request)
        assert status == 200 and generated["replayed"] is False
        assert generated["text"].strip()
        assert generated["output_digest"] == sha256(
            generated["text"].encode("utf-8")
        ).hexdigest()
        assert generated["local_execution_receipt"]["output_sha256"] == generated["output_digest"]
        assert generated["evidence"]["citations"] == preview["grounding_preview"]["citations"]
        assert generated["evidence"]["context_sha256"] == preview["grounding_preview"]["context_sha256"]
        assert all(citation["document_id"] == first for citation in generated["evidence"]["citations"])
        status, replay = app.dispatch("POST", endpoint + "/turn", request)
        assert status == 200 and replay["replayed"] is True
        assert replay["text"] == generated["text"]
        for mutated in (
            {**request, "document_ids": [second]},
            {k: v for k, v in request.items() if k != "document_ids"},
        ):
            with pytest.raises((RuntimeContractError, OfflineHTTPError)):
                app.dispatch("POST", endpoint + "/turn", mutated)
        _, after = app.dispatch("GET", endpoint)
        assert after["revision"] == 1
        assert after["evidence"][0] == generated["evidence"]
    finally:
        app.close()


def test_missing_or_withdrawn_selected_reference_denies_without_model_generation(tmp_path):
    app = make_app(tmp_path)
    try:
        first, second = add_sources(app)
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        endpoint = "/v1/sessions/" + sid
        invalid_requests = [
            {"message": "rasterizer edge coverage", "grounded": False,
             "document_ids": [first]},
            {"message": "rasterizer edge coverage", "grounded": True,
             "document_ids": [first, first]},
            {"message": "rasterizer edge coverage", "grounded": True,
             "document_ids": None},
        ]
        for request in invalid_requests:
            with pytest.raises(OfflineHTTPError) as err:
                app.dispatch("POST", endpoint + "/context-preview", request)
            assert err.value.status == 400
        app.dispatch("DELETE", "/v1/knowledge/documents/" + first)
        for suffix, body in (
            ("/context-preview", {"message": "rasterizer edge coverage", "grounded": True,
                                  "max_output_tokens": 2, "document_ids": [first]}),
            ("/turn", {"message": "rasterizer edge coverage", "grounded": True,
                       "max_output_tokens": 2, "request_id": "deleted-scoped-id",
                       "document_ids": [first]}),
        ):
            with pytest.raises(OfflineHTTPError) as err:
                app.dispatch("POST", endpoint + suffix, body)
            assert err.value.status == 422
        _, saved = app.dispatch("GET", endpoint)
        assert saved["revision"] == 0
        # A different local document is still available; the selected query
        # is NEVER silently broadened back to it.
        assert app.knowledge.search("rasterizer edge coverage", document_ids=[second])
    finally:
        app.close()


def test_scoped_async_job_finalizes_against_same_native_sqlite_receipt(tmp_path):
    app = make_app(tmp_path)
    try:
        selected, _ = add_sources(app)
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        request = {
            "message": "rasterizer edge coverage", "grounded": True,
            "document_ids": [selected], "max_output_tokens": 2,
            "request_id": "scoped-async-2026", "require_full_history": True,
        }
        status, queued = app.dispatch("POST", f"/v1/sessions/{sid}/turns", request)
        assert status == 202 and queued["request_id"] == request["request_id"]
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            final = app.turn_status(sid, request["request_id"])
            if final["terminal"]:
                break
            time.sleep(0.02)
        assert final["state"] == "complete", final
        answer = final["result"]
        assert answer["replayed"] is False
        assert answer["evidence"]["citations"]
        assert all(c["document_id"] == selected for c in answer["evidence"]["citations"])
        assert answer["local_execution_receipt"]["output_sha256"] == answer["output_digest"]
        _, saved = app.dispatch("GET", f"/v1/sessions/{sid}")
        assert saved["revision"] == 1
    finally:
        app.close()


def test_scope_controls_are_wired_to_local_browser_without_persistent_account_storage():
    from skeleton.app.offline_web import HTML, JAVASCRIPT
    assert 'id="knowledge-scope-status"' in HTML
    for snippet in (
        "selectedKnowledgeIds: new Set()",
        "knowledge-scope-picker",
        "knowledgeScopeStatus()",
        "selectedKnowledgeIds.clear()",
        "document_scope",
        "document_ids",
        "JSON.stringify(original.document_ids || [])",
        "const scope = grounded ? Array.from(state.selectedKnowledgeIds).sort()",
        "row.append(scopeLabel, open, remove)",
    ):
        assert snippet in JAVASCRIPT
    assert "localStorage" not in JAVASCRIPT
    assert "sessionStorage" not in JAVASCRIPT
