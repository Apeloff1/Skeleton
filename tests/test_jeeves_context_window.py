"""2026 Jeeves strict-context prototype: real native tokenizer and SQLite HTTP.

Unlike a planning document, these tests execute the actual local model
boundary. Source-native TinyTransformer is not operator-owned GGUF quality,
the mobile installer, or full-system release qualification.
"""
from __future__ import annotations

from hashlib import sha256

import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.local_ai import (
    OfflineAIError, OfflineAISession, _strict_context_digest,
)
from skeleton.app.offline_http import OfflineHTTPApplication, OfflineHTTPError
from skeleton.cortex.transformer import TinyTransformer


def native_model() -> NativeRuntimeLocalModel:
    return NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer",
               "local", "offline", "jeeves", "computer", ".", " "),
        dim=8, ctx=1024, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )))


def test_strict_and_legacy_digest_domains_are_distinct_and_boolean_checked():
    digest = sha256(b"immutable request contents").hexdigest()
    assert _strict_context_digest(digest, False) == digest
    strict = _strict_context_digest(digest, True)
    assert strict != digest
    assert len(strict) == 64
    assert strict == _strict_context_digest(digest, True)
    with pytest.raises(OfflineAIError):
        _strict_context_digest(digest, 1)
    with pytest.raises(OfflineAIError):
        _strict_context_digest("invalid", True)


def test_real_native_context_preflight_is_readonly_and_counts_retained_history():
    session = OfflineAISession(native_model())
    original = (("user", "hello"), ("assistant", "world"))
    session.history = original
    preview = session.preview_context("hello", 2)
    assert preview["schema"] == "skeleton.jeeves.local-context-preview.v1"
    assert preview["read_only"] is True
    assert preview["generation_performed"] is False
    assert preview["accounting"] == "exact-native-tokenizer"
    assert preview["gguf_final_tokenizer_admission_required"] is False
    assert preview["estimated_input_tokens"] > 0
    assert preview["estimated_total_tokens"] <= preview["context_tokens"]
    assert preview["reserved_output_tokens"] == 2
    assert preview["full_history_messages"] == len(original)
    assert preview["retained_history_messages"] == len(original)
    assert preview["omitted_history_messages"] == 0
    assert preview["fits_full_history"] is True
    assert session.history == original


def test_full_history_policy_denies_silent_trimming_but_preserves_source_history():
    session = OfflineAISession(native_model())
    original = (("user", "hello " * 180), ("assistant", "world " * 180)) * 9
    session.history = original
    preview = session.preview_context("hello", 2)
    assert preview["fits_full_history"] is False
    assert preview["omitted_history_messages"] >= 2
    assert preview["omitted_history_messages"] % 2 == 0
    assert preview["retained_history_messages"] + preview["omitted_history_messages"] == len(original)
    with pytest.raises(OfflineAIError, match="full conversation exceeds model context"):
        session._request("hello", 2, require_full_history=True)
    bounded, used = session._request("hello", 2, require_full_history=False)
    assert used != original
    assert used == original[-len(used):] if used else True
    assert bounded.history == used
    assert session.history == original


@pytest.mark.parametrize("policy", [None, 0, 1, "", "true", {}, []])
def test_native_context_policy_refuses_nonboolean_requests(policy):
    session = OfflineAISession(native_model())
    with pytest.raises(OfflineAIError, match="full-history policy must be a boolean"):
        session._request("hello", 2, require_full_history=policy)


def test_real_authenticated_http_preflight_has_no_storage_or_inference_side_effect(tmp_path):
    app = OfflineHTTPApplication(
        native_model(), tmp_path / "jeeves-context.sqlite3", token="t" * 64,
    )
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        code, report = app.dispatch("POST", f"/v1/sessions/{sid}/context-preview", {
            "message": "hello", "max_output_tokens": 2,
            "grounded": False, "require_full_history": True,
        })
        assert code == 200
        assert report["session_id"] == sid
        assert report["session_revision"] == 0
        assert report["may_submit_under_policy"] is True
        assert report["preview_is_admission_proof"] is False
        assert report["model_digest"] == app.model_digest
        assert report["generation_performed"] is False
        assert report["older_messages_were_deleted"] is False
        _, saved = app.dispatch("GET", f"/v1/sessions/{sid}")
        assert saved["revision"] == 0 and saved["messages"] == []
    finally:
        app.close()


