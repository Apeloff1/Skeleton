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
    assert "previewLocalContext(message, max_output_tokens, grounded, require_full_history, cognitive = false)" in JAVASCRIPT
    assert "cognitive ? {cognitive: true} : {}" in JAVASCRIPT
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


def _paired_calibration_fixture():
    from scripts.evaluate_jeeves_calibration import _hash
    profiles = []
    for seed in ("c", "d"):
        pair = {"model_sha256": seed*64, "policy_sha256": "e"*64}
        profiles.append({**pair, "profile_sha256": _hash(pair)})
    a, b = [p["profile_sha256"] for p in profiles]
    cases = []
    for i in range(20):
        cases.append({
            "case_sha256": sha256(str(i).encode()).hexdigest(),
            "stratum": "code" if i < 10 else "reasoning",
            "results": {
                a: {"response_sha256": "1"*64, "confidence_ppm": 500_000,
                    "correct": i < 10, "abstained": False, "elapsed_ms": 10},
                b: {"response_sha256": "2"*64, "confidence_ppm": 900_000 if i < 15 else 0,
                    "correct": i < 15, "abstained": i >= 15, "elapsed_ms": 12},
            },
        })
    return {"holdout_sha256": "a"*64, "evaluator_sha256": "b"*64,
            "profiles": profiles, "cases": cases}


def test_paired_calibration_distinguishes_accuracy_coverage_and_uncertainty():
    from scripts.evaluate_jeeves_calibration import evaluate, _hash
    fixture = _paired_calibration_fixture()
    report = evaluate(fixture)
    a, b = [p["profile_sha256"] for p in fixture["profiles"]]
    left, right = report["overall"][a], report["overall"][b]
    assert left["all_case_accuracy"] == .5
    assert left["brier_answered"] == .25
    assert left["ece10_answered"] == 0
    assert right["all_case_accuracy"] == .75
    assert right["coverage"] == .75
    assert right["answered_accuracy"] == 1
    assert right["brier_answered"] == pytest.approx(.01)
    assert right["ece10_answered"] == pytest.approx(.1)
    assert right["risk_coverage"][-1]["selective_accuracy"] is None
    assert report["paired"]["right_only_correct"] == 5
    assert report["paired"]["mcnemar_two_sided_exact_p"] == .0625
    assert report["strata"]["reasoning"][b]["coverage"] == .5
    assert report["production_quality_certified"] is False
    assert report["activation_authorized"] is False
    assert report["report_sha256"] == _hash({
        k: v for k, v in report.items() if k != "report_sha256"})


def test_paired_calibration_fails_closed_on_missing_pairs_and_invalid_labels():
    from scripts.evaluate_jeeves_calibration import evaluate
    fixture = _paired_calibration_fixture()
    a = fixture["profiles"][0]["profile_sha256"]
    fixture["cases"][0]["results"][a]["correct"] = 1
    with pytest.raises(ValueError):
        evaluate(fixture)
    fixture["cases"][0]["results"][a]["correct"] = True
    del fixture["cases"][0]["results"][a]
    with pytest.raises(ValueError, match="complete paired"):
        evaluate(fixture)
    fixture = _paired_calibration_fixture()
    fixture["evaluator_sha256"] = fixture["profiles"][0]["model_sha256"]
    with pytest.raises(ValueError, match="separately"):
        evaluate(fixture)


def test_paired_calibration_rejects_changed_bytes_duplicate_keys_and_nonfinite(tmp_path):
    from scripts.evaluate_jeeves_calibration import load_pinned
    destination = tmp_path / "calibration.json"
    for raw in (b'{"x":1,"x":2}', b'{"x":NaN}'):
        destination.write_bytes(raw)
        with pytest.raises(ValueError):
            load_pinned(destination, sha256(raw).hexdigest())
    destination.write_bytes(b"{}")
    with pytest.raises(ValueError, match="identity"):
        load_pinned(destination, "a"*64)


def _new_memory_session(app):
    _, created = app.dispatch("POST", "/v1/sessions", {})
    sid = created["session_id"]
    prefix = f"/v1/sessions/{sid}"
    text = "hello offline world"
    _, answer = app.dispatch("POST", prefix + "/turn", {
        "message": text, "request_id": "memory-original-turn",
        "max_output_tokens": 2,
    })
    assert answer["revision"] == 1
    selection = {"expected_revision": 1, "message_index": 0,
                 "message_sha256": sha256(text.encode()).hexdigest(),
                 "start": 0, "end": len(text), "kind": "procedure"}
    return prefix, selection


def test_reviewed_memory_exact_approval_duplicate_and_separate_deletion(tmp_path):
    app = OfflineHTTPApplication(native_model(), tmp_path / "reviewed-memory.sqlite3",
                                 token="t"*64)
    try:
        prefix, selection = _new_memory_session(app)
        code, draft = app.dispatch("POST", prefix + "/memory-preview", {"selection": selection})
        assert code == 200 and draft["excerpt"] == "hello offline world"
        assert draft["saved"] is False and draft["auto_applied"] is False
        assert draft["source_deletion_cascades"] is False
        assert app.knowledge.list_documents() == []
        body = {"selection": selection, "approval_sha256": draft["approval_sha256"],
                "approved": True}
        code, result = app.dispatch("POST", prefix + "/memory-save", body)
        assert code == 201 and result["saved"]
        code, repeated = app.dispatch("POST", prefix + "/memory-save", body)
        assert code == 200 and repeated["reused"]
        assert result["document_id"] == repeated["document_id"]
        doc = app.knowledge.get_document(result["document_id"])
        assert doc["text"] == draft["document_text"]
        assert doc["sha256"] == draft["document_sha256"]
        # Cross-session use goes through existing explicitly grounded sources.
        hits = app.knowledge.search("hello offline", document_ids=[doc["document_id"]])
        assert hits and all(hit["document_id"] == doc["document_id"] for hit in hits)
        _, saved = app.dispatch("GET", prefix)
        assert saved["revision"] == 1
        app.dispatch("DELETE", prefix)
        assert app.knowledge.get_document(doc["document_id"])["text"] == doc["text"]
        app.dispatch("DELETE", "/v1/knowledge/documents/" + doc["document_id"])
        assert app.knowledge.list_documents() == []
    finally:
        app.close()


