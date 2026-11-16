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
        assert report["grounding_preview"] is None
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
    assert 'id="context-grounding-preview"' in HTML
    assert 'id="context-grounding-citations"' in HTML
    assert "local-grounding-preview.v1" in JAVASCRIPT
    assert "await exactLocalSha256(row.passage)" in JAVASCRIPT
    assert "passage.textContent = row.passage" in JAVASCRIPT
    assert "clearGroundingPreview()" in JAVASCRIPT
    assert "grounding.future_source_snapshot_guaranteed !== false" in JAVASCRIPT
    assert "OL DER" not in JAVASCRIPT


def test_real_grounded_strict_context_reuses_evidence_identity_but_fences_turn_policy(tmp_path):
    """Native model genuinely generates with reviewed local evidence and full-history safety."""
    app = OfflineHTTPApplication(
        native_model(), tmp_path / "jeeves-context-grounded.sqlite3",
        token="t" * 64,
    )
    try:
        status, _ = app.dispatch("POST", "/v1/knowledge/documents", {
            "title": "Local rasterizer reference",
            "text": "The local rasterizer uses integer edge equations for coverage.",
        })
        assert status in (200, 201)
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        message = "How does rasterizer integer edge coverage work?"
        preview_code, preview = app.dispatch(
            "POST", f"/v1/sessions/{sid}/context-preview", {
                "message": message, "max_output_tokens": 2,
                "grounded": True, "require_full_history": True,
            },
        )
        assert preview_code == 200 and preview["grounded"] is True
        assert preview["fits_full_history"] is True
        assert preview["may_submit_under_policy"] is True
        manifest = preview["grounding_preview"]
        assert manifest["schema"] == "skeleton.jeeves.local-grounding-preview.v1"
        assert manifest["source_authority"] == "untrusted-local-passages-only"
        assert manifest["generation_performed"] is False
        assert manifest["is_committed_inference_evidence"] is False
        assert manifest["future_source_snapshot_guaranteed"] is False
        assert len(manifest["context_sha256"]) == 64
        assert manifest["source_count"] == len(manifest["citations"]) >= 1
        for citation in manifest["citations"]:
            assert citation["passage_sha256"] == sha256(citation["passage"].encode("utf-8")).hexdigest()
            _, document = app.dispatch(
                "GET", "/v1/knowledge/documents/" + citation["document_id"],
            )
            assert document["sha256"] == citation["document_sha256"]
            assert document["text"][citation["char_start"]:citation["char_end"]] == citation["passage"]
        _, before_generation = app.dispatch("GET", f"/v1/sessions/{sid}")
        assert before_generation["revision"] == 0
        status, answer = app.dispatch("POST", f"/v1/sessions/{sid}/turn", {
            "message": message,
            "request_id": "grounded-strict-context-2026",
            "max_output_tokens": 2,
            "grounded": True,
            "require_full_history": True,
        })
        assert status == 200
        assert answer["replayed"] is False
        assert answer["text"].strip()
        assert answer["evidence"]["claim"] == "source_passages_supplied_not_answer_verification"
        assert answer["evidence"]["context_sha256"] == manifest["context_sha256"]
        assert answer["evidence"]["citations"] == manifest["citations"]
        assert answer["local_execution_receipt"]["output_sha256"] == answer["output_digest"]
        assert len(answer["evidence"]["citations"]) >= 1
        _, saved = app.dispatch("GET", f"/v1/sessions/{sid}")
        assert saved["revision"] == 1
        assert saved["messages"][0]["content"] == message
    finally:
        app.close()


# Cognitive preflight is opt-in, and never an alternate generation path.
def _cognitive_report():
    return {"context_tokens": 1024, "estimated_input_tokens": 128,
            "reserved_output_tokens": 64, "omitted_history_messages": 2}


def test_cognitive_plan_exact_unicode_fragments_and_dependency_order():
    from skeleton.app.jeeves_cognitive import build_preview, verify_preview
    question = "Compare 🐉 game design; implement Python code; verify evidence?"
    rows = [
        {"role": "system", "content": "Never recall this system message: game."},
        {"role": "user", "content": "My game design uses a dragon companion."},
        {"role": "assistant", "content": "Fabricated game design fact."},
        {"role": "user", "content": "Python code for the game is offline."},
    ]
    result = build_preview(question, rows, session_revision=2,
                           model_digest="a"*64, tokenizer_digest="b"*64,
                           context_report=_cognitive_report())
    assert verify_preview(result)
    assert result["suggested_effort"] == "deep"
    assert result["budget"]["unreserved_units"] == 832
    assert result["budget"]["recommended_action"] == "review-context"
    assert {row["message_index"] for row in result["memory"]["matches"]} == {1, 3}
    for row in result["request_spans"]:
        assert question[row["start"]:row["end"]] == row["text"]
        assert sha256(row["text"].encode()).hexdigest() == row["sha256"]
    seen = set()
    for step in result["workflow"]:
        assert set(step["depends_on"]).issubset(seen)
        assert step["authority"] == "advice-only"
        seen.add(step["id"])
    assert not result["tool_execution_authorized"]
    assert not result["prompt_modified"]
    assert not result["memory_saved"]
    assert not result["model_quality_measured"]
    result["suggested_effort"] = "brief"
    assert not verify_preview(result)