def test_context_preview_fails_closed_for_invalid_schema_and_missing_grounding(tmp_path):
    app = OfflineHTTPApplication(
        native_model(), tmp_path / "jeeves-context-errors.sqlite3", token="t" * 64,
    )
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        endpoint = f"/v1/sessions/{sid}/context-preview"
        for body in [
            {"message": "hello", "require_full_history": "true"},
            {"message": "hello", "require_full_history": 1},
            {"message": "hello", "grounded": "false"},
            {"message": "hello", "extra": "not admitted"},
            {"message": " "},
            {"message": "hello", "max_output_tokens": 0},
        ]:
            with pytest.raises(OfflineHTTPError) as err:
                app.dispatch("POST", endpoint, body)
            assert err.value.status == 400
        with pytest.raises(OfflineHTTPError) as no_hits:
            app.dispatch("POST", endpoint, {"message": "hello", "grounded": True})
        assert no_hits.value.status == 422
        _, after = app.dispatch("GET", f"/v1/sessions/{sid}")
        assert after["revision"] == 0 and after["messages"] == []
    finally:
        app.close()


def test_http_request_identity_binds_strict_policy_independently_of_grounding(tmp_path):
    app = OfflineHTTPApplication(
        native_model(), tmp_path / "jeeves-context-identity.sqlite3", token="t" * 64,
    )
    try:
        original = {"message": "hello", "request_id": "stable-2026",
                    "max_output_tokens": 2}
        rid, ordinary = app._turn_identity(original, 2)
        assert rid == "stable-2026"
        assert app._turn_identity({**original, "require_full_history": False}, 2)[1] == ordinary
        strict = app._turn_identity({**original, "require_full_history": True}, 2)[1]
        assert strict != ordinary
        grounded = app._turn_identity({**original, "grounded": True}, 2)[1]
        assert grounded != strict
        strict_grounded = app._turn_identity({
            **original, "grounded": True, "require_full_history": True,
        }, 2)[1]
        assert strict_grounded not in {ordinary, strict, grounded}
        with pytest.raises(OfflineHTTPError):
            app._turn_identity({**original, "require_full_history": 1}, 2)
    finally:
        app.close()


def test_genuine_native_http_turn_with_strict_full_context_commits_and_replays(tmp_path):
    app = OfflineHTTPApplication(
        native_model(), tmp_path / "jeeves-context-native.sqlite3", token="t" * 64,
    )
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        request = {"message": "hello", "request_id": "strict-native-2026",
                   "max_output_tokens": 2, "require_full_history": True}
        status, generated = app.dispatch("POST", f"/v1/sessions/{sid}/turn", request)
        assert status == 200
        assert generated["replayed"] is False
        assert generated["output_tokens"] == 2
        assert len(generated["text"]) > 0
        assert generated["output_digest"] == sha256(generated["text"].encode("utf-8")).hexdigest()
        status, replay = app.dispatch("POST", f"/v1/sessions/{sid}/turn", request)
        assert status == 200 and replay["text"] == generated["text"]
        assert replay["replayed"] is True
        _, saved = app.dispatch("GET", f"/v1/sessions/{sid}")
        assert saved["revision"] == 1
        assert [m["content"] for m in saved["messages"] if m["role"] == "assistant"] == [generated["text"]]
        # One request ID must not be replayed as a different context policy.
        with pytest.raises(Exception):
            app.dispatch("POST", f"/v1/sessions/{sid}/turn", {
                **request, "require_full_history": False,
            })
        _, after = app.dispatch("GET", f"/v1/sessions/{sid}")
        assert after["revision"] == 1
    finally:
        app.close()


def test_live_browser_exposes_context_preflight_and_strict_dispatch_contract():
    from skeleton.app.offline_web import HTML, JAVASCRIPT
    for name in ("context-preserve", "context-preview", "context-report"):
        assert f'id="{name}"' in HTML
    assert 'id="context-preserve" type="checkbox" checked' in HTML
    assert "/context-preview" in JAVASCRIPT
    assert "previewLocalContext(message, max_output_tokens, grounded, require_full_history)" in JAVASCRIPT
    assert "payload.may_submit_under_policy === true" in JAVASCRIPT
    assert "request = {session_id: state.session, message, grounded, max_output_tokens," in JAVASCRIPT
    assert "original.require_full_history === require_full_history" in JAVASCRIPT
    assert "require_full_history: true" in JAVASCRIPT
    assert "OL DER" not in JAVASCRIPT