def test_reviewed_memory_rejects_unapproved_assistant_tampering_and_stale_revision(tmp_path):
    app = OfflineHTTPApplication(native_model(), tmp_path / "memory-rejected.sqlite3",
                                 token="t"*64)
    try:
        prefix, selection = _new_memory_session(app)
        _, draft = app.dispatch("POST", prefix + "/memory-preview", {"selection": selection})
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST", prefix + "/memory-preview",
                         {"selection": selection | {"message_index": 1}})
        assert exc.value.status == 400
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST", prefix + "/memory-save", {"selection": selection,
                         "approval_sha256": draft["approval_sha256"], "approved": False})
        assert exc.value.status == 403
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST", prefix + "/memory-save", {"selection": selection | {"kind": "episode"},
                         "approval_sha256": draft["approval_sha256"], "approved": True})
        assert exc.value.status == 409
        app.dispatch("POST", prefix + "/turn", {"message": "world", "max_output_tokens": 2,
                                               "request_id": "memory-revision-next"})
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST", prefix + "/memory-save", {"selection": selection,
                         "approval_sha256": draft["approval_sha256"], "approved": True})
        assert exc.value.status == 409
        assert app.knowledge.list_documents() == []
    finally:
        app.close()


def test_reviewed_memory_source_fence_is_inside_write_transaction(tmp_path, monkeypatch):
    from skeleton.app.jeeves_reviewed_memory import prepare_memory, save_memory, MemoryConflict
    from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
    app = OfflineHTTPApplication(native_model(), tmp_path / "memory-fence.sqlite3",
                                 token="t"*64)
    try:
        prefix, selection = _new_memory_session(app)
        sid = prefix.rsplit("/", 1)[-1]
        draft = prepare_memory(app.knowledge, sid, selection)
        original = app.knowledge.add_text
        observed = []
        def intercept(title, content, *, _source_recheck):
            def fenced():
                observed.append(app._store._db.in_transaction)
                _source_recheck()
                raise MemoryConflict("independent qualification simulated source loss")
            return original(title, content, _source_recheck=fenced)
        monkeypatch.setattr(app.knowledge, "add_text", intercept)
        with pytest.raises(MemoryConflict):
            save_memory(app.knowledge, sid, selection, approved=True,
                        approval_sha256=draft["approval_sha256"])
        assert observed == [True]
        assert not app._store._db.in_transaction
        assert app.knowledge.list_documents() == []
        with OfflineChatStore(app.database) as other:
            assert other.load(sid, app.model_digest, app.tokenizer_digest).revision == 1
    finally:
        app.close()