def test_cognitive_memory_exact_excerpt_deduplicates_and_bounds_scan():
    from skeleton.app.jeeves_cognitive import recall
    text = "prefix " * 200 + "nebula recovery" + " suffix" * 200
    messages = [{"role": "user", "content": "nebula old secret"}] * 140
    messages.extend([{"role": "user", "content": text},
                     {"role": "user", "content": text},
                     {"role": "assistant", "content": "nebula recovery invented"}])
    result = recall("nebula recovery", messages)
    assert result["history_rows_scanned"] == 128
    assert result["scan_truncated"]
    assert result["automatically_injected"] is False
    matches = result["matches"]
    assert len(matches) == 2
    picked = next(row for row in matches if row["message_index"] == 141)
    assert picked["text"] == text[picked["start"]:picked["end"]]
    assert "nebula recovery" in picked["text"]
    assert len(picked["text"]) <= 420
    assert picked["source_sha256"] == sha256(text.encode()).hexdigest()
    assert all(row["role"] == "user" for row in matches)


def test_cognitive_clauses_does_not_discard_tail():
    from skeleton.app.jeeves_cognitive import clauses
    question = "; ".join("clause " + str(i) for i in range(40))
    spans = clauses(question)
    assert len(spans) == 8
    assert spans[-1]["text"].endswith("clause 39")
    assert spans[-1]["end"] == len(question)
    assert spans == sorted(spans, key=lambda row: row["start"])


def test_cognitive_evidence_reports_overlap_not_entailment_and_refuses_forgery():
    from skeleton.app.jeeves_cognitive import build_preview
    passage = "The dragon has a blue wing."
    manifest = {"citations": [
        {"citation": "local:12345678:0:" + "b"*16, "passage": passage,
         "passage_sha256": sha256(passage.encode()).hexdigest()}
    ]}
    params = dict(session_revision=0, model_digest="a"*64, tokenizer_digest="b"*64,
                  context_report=_cognitive_report(), manifest=manifest)
    result = build_preview("dragon wings; unrelated moon", [], **params)
    evidence = result["evidence"]
    assert evidence["source_count"] == 1
    assert evidence["clause_coverage"][0]["any_lexical_overlap"]
    assert not evidence["clause_coverage"][1]["any_lexical_overlap"]
    assert evidence["semantic_entailment_verified"] is False
    manifest["citations"][0]["passage"] = "altered"
    with pytest.raises(ValueError, match="unverified preview passage"):
        build_preview("dragon", [], **params)


@pytest.mark.parametrize("override", [
    {"context_tokens": True}, {"estimated_input_tokens": 0},
    {"reserved_output_tokens": 999}, {"omitted_history_messages": -1},
])
def test_cognitive_budget_rejects_invalid_geometry(override):
    from skeleton.app.jeeves_cognitive import build_preview
    with pytest.raises(ValueError):
        build_preview("hello", [], session_revision=0, model_digest="a"*64,
                      tokenizer_digest="b"*64, context_report=_cognitive_report() | override)


def test_real_context_cognitive_preview_opt_in_and_no_second_generation(tmp_path):
    from skeleton.app.jeeves_cognitive import verify_preview
    app = OfflineHTTPApplication(native_model(), tmp_path / "cognitive.sqlite3",
                                 token="t" * 64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        prefix = f"/v1/sessions/{sid}"
        _, result = app.dispatch("POST", prefix + "/turn", {
            "message": "hello offline", "request_id": "cognitive-original-turn",
            "max_output_tokens": 2,
        })
        assert result["revision"] == 1
        _, before = app.dispatch("GET", prefix)
        _, normal = app.dispatch("POST", prefix + "/context-preview",
                                 {"message": "hello offline", "max_output_tokens": 2})
        assert "cognitive_preview" not in normal
        _, report = app.dispatch("POST", prefix + "/context-preview", {
            "message": "hello offline", "max_output_tokens": 2, "cognitive": True,
        })
        plan = report["cognitive_preview"]
        assert verify_preview(plan)
        assert plan["session_revision"] == 1
        assert plan["memory"]["matches"][0]["text"] == "hello offline"
        assert plan["generation_performed"] is False
        assert report["preview_is_admission_proof"] is False
        _, after = app.dispatch("GET", prefix)
        assert after == before
        with pytest.raises(OfflineHTTPError) as error:
            app.dispatch("POST", prefix + "/context-preview",
                         {"message": "hello", "cognitive": 1})
        assert error.value.status == 400
    finally:
        app.close()