def test_real_dual_candidate_deliberation_uses_native_model_without_committing(tmp_path):
    app = OfflineHTTPApplication(native_model(), tmp_path / "deliberation.sqlite3",
                                 token="t"*64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        prefix = "/v1/sessions/" + created["session_id"]
        _, before = app.dispatch("GET", prefix)
        code, report = app.dispatch("POST", prefix + "/deliberation-review", {
            "message": "hello", "expected_revision": 0, "approved": True,
            "max_output_tokens": 4,
        })
        assert code == 200 and report["generation_performed"] is True
        assert report["transcript_committed"] is False
        assert report["reserved_total_output_tokens"] == 8
        assert report["actual_total_output_tokens"] <= 8
        assert report["comparison"]["answer_selected"] is False
        assert report["comparison"]["independent_model_count"] == 1
        candidates = report["candidates"]
        assert [c["strategy"] for c in candidates] == ["direct", "counterpoint"]
        assert len({c["question_variant_sha256"] for c in candidates}) == 2
        for candidate in candidates:
            assert candidate["text"].strip()
            assert candidate["output_sha256"] == sha256(candidate["text"].encode()).hexdigest()
            assert len(candidate["execution_receipt_digest"]) == 64
        assert app.dispatch("GET", prefix)[1] == before
        assert app._active_session is None
    finally:
        app.close()


def test_deliberation_rejects_invalid_budget_approval_and_revision(tmp_path):
    app = OfflineHTTPApplication(native_model(), tmp_path / "deliberation-rejected.sqlite3",
                                 token="t"*64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        prefix = "/v1/sessions/" + created["session_id"]
        endpoint = prefix + "/deliberation-review"
        body = {"message": "hello", "expected_revision": 0, "approved": True,
                "max_output_tokens": 2}
        for changes, status in [
            ({"approved": False}, 403), ({"approved": 1}, 403),
            ({"max_output_tokens": 129}, 400), ({"expected_revision": True}, 400),
            ({"expected_revision": 1}, 409), ({"grounded": "true"}, 400),
            ({"message": "x"*1025}, 400), ({"tool": "write"}, 400),
        ]:
            with pytest.raises(OfflineHTTPError) as error:
                app.dispatch("POST", endpoint, body | changes)
            assert error.value.status == status
            assert app._active_session is None
        _, after = app.dispatch("GET", prefix)
        assert after["revision"] == 0
    finally:
        app.close()


def test_deliberation_refuses_source_loss_without_partial_report(tmp_path, monkeypatch):
    import skeleton.app.jeeves_deliberation as module
    app = OfflineHTTPApplication(native_model(), tmp_path / "deliberation-fenced.sqlite3",
                                 token="t"*64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        prefix = "/v1/sessions/" + created["session_id"]
        item = app.knowledge.add_text("Offline reference", "The hello world procedure starts offline.")
        async def interrupted(_backend, _question, **params):
            params["recheck"]()
            app.knowledge.delete(item["document_id"])
            params["recheck"]()
            pytest.fail("source loss must prevent returning a report")
        monkeypatch.setattr(module, "deliberate", interrupted)
        with pytest.raises(OfflineHTTPError) as error:
            app.dispatch("POST", prefix + "/deliberation-review", {
                "message": "hello world", "expected_revision": 0, "approved": True,
                "grounded": True, "document_ids": [item["document_id"]], "max_output_tokens": 2,
            })
        assert error.value.status == 409
        assert app._active_session is None
        assert app.dispatch("GET", prefix)[1]["revision"] == 0
    finally:
        app.close()


def test_grounded_context_preview_accounts_for_exact_rendered_newlines():
    session = OfflineAISession(native_model())
    question, context = "hello", "offline world"
    report = session.preview_context(question, 2, grounding_context=context)
    request, retained = session._request(question + "\n\n" + context, 2)
    expected = len(session.backend.runtime.tokenizer.encode_ids(request.rendered_input))
    assert report["estimated_input_tokens"] == expected
    assert report["retained_history_messages"] == len(retained)


def test_local_research_review_runs_multi_hop_lexical_and_preserves_explicit_scope(tmp_path):
    app = OfflineHTTPApplication(native_model(), tmp_path / "research-review.sqlite3",
                                 token="t"*64)
    try:
        a = app.knowledge.add_text("Recovery module", "Nebula recovery uses XA-193.")
        b = app.knowledge.add_text("Module detail", "XA-193 restores offline backup state.")
        other = app.knowledge.add_text("Unselected source", "Nebula recovery unrelated secret.")
        scope = sorted([a["document_id"], b["document_id"]])
        endpoint = "/v1/knowledge/research-review"
        body = {"query": "Nebula recovery", "document_ids": scope, "approved": True}
        status, report = app.dispatch("POST", endpoint, body)
        assert status == 200 and report["ranking"] == "lexical"
        assert report["document_scope"] == scope
        assert report["network_called"] is False and report["generation_performed"] is False
        assert report["semantic_entailment_verified"] is False
        assert len(report["trace"]["queries"]) <= 6
        assert any(q["parent_citation"] for q in report["trace"]["queries"])
        assert report["sources"]
        assert other["document_id"] not in {s["document_id"] for s in report["sources"]}
        for row in report["sources"]:
            original = app.knowledge.get_document(row["document_id"])
            assert original["text"][row["char_start"]:row["char_end"]] == row["passage"]
            assert sha256(row["passage"].encode()).hexdigest() == row["passage_sha256"]
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST", endpoint, body | {"approved": False})
        assert exc.value.status == 403
        app.knowledge.delete(b["document_id"])
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST", endpoint, body)
        assert exc.value.status == 422
        # A withdrawn explicit scope must not broaden to the other document.
        assert len(app.knowledge.list_documents()) == 2
    finally:
        app.close()


def test_local_research_review_no_evidence_is_not_generation(tmp_path):
    app = OfflineHTTPApplication(native_model(), tmp_path / "research-empty.sqlite3",
                                 token="t"*64)
    try:
        code, report = app.dispatch("POST", "/v1/knowledge/research-review",
                                   {"query": "nebula", "approved": True})
        assert code == 200 and report["sources"] == []
        assert report["trace"]["status"] == "no_evidence"
        assert report["trace"]["semantic_entailment_verified"] is False
        assert report["generation_performed"] is False
    finally:
        app.close()



@pytest.mark.parametrize("expression,answer", [
    ("(17+5)*3/2", "33"),
    ("1/3 + 1/6", "0.5"),
    ("2**-4", "1/16"),
    ("-(3-7)*2", "8"),
    ("1/3", "1/3"),
])
def test_adaptive_exact_rational_arithmetic(expression, answer):
    from skeleton.app.jeeves_constraints import assess, digest
    contract = {"kind": "arithmetic", "expression": expression}
    row = assess(answer, contract)
    assert row["passed"] is True and row["code"] == "exact_arithmetic_match"
    assert row["semantic_truth_verified"] is False
    assert row["verifier_sha256"] == digest({k: v for k, v in row.items()
                                               if k != "verifier_sha256"})
    assert not assess("999999", contract)["passed"]


@pytest.mark.parametrize("expression", [
    "__import__('os')", "2**100", "1/0", "2**(2**16)", "1//2",
    "1.5", "0**-1", "1"*250, "(1+"*35 + "1" + ")"*35,
])
def test_adaptive_rational_refuses_unsafe_or_unbounded_arithmetic(expression):
    from skeleton.app.jeeves_constraints import rational
    with pytest.raises(ValueError):
        rational(expression)


@pytest.mark.parametrize("artifact_kind,text", [
    ("table", '{"kind":"table","title":"Plan","columns":["Stage"],"rows":[["Review"]]}'),
    ("checklist", '{"kind":"checklist","title":"Plan","items":["Inspect","Review"]}'),
    ("series", '{"kind":"series","title":"Measurements","unit":"ms","points":[{"label":"A","value":12.5}]}'),
])
def test_adaptive_inert_artifact_validates_only_schema(artifact_kind, text):
    from skeleton.app.jeeves_constraints import assess
    row = assess(text, {"kind": "artifact", "artifact_kind": artifact_kind})
    assert row["passed"] is True
    assert row["code"] == "schema_valid_not_fact_checked"
    assert row["semantic_truth_verified"] is False
    assert row["artifact"]["kind"] == artifact_kind


@pytest.mark.parametrize("artifact_kind,text", [
    ("table", '{"kind":"table","title":"a","title":"b","columns":["a"],"rows":[["x"]]}'),
    ("table", '{"kind":"table","title":"x","columns":["a","b"],"rows":[["x"]]}'),
    ("checklist", '{"kind":"checklist","title":"x","items":["y"],"execute":"command"}'),
    ("series", '{"kind":"series","title":"x","unit":"m","points":[{"label":"A","value":1e999}]}'),
    ("series", '{"kind":"series","title":"x","unit":"m","points":[{"label":"A","value":true}]}'),
    ("series", '{"kind":"series","title":"x","unit":"m","points":[{"label":"A","value":NaN}]}'),
    ("series", '{"kind":"series","title":"x","unit":"m","points":[{"label":"A","value":1},{"label":"A","value":2}]}'),
    ("checklist", '{"kind":"checklist","title":"x","items":[] }'),
])
def test_adaptive_artifact_fail_closed(artifact_kind, text):
    from skeleton.app.jeeves_constraints import assess
    row = assess(text, {"kind": "artifact", "artifact_kind": artifact_kind})
    assert row["passed"] is False and row["artifact"] is None
    assert row["code"] == "invalid_artifact_schema"


def _adaptive_policy(kind="review", total=12, attempts=4):
    return {"max_attempts": attempts, "maximum_reserved_tokens": total,
            "language": "nb", "contract": {"kind": kind}}


def test_adaptive_native_review_cap_is_real_and_does_not_commit(tmp_path):
    app = OfflineHTTPApplication(native_model(), tmp_path / "adaptive-real.sqlite3", token="t"*64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        route = "/v1/sessions/" + created["session_id"]
        before = app.dispatch("GET", route)[1]
        _, report = app.dispatch("POST", route + "/deliberation-review", {
            "message": "hello", "expected_revision": 0, "approved": True,
            "max_output_tokens": 4, "adaptive": _adaptive_policy(total=9),
        })
        assert report["schema"] == "skeleton.jeeves.adaptive-review.v1"
        assert report["adaptive"]["stop_reason"] == "token_budget"
        assert report["adaptive"]["attempts"] == 2
        assert report["reserved_total_output_tokens"] == 8
        assert report["actual_total_output_tokens"] <= 8
        assert report["adaptive"]["contract_passed"] is False
        assert all(c["verification"]["code"] == "review_required" for c in report["candidates"])
        assert all("Norwegian Bokmål" in c["strategy_text"] for c in report["candidates"])
        assert app.dispatch("GET", route)[1] == before
        assert app._active_session is None
    finally:
        app.close()


def test_adaptive_verifier_feedback_uses_codes_not_candidate_text(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from skeleton.app import jeeves_deliberation as module
    model, tokenizer = "a"*64, "b"*64
    prompts = []
    class ControlledSession:
        tokenizer_digest = tokenizer
        history = ()
        instructions = ""
        def __init__(self, backend):
            pass
        def preview_context(self, prompt, tokens, **kwargs):
            return {"fits_full_history": True, "retained_history_messages": 0}
        async def ask(self, prompt, **kwargs):
            prompts.append(prompt)
            response = "UNTRUSTED_MODEL_OUTPUT_999" if len(prompts) == 1 else "42"
            return SimpleNamespace(model_digest=model, execution_receipt_digest="c"*64,
                                   output_tokens=2, input_tokens=4, text=response)
    monkeypatch.setattr(module, "OfflineAISession", ControlledSession)
    policy = _adaptive_policy("arithmetic", total=16)
    policy["contract"]["expression"] = "6*7"
    report = asyncio.run(module.deliberate(
        SimpleNamespace(model_digest=model), "Compute the result", history=(),
        instructions="", revision=0, model_digest=model, tokenizer_digest=tokenizer,
        output_tokens=4, require_full_history=True, adaptive=policy, recheck=lambda: None,
    ))
    assert len(prompts) == 2
    assert "invalid_numeric_format" in prompts[1]
    assert "UNTRUSTED_MODEL_OUTPUT_999" not in prompts[1]
    assert report["adaptive"]["stop_reason"] == "explicit_contract_passed"
    assert report["adaptive"]["contract_passed"] is True
    assert report["reserved_total_output_tokens"] == 8
    assert report["comparison"]["answer_selected"] is False
    assert not report["comparison"]["semantic_truth_verified"]


@pytest.mark.parametrize("policy", [
    {"max_attempts": 5, "maximum_reserved_tokens": 16, "language": "en", "contract": {"kind":"review"}},
    {"max_attempts": True, "maximum_reserved_tokens": 16, "language": "en", "contract": {"kind":"review"}},
    {"max_attempts": 2, "maximum_reserved_tokens": 3, "language": "en", "contract": {"kind":"review"}},
    {"max_attempts": 2, "maximum_reserved_tokens": 16, "language": "custom", "contract": {"kind":"review"}},
    {"max_attempts": 2, "maximum_reserved_tokens": 16, "language": "en", "contract": {"kind":"arithmetic","expression":"1/0"}},
    {"max_attempts": 2, "maximum_reserved_tokens": 16, "language": "en", "contract": {"kind":"artifact","artifact_kind":"html"}},
])
def test_adaptive_policy_rejects_invalid_inputs_before_dispatch(policy):
    from skeleton.app.jeeves_constraints import normalize_policy
    with pytest.raises(ValueError):
        normalize_policy(policy, 4)


@pytest.mark.parametrize("question,role", [
    ("Sammenlign kilder og verifiser bevis", "research"),
    ("Planlegg arkitektur og avhengigheter", "planning"),
    ("Beregn resultatet", "analysis"),
    ("Implementieren und debuggen", "code"),
    ("比较来源并验证证据", "research"),
    ("ゲームのクエストを設計", "game"),
    ("بحث مقارنة مصادر", "research"),
])
def test_multilingual_cognitive_role_cues(question, role):
    from skeleton.app.jeeves_cognitive import _roles
    assert role in _roles(question)


def test_adaptive_browser_controls_render_inert_artifacts():
    from skeleton.app.offline_web import HTML, JAVASCRIPT
    for item in ("adaptive-mode", "adaptive-attempts", "adaptive-total",
                 "adaptive-language", "adaptive-expression", "adaptive-artifacts"):
        assert f'id="{item}"' in HTML
    assert "skeleton.jeeves.adaptive-review.v1" in JAVASCRIPT
    assert "label.prepend(box)" in JAVASCRIPT
    assert "el.textContent = value" in JAVASCRIPT
    assert "get('adaptive-artifacts').replaceChildren()" in JAVASCRIPT
    assert "policyMatches()" in JAVASCRIPT



def _campaign_step(node, parents=(), question="hello", tokens=4):
    return {"id": node, "depends_on": list(parents), "message": question,
            "max_output_tokens": tokens,
            "adaptive": _adaptive_policy(total=tokens, attempts=1)}


def test_real_campaign_executes_dependency_graph_and_replays_after_reopen(tmp_path):
    path = tmp_path / "campaign-real.sqlite3"
    app = OfflineHTTPApplication(native_model(), path, token="t"*64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        route = "/v1/sessions/" + created["session_id"]
        before = app.dispatch("GET", route)[1]
        graph = {"campaign_id": "demo", "expected_session_revision": 0, "approved": True,
                 "steps": [_campaign_step("second", ("first",)), _campaign_step("first")],
                 "maximum_reserved_tokens": 8}
        code, state = app.dispatch("POST", route + "/campaign-create", graph)
        assert code == 201 and state["ready_steps"] == ["first"]
        assert app.dispatch("POST", route + "/campaign-create", graph)[0] == 200
        advance = {"campaign_id": "demo", "step_id": "second", "operation_id": "op-second",
                   "expected_revision": 0, "approved": True}
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST", route + "/campaign-advance", advance)
        assert exc.value.status == 409
        first = advance | {"step_id": "first", "operation_id": "op-first"}
        code, state = app.dispatch("POST", route + "/campaign-advance", first)
        assert code == 200 and state["revision"] == 2
        assert state["ready_steps"] == ["second"]
        report = state["statuses"]["first"]["report"]
        assert report["generation_performed"] is True
        assert report["candidates"][0]["text"].strip()
        assert state["reserved_tokens"] == 4
        assert app.dispatch("GET", route)[1] == before
    finally:
        app.close()
    app = OfflineHTTPApplication(native_model(), path, token="t"*64)
    try:
        _, reopened = app.dispatch("POST", route + "/campaign-inspect", {"campaign_id": "demo"})
        assert reopened["statuses"]["first"]["report"] == report
        _, replay = app.dispatch("POST", route + "/campaign-advance", first)
        assert replay == reopened
        _, done = app.dispatch("POST", route + "/campaign-advance", advance | {"expected_revision": 2})
        assert done["all_steps_complete"] is True
        assert done["reserved_tokens"] == 8
        assert done["revision"] == 4
        assert app.dispatch("GET", route)[1] == before
        assert done["dependency_output_injected"] is False
        _, deleted = app.dispatch("POST", route + "/campaign-delete",
                                  {"campaign_id": "demo", "expected_revision": 4, "approved": True})
        assert deleted["transcript_deleted"] is False
        assert app.dispatch("GET", route)[1] == before
    finally:
        app.close()


@pytest.mark.parametrize("steps,ceiling", [
    ([_campaign_step("a", ("b",)), _campaign_step("b", ("a",))], 8),
    ([_campaign_step("a", ("missing",))], 8),
    ([_campaign_step("a"), _campaign_step("a")], 8),
    ([_campaign_step("a"), _campaign_step("b")], 7),
    ([_campaign_step("a")|{"tool": "shell"}], 8),
])
def test_campaign_rejects_cycles_bad_dependencies_duplicate_ids_and_ceiling(steps, ceiling):
    from skeleton.app.jeeves_review_campaign import normalize_plan, CampaignRejected
    with pytest.raises(CampaignRejected):
        normalize_plan(steps, ceiling)


def test_campaign_unconfirmed_claim_is_persistent_and_abandon_never_retries(tmp_path):
    path = tmp_path / "campaign-recover.sqlite3"
    app = OfflineHTTPApplication(native_model(), path, token="t"*64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        route = "/v1/sessions/" + sid
        app.dispatch("POST", route + "/campaign-create", {
            "campaign_id": "recovery", "expected_session_revision": 0, "approved": True,
            "steps": [_campaign_step("a"), _campaign_step("b", ("a",))],
            "maximum_reserved_tokens": 8,
        })
        claim, spec = app.review_campaigns.claim(sid, "recovery", "a", "op-a", 0)
        assert spec["id"] == "a" and claim["ready_steps"] == []
        assert claim["statuses"]["a"]["status"] == "running"
    finally:
        app.close()
    app = OfflineHTTPApplication(native_model(), path, token="t"*64)
    try:
        body = {"campaign_id": "recovery", "step_id": "a", "operation_id": "op-a",
                "expected_revision": 1, "approved": True}
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST", route + "/campaign-advance", body)
        assert exc.value.status == 409
        _, state = app.dispatch("POST", route + "/campaign-abandon", body)
        assert state["statuses"]["a"]["status"] == "abandoned_unconfirmed"
        assert state["reserved_tokens"] == 4 and state["ready_steps"] == []
        _, replay = app.dispatch("POST", route + "/campaign-advance", body)
        assert replay == state
        assert app.dispatch("GET", route)[1]["revision"] == 0
    finally:
        app.close()


def test_campaign_rejects_unapproved_mutations_and_forged_result(tmp_path):
    from skeleton.app.jeeves_review_campaign import CampaignConflict
    app = OfflineHTTPApplication(native_model(), tmp_path / "campaign-fence.sqlite3", token="t"*64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        route = "/v1/sessions/" + sid
        graph = {"campaign_id": "fence", "expected_session_revision": 0,
                 "approved": False, "steps": [_campaign_step("a")],
                 "maximum_reserved_tokens": 4}
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST", route + "/campaign-create", graph)
        assert exc.value.status == 403
        app.dispatch("POST", route + "/campaign-create", graph | {"approved": True})
        app.review_campaigns.claim(sid, "fence", "a", "op", 0)
        with pytest.raises(CampaignConflict):
            app.review_campaigns.settle(sid, "fence", "a", "op", {"generation_performed": True})
        assert app.review_campaigns.inspect(sid, "fence")["statuses"]["a"]["status"] == "running"
        settled = app.review_campaigns.settle(sid, "fence", "a", "op")
        assert settled["statuses"]["a"]["status"] == "execution_unconfirmed"
        assert settled["reserved_tokens"] == 4
        assert "report" not in settled["statuses"]["a"]
    finally:
        app.close()


def test_campaign_browser_routes_are_explicit_and_local():
    from skeleton.app.offline_web import HTML, JAVASCRIPT
    for item in ("campaign-id", "campaign-plan", "campaign-create", "campaign-inspect",
                 "campaign-result", "campaign-delete"):
        assert f'id="{item}"' in HTML
    assert "dependency_output_injected !== false" in JAVASCRIPT
    assert "result.textContent = JSON.stringify(row.report, null, 2)" in JAVASCRIPT
    assert "Mark claim abandoned (does not cancel or retry)" in JAVASCRIPT
    assert "get('campaign-plan').value = '';" in JAVASCRIPT



def test_relevance_packing_preserves_old_useful_turn_and_exact_original_pairs():
    from skeleton.app.jeeves_history_pack import pack_history, digest
    history = (
        ("user", "Nebula recovery requires the violet module."),
        ("assistant", "Check the committed Nebula recovery specification."),
        ("user", "Unrelated discussion " * 100),
        ("assistant", "Unrelated text " * 100),
        ("user", "What is the weather?"),
        ("assistant", "Weather is unrelated."),
        ("user", "Latest deployment status"),
        ("assistant", "Deployment ready for review."),
    )
    selected, proof = pack_history(
        "Nebula recovery", history, recent_turns=1,
        fits=lambda pairs: sum(len(row[1]) for row in pairs) <= 210,
    )
    assert selected == history[:2] + history[-2:]
    assert [turn["turn_index"] for turn in proof["selected_turns"]] == [0, 3]
    assert proof["omitted_turns"] == 2
    assert proof["selected_history_sha256"] == digest(selected)
    assert proof["receipt_sha256"] == digest({k: v for k, v in proof.items()
                                               if k != "receipt_sha256"})
    assert proof["history_modified"] is False
    assert proof["summarized"] is False


def test_relevance_history_bounded_scan_and_admission():
    from skeleton.app.jeeves_history_pack import pack_history, MAX_ADMISSION_CHECKS
    history = tuple(row for i in range(180)
                    for row in (("user", "nebula case " + str(i)),
                                ("assistant", "nebula reviewed " + str(i))))
    decisions = []
    def fits(rows):
        decisions.append(rows)
        return len(rows) <= 4
    selected, proof = pack_history("nebula", history, fits=fits)
    assert len(selected) == 4
    assert proof["scan_start_turn"] == 84
    assert proof["scan_truncated"] is True
    assert proof["admission_checks"] == len(decisions) <= MAX_ADMISSION_CHECKS
    assert all(row["turn_index"] >= 84 for row in proof["selected_turns"])
    with pytest.raises(ValueError):
        pack_history("nebula", (("assistant", "bad"), ("user", "roles")), fits=fits)
    with pytest.raises(ValueError):
        pack_history("nebula", history, fits=lambda _: False)


def test_relevance_history_native_review_retains_source_proof_without_commit(tmp_path):
    app = OfflineHTTPApplication(native_model(), tmp_path / "packed-review.sqlite3", token="t"*64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        route = "/v1/sessions/" + created["session_id"]
        for i, question in enumerate(("hello offline", "world", "hello")):
            app.dispatch("POST", route + "/turn", {"message": question,
                         "request_id": "pack-turn-" + str(i), "max_output_tokens": 2})
        before = app.dispatch("GET", route)[1]
        body = {"message": "hello offline", "expected_revision": 3, "approved": True,
                "max_output_tokens": 2, "history_policy": "relevance",
                "require_full_history": False, "adaptive": _adaptive_policy(total=2, attempts=1)}
        _, report = app.dispatch("POST", route + "/deliberation-review", body)
        assert report["history_policy"] == "relevance"
        assert report["require_full_history"] is False
        candidate = report["candidates"][0]
        proof = candidate["history_packing"]
        assert proof["total_turns"] == 3
        assert len(proof["selected_turns"]) + proof["omitted_turns"] == 3
        assert candidate["estimated_history_retained"] == len(proof["selected_turns"]) * 2
        assert report["candidate_challenge"]["winner_selected"] is False
        assert app.dispatch("GET", route)[1] == before
        with pytest.raises(OfflineHTTPError) as error:
            app.dispatch("POST", route + "/deliberation-review", body | {"require_full_history": True})
        assert error.value.status == 400
    finally:
        app.close()


def _quote_manifest():
    passages = ["The Nebula module restores the vault.", "Recovery requires the violet key."]
    rows = []
    for i, text in enumerate(passages):
        doc = "document-" + str(i)
        pin = sha256(text.encode()).hexdigest()
        rows.append({"document_id": doc, "document_sha256": pin,
                     "citation": "local:" + doc + ":0:" + pin[:16],
                     "passage": text, "passage_sha256": pin, "char_start": 0,
                     "char_end": len(text)})
    return {"citations": rows}


def test_exact_source_quote_contract_checks_content_diversity_and_offsets():
    import json
    from skeleton.app.jeeves_constraints import assess
    manifest = _quote_manifest()
    contract = {"kind": "source_quotes", "minimum_quotes": 2, "minimum_distinct_sources": 2}
    quotes = [{"citation": row["citation"], "quote": row["passage"]}
              for row in manifest["citations"]]
    answer = json.dumps({"quotes": quotes})
    result = assess(answer, contract, evidence=manifest)
    proof = result["quote_verification"]
    assert result["passed"] is True and proof["distinct_document_count"] == 2
    assert proof["literal_identity_verified"] is True
    assert proof["source_truth_verified"] is False
    assert proof["answer_completeness_verified"] is False
    for span, row in zip(proof["quotes"], manifest["citations"]):
        assert row["passage"][span["start"]:span["end"]] == span["quote"]
        assert span["quote_sha256"] == sha256(span["quote"].encode()).hexdigest()
    for invalid in [
        {"quotes": [quotes[0], quotes[0]]},
        {"quotes": [quotes[0], quotes[1] | {"quote": "Recovery uses the orange key."}]},
        {"quotes": [quotes[0], quotes[1] | {"citation": "local:invented"}]},
        {"quotes": quotes, "answer": "false extrapolation"},
    ]:
        assert assess(json.dumps(invalid), contract, evidence=manifest)["passed"] is False
    assert assess(answer, contract)["passed"] is False


def test_exact_quotes_reject_overlaps_ambiguous_matches_and_corrupted_passage():
    import json
    from skeleton.app.jeeves_constraints import assess
    manifest = _quote_manifest()
    row = manifest["citations"][0]
    contract = {"kind": "source_quotes", "minimum_quotes": 2, "minimum_distinct_sources": 1}
    answer = json.dumps({"quotes": [
        {"citation": row["citation"], "quote": "The Nebula module"},
        {"citation": row["citation"], "quote": "Nebula module restores"},
    ]})
    assert not assess(answer, contract, evidence=manifest)["passed"]
    repeated = "The Nebula module. The Nebula module."
    row.update(passage=repeated, passage_sha256=sha256(repeated.encode()).hexdigest(),
               char_end=len(repeated))
    single = contract | {"minimum_quotes": 1}
    text = json.dumps({"quotes": [{"citation": row["citation"], "quote": "The Nebula module"}]})
    assert not assess(text, single, evidence=manifest)["passed"]
    row["passage"] = "Changed passage identity."
    assert not assess(text, single, evidence=manifest)["passed"]


def test_grounded_quote_review_requires_scope_and_distinct_sources_before_generation(tmp_path):
    app = OfflineHTTPApplication(native_model(), tmp_path / "quote-admission.sqlite3", token="t"*64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        route = "/v1/sessions/" + created["session_id"]
        policy = _adaptive_policy(total=4, attempts=1)
        policy["contract"] = {"kind": "source_quotes", "minimum_quotes": 2,
                              "minimum_distinct_sources": 2}
        body = {"message": "Nebula recovery", "expected_revision": 0, "approved": True,
                "max_output_tokens": 4, "adaptive": policy}
        with pytest.raises(OfflineHTTPError) as error:
            app.dispatch("POST", route + "/deliberation-review", body)
        assert error.value.status == 400
        first = app.knowledge.add_text("One source", "Nebula recovery uses the violet module.")
        with pytest.raises(OfflineHTTPError) as error:
            app.dispatch("POST", route + "/deliberation-review",
                         body | {"grounded": True, "document_ids": [first["document_id"]]})
        assert error.value.status == 422
        assert app._active_session is None
        assert app.dispatch("GET", route)[1]["revision"] == 0
    finally:
        app.close()


def test_candidate_challenge_reports_literal_numeric_disagreement_not_truth():
    from skeleton.app.jeeves_candidate_challenge import examine, digest
    texts = ["The module timeout is 20 ms. The local state is ready.",
             "The module timeout is 45 ms. The local state is ready."]
    candidates = [{"text": text, "output_sha256": sha256(text.encode()).hexdigest(),
                   "faithfulness": None, "citation_audit": None} for text in texts]
    report = examine(candidates)
    assert report["distinct_exact_outputs"] == 2
    assert report["semantic_contradiction_verified"] is False
    assert report["winner_selected"] is False
    assert len(report["numeric_disagreements"]) == 1
    diff = report["numeric_disagreements"][0]
    assert diff["left"]["numeric_literals"] == ["20"]
    assert diff["right"]["numeric_literals"] == ["45"]
    for side in (diff["left"], diff["right"]):
        original = texts[side["candidate_index"]][side["start"]:side["end"]]
        assert side["segment_sha256"] == sha256(original.encode()).hexdigest()
    assert report["receipt_sha256"] == digest({k: v for k, v in report.items()
                                                if k != "receipt_sha256"})
    with pytest.raises(ValueError):
        examine([candidates[0] | {"text": "changed"}])


def test_grounded_campaign_pins_source_and_rejects_withdrawal_before_reservation(tmp_path):
    app = OfflineHTTPApplication(native_model(), tmp_path / "grounded-dag.sqlite3", token="t"*64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        route = "/v1/sessions/" + created["session_id"]
        doc = app.knowledge.add_text("Recovery source", "Nebula recovery uses the violet module.")
        pin = {"document_id": doc["document_id"], "sha256": doc["sha256"]}
        spec = _campaign_step("review", question="Nebula recovery") | {"sources": [pin]}
        create = {"campaign_id": "grounded-dag", "expected_session_revision": 0,
                  "approved": True, "steps": [spec], "maximum_reserved_tokens": 4}
        with pytest.raises(OfflineHTTPError) as error:
            app.dispatch("POST", route + "/campaign-create",
                         create | {"steps": [spec | {"sources": [pin | {"sha256": "0"*64}]}]})
        assert error.value.status == 409
        _, graph = app.dispatch("POST", route + "/campaign-create", create)
        assert graph["plan"]["steps"][0]["sources"] == [pin]
        app.knowledge.delete(doc["document_id"])
        body = {"campaign_id": "grounded-dag", "step_id": "review", "operation_id": "source-op",
                "expected_revision": 0, "approved": True}
        with pytest.raises(OfflineHTTPError) as error:
            app.dispatch("POST", route + "/campaign-advance", body)
        assert error.value.status == 409
        _, current = app.dispatch("POST", route + "/campaign-inspect", {"campaign_id": "grounded-dag"})
        assert current["reserved_tokens"] == 0
        assert current["statuses"]["review"]["status"] == "pending"
    finally:
        app.close()


def test_grounded_campaign_executes_real_native_and_retains_exact_scope_receipt(tmp_path):
    app = OfflineHTTPApplication(native_model(), tmp_path / "grounded-dag-real.sqlite3", token="t"*64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        route = "/v1/sessions/" + created["session_id"]
        doc = app.knowledge.add_text("Recovery source", "Nebula recovery uses the violet module.")
        other = app.knowledge.add_text("Excluded", "Nebula recovery alternative unrelated text.")
        pin = {"document_id": doc["document_id"], "sha256": doc["sha256"]}
        spec = _campaign_step("review", question="Nebula recovery") | {
            "sources": [pin], "history_policy": "relevance"}
        app.dispatch("POST", route + "/campaign-create", {
            "campaign_id": "real-scope", "expected_session_revision": 0,
            "approved": True, "steps": [spec], "maximum_reserved_tokens": 4})
        _, current = app.dispatch("POST", route + "/campaign-advance", {
            "campaign_id": "real-scope", "step_id": "review", "operation_id": "read-scoped",
            "expected_revision": 0, "approved": True})
        report = current["statuses"]["review"]["report"]
        assert current["all_steps_complete"]
        assert report["generation_performed"] is True and report["history_policy"] == "relevance"
        assert report["evidence_sources"]
        assert {row["document_id"] for row in report["evidence_sources"]} == {doc["document_id"]}
        assert all(row["document_sha256"] == doc["sha256"] for row in report["evidence_sources"])
        assert app.dispatch("GET", route)[1]["revision"] == 0
        assert other["document_id"] != doc["document_id"]
    finally:
        app.close()


def test_wave_iv_browser_receipts_and_controls():
    from skeleton.app.offline_web import HTML, JAVASCRIPT
    for item in ("review-history-policy", "quote-minimum", "quote-sources"):
        assert f'id="{item}"' in HTML
    assert "history_policy: historyPolicy" in JAVASCRIPT
    assert "Quotation does not match supplied passage." in JAVASCRIPT
    assert "Selected history pair identity changed." in JAVASCRIPT
    assert "Candidate disagreement span mismatch." in JAVASCRIPT
    assert "not semantic contradictions" in JAVASCRIPT
