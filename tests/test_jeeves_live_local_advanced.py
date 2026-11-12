"""Jeeves advanced acceptance: real local generation, HTTP, durable restart.

The native tiny transformer here is an actual executing model, intentionally
NOT a production GGUF or a model-quality certification. Production deployment
must run the same HTTP/SQLite acceptance with operator-owned pinned GGUF.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.transformer import TinyTransformer
from scripts.qualify_jeeves_live_local import (
    LiveJeevesFailure, _qualify_actual_local_http, qualify_jeeves_live_local,
)


def native_model():
    return NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer",
               "local", "offline", "jeeves", "computer", ".", " "),
        dim=8, ctx=1024, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )))


def test_real_offline_model_generates_across_loopback_http_then_recovers_sqlite():
    model = native_model()
    report = _qualify_actual_local_http(
        model, timeout_seconds=45, output_tokens=2,
    )
    assert report["qualified"] is True
    assert report["local_only"] is True
    assert report["hosted_provider_used"] is False
    assert report["model_id"] == model.model_id
    assert report["model_digest"] == model.model_digest
    assert report["actual_model_turns"] == 2
    assert report["durable_recovery_verified"] is True
    assert report["read_only_replay_verified"] is True
    assert report["context_continuation_verified"] is True
    assert report["unauthenticated_local_query_denied"] is True
    assert report["committed_request_rewrite_denied"] is True
    assert report["protected_backend_verified"] is False
    assert report["mobile_device_verified"] is False
    assert report["underlying_model_quality_certified"] is False
    assert len(report["run_1_output_sha256"]) == 64
    assert len(report["run_2_output_sha256"]) == 64
    assert len(report["turn_metrics"]) == 2
    assert all(r["actual_output_tokens"] == 2 for r in report["turn_metrics"])


def test_production_live_qualification_refuses_a_different_native_model():
    with pytest.raises(LiveJeevesFailure, match="real loaded local model identity"):
        qualify_jeeves_live_local(native_model())


@pytest.mark.parametrize("timeout,tokens", [
    (0, 2), (601, 2), (True, 2), (45, 0), (45, 65), (45, True),
])
def test_resource_budgets_fail_before_live_generation(timeout, tokens):
    with pytest.raises(LiveJeevesFailure, match="time/token budgets"):
        _qualify_actual_local_http(
            native_model(), timeout_seconds=timeout, output_tokens=tokens,
        )



def test_live_loopback_status_refuses_mutated_native_weights_without_exposing_data(tmp_path, monkeypatch):
    """A process that booted successfully is not perpetually ready.

    Source digest/device changes make new work unavailable, while old
    SQLite history can still be read without executing another model.
    """
    from skeleton.app.offline_http import OfflineHTTPApplication, OfflineHTTPError
    model = native_model()
    app = OfflineHTTPApplication(model, tmp_path / "jeeves.sqlite3", token="t" * 64)
    try:
        status, observed = app.dispatch("GET", "/v1/status")
        assert status == 200 and observed["ready"] is True
        assert observed["model_readiness_code"] == "ready"
        assert observed["readiness_is_live_inference_proof"] is False
        _, session = app.dispatch("POST", "/v1/sessions", {})
        monkeypatch.setattr(model, "check_readiness",
                            lambda: (_ for _ in ()).throw(
                                RuntimeError("private-device-path-and-credentials")))
        status, observed = app.dispatch("GET", "/v1/status")
        assert status == 200 and observed["ready"] is False
        assert observed["model_readiness_code"] == "local_model_identity_unavailable"
        assert "private-device-path" not in repr(observed)
        with pytest.raises(OfflineHTTPError, match="local inference unavailable") as blocked:
            app.submit_turn(session["session_id"], {
                "message": "Prevent a model-drift launch",
                "request_id": "stale-model-1",
                "max_output_tokens": 2,
            })
        assert blocked.value.status == 503
        assert "private-device-path" not in str(blocked.value)
        _, transcript = app.dispatch("GET", "/v1/sessions/" + session["session_id"])
        assert transcript["revision"] == 0 and transcript["messages"] == []
    finally:
        app.close()


def test_readonly_history_survives_native_model_unavailability_after_real_generation(
    tmp_path, monkeypatch
):
    """No re-generation of committed text during a model outage."""
    from skeleton.app.offline_http import OfflineHTTPApplication, OfflineHTTPError
    model = native_model()
    app = OfflineHTTPApplication(model, tmp_path / "persistent.sqlite3", token="t" * 64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        payload = {
            "message": "A real offline answer",
            "request_id": "persist-then-unavailable",
            "max_output_tokens": 2,
        }
        status, committed = app.dispatch(
            "POST", "/v1/sessions/" + sid + "/turn", payload,
        )
        assert status == 200 and committed["revision"] == 1
        monkeypatch.setattr(
            model, "check_readiness",
            lambda: (_ for _ in ()).throw(RuntimeError("private-weight-error")),
        )
        _, observed = app.dispatch("GET", "/v1/status")
        assert observed["ready"] is False
        _, replayed = app.dispatch(
            "GET", "/v1/sessions/" + sid + "/turns/" + payload["request_id"],
        )
        assert replayed["state"] == "complete"
        assert replayed["result"]["output_digest"] == committed["output_digest"]
        _, historical = app.dispatch("GET", "/v1/sessions/" + sid)
        assert historical["revision"] == 1
        assert historical["messages"][-1]["content"] == committed["text"]
        with pytest.raises(OfflineHTTPError) as blocked:
            app.dispatch("POST", "/v1/sessions/" + sid + "/turn", {
                "message": "new input cannot run untrusted backend",
                "request_id": "next-must-block",
                "max_output_tokens": 2,
            })
        assert blocked.value.status == 503
        # Historical exactly-once retries must not need the lost model.
        status, duplicate = app.dispatch(
            "POST", "/v1/sessions/" + sid + "/turn", payload,
        )
        assert status == 200 and duplicate["replayed"] is True
        assert duplicate["output_digest"] == committed["output_digest"]
    finally:
        app.close()


def test_closing_and_wrong_jeeves_identity_never_admit_new_generation(tmp_path, monkeypatch):
    from skeleton.app.offline_http import OfflineHTTPApplication, OfflineHTTPError
    model = native_model()
    app = OfflineHTTPApplication(model, tmp_path / "closing.sqlite3", token="t" * 64)
    try:
        status, created = app.dispatch("POST", "/v1/sessions", {})
        assert status == 201
        monkeypatch.setenv("JEEVES_LOCAL_ONLY", "1")
        monkeypatch.setenv("JEEVES_PRIMARY_MODEL_ID", "jeeves")
        _, status = app.dispatch("GET", "/v1/status")
        assert status["ready"] is False
        assert status["model_readiness_code"] == "local_primary_identity_changed"
        with pytest.raises(OfflineHTTPError, match="local_primary_identity_changed"):
            app.submit_turn(created["session_id"], {
                "message": "reject non-Jeeves primary at dispatch",
                "request_id": "deny-other-model", "max_output_tokens": 2,
            })
    finally:
        app.close()
    _, state = app.dispatch("GET", "/v1/status")
    assert state["ready"] is False
    assert state["model_readiness_code"] == "local_service_shutting_down"



def test_continuation_preflight_refuses_a_reopened_session_that_discards_history(monkeypatch):
    """A second answer is not context continuity if the model forgets turn one."""
    from skeleton.app.local_ai import DurableOfflineAISession
    original = DurableOfflineAISession._request
    def forget_first_turn(self, prompt, max_output_tokens):
        prepared, kept = original(self, prompt, max_output_tokens)
        if prompt.startswith("Continue the local Jeeves conversation"):
            return prepared, ()
        return prepared, kept
    monkeypatch.setattr(DurableOfflineAISession, "_request", forget_first_turn)
    with pytest.raises(LiveJeevesFailure, match="discard the prior conversation context"):
        _qualify_actual_local_http(native_model(), timeout_seconds=45, output_tokens=2)


def test_advanced_qualification_reports_context_preflight_not_cryptographic_generation_proof():
    result = _qualify_actual_local_http(native_model(), timeout_seconds=45, output_tokens=2)
    assert result["context_preflight_history_retained"] is True
    assert result["context_preflight_is_generation_proof"] is False
    assert result["actual_model_turns"] == 2



def test_local_runtime_execution_receipt_survives_full_sqlite_reopen_and_detects_missing_sidecar(
    tmp_path,
):
    """A real native generation must atomically commit both text and runtime proof."""
    from skeleton.app.offline_http import OfflineHTTPApplication
    from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError

    model = native_model()
    database = tmp_path / "receipt.sqlite3"
    token = "t" * 64
    rid = "native-receipt-atomicity"
    app = OfflineHTTPApplication(model, database, token=token)
    try:
        status, created = app.dispatch("POST", "/v1/sessions", {})
        assert status == 201
        sid = created["session_id"]
        status, completed = app.dispatch(
            "POST", "/v1/sessions/" + sid + "/turn",
            {"message": "Generate a local response with native receipt",
             "request_id": rid, "max_output_tokens": 2},
        )
        assert status == 200 and completed["revision"] == 1
        local = completed["local_execution_receipt"]
        assert local["schema"] == "skeleton.ai.local-runtime-receipt.v1"
        assert local["model_digest"] == model.model_digest
        assert local["output_sha256"] == completed["output_digest"]
        assert local["authority"] == "local-runtime-custody-not-independent-attestation"
        assert len(local["execution_receipt_digest"]) == 64
    finally:
        app.close()

    reopened = OfflineHTTPApplication(model, database, token=token)
    try:
        status, historic = reopened.dispatch(
            "GET", "/v1/sessions/" + sid + "/turns/" + rid,
        )
        assert status == 200
        assert historic["recovered_from_store"] is True
        assert historic["result"]["local_execution_receipt"] == local
        assert historic["result"]["text"] == completed["text"]
        # A committed new native turn's marker is required: deleting its
        # execution receipt must produce a hard integrity failure, not
        # silently downgrade the turn into an allegedly old unverified one.
        with reopened._store._transaction():
            deleted = reopened._store._db.execute(
                "DELETE FROM offline_turn_execution_receipts WHERE session_id=? AND request_id=?",
                (sid, rid),
            )
            assert deleted.rowcount == 1
        with pytest.raises(RuntimeContractError, match="required local execution receipt is missing"):
            reopened.dispatch("GET", "/v1/sessions/" + sid + "/turns/" + rid)
    finally:
        reopened.close()


def test_local_receipt_identity_tamper_is_detected_during_read_only_replay(tmp_path):
    from skeleton.app.offline_http import OfflineHTTPApplication
    from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
    model = native_model()
    app = OfflineHTTPApplication(model, tmp_path / "tamper.sqlite3", token="t" * 64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        rid = "receipt-bind-model-and-output"
        _, committed = app.dispatch(
            "POST", "/v1/sessions/" + sid + "/turn",
            {"message": "Local native model binding test",
             "request_id": rid, "max_output_tokens": 2},
        )
        assert committed["local_execution_receipt"]
        with app._store._transaction():
            app._store._db.execute(
                "UPDATE offline_turn_execution_receipts SET model_digest=? "
                "WHERE session_id=? AND request_id=?",
                ("f" * 64, sid, rid),
            )
        with pytest.raises(RuntimeContractError, match="not bound to committed model output"):
            app.dispatch("GET", "/v1/sessions/" + sid + "/turns/" + rid)
    finally:
        app.close()


def test_advanced_genuine_execution_exposes_distinct_receipts_for_two_actual_turns():
    report = _qualify_actual_local_http(native_model(), timeout_seconds=45, output_tokens=2)
    assert report["runtime_receipts_survived_restart"] is True
    assert len(report["run_1_execution_receipt_sha256"]) == 64
    assert len(report["run_2_execution_receipt_sha256"]) == 64
    assert report["run_1_execution_receipt_sha256"] != report["run_2_execution_receipt_sha256"]


def test_async_committed_retry_recovers_after_restart_without_model(monkeypatch, tmp_path):
    """Idempotent async POST must read durable truth before model admission."""
    from skeleton.app.offline_http import OfflineHTTPApplication
    from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError

    model = native_model()
    database = tmp_path / "async-restart.sqlite3"
    payload = {
        "message": "Keep this native answer after offline restart",
        "request_id": "durable-async-replay-1",
        "max_output_tokens": 2,
    }
    initial = OfflineHTTPApplication(model, database, token="t" * 64)
    try:
        _, created = initial.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        status, completed = initial.dispatch("POST", f"/v1/sessions/{sid}/turn", payload)
        assert status == 200 and completed["revision"] == 1
    finally:
        initial.close()

    restarted = OfflineHTTPApplication(model, database, token="t" * 64)
    try:
        monkeypatch.setattr(
            model, "check_readiness",
            lambda: (_ for _ in ()).throw(RuntimeError("/private/gguf/model.gguf API-SECRET")),
        )
        status, readiness = restarted.dispatch("GET", "/v1/status")
        assert status == 200 and readiness["ready"] is False
        status, replay = restarted.dispatch(
            "POST", f"/v1/sessions/{sid}/turns", payload,
        )
        assert status == 200 and replay["state"] == "complete"
        assert replay["recovered_from_store"] is True
        assert replay["result"]["replayed"] is True
        assert replay["result"]["output_digest"] == completed["output_digest"]
        assert replay["result"]["local_execution_receipt"] == completed["local_execution_receipt"]
        with pytest.raises(RuntimeContractError, match="request id reused"):
            restarted.submit_turn(sid, {**payload, "message": "Changed request must conflict"})
        with pytest.raises(Exception, match="local inference unavailable"):
            restarted.submit_turn(sid, {**payload, "request_id": "new-work-model-unavailable"})
    finally:
        restarted.close()


def test_async_model_failure_does_not_expose_private_exception(monkeypatch, tmp_path):
    """Polling failed work must not surface a model executable path or token."""
    import time
    from skeleton.app.offline_http import OfflineHTTPApplication
    from skeleton.app.local_ai import OfflineAIError

    model = native_model()
    app = OfflineHTTPApplication(model, tmp_path / "ticket-privacy.sqlite3", token="t" * 64)
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        secret = "/private/weights/API-SECRET.gguf"
        def fail_inference(*args, **kwargs):
            raise OfflineAIError(secret)
        monkeypatch.setattr(app, "_perform_turn", fail_inference)
        status, accepted = app.submit_turn(sid, {
            "request_id": "redact-failed-ticket",
            "message": "No private error text",
            "max_output_tokens": 2,
        })
        assert status == 202
        deadline = time.monotonic() + 4
        while True:
            observed = app.turn_status(sid, "redact-failed-ticket")
            if observed["terminal"] or time.monotonic() >= deadline:
                break
            time.sleep(0.01)
        assert observed["terminal"] and observed["state"] == "failed"
        assert "API-SECRET" not in str(observed)
        assert "/private/weights/" not in str(observed)
        assert observed["error"] == "local model or durable conversation operation failed"
    finally:
        app.close()


@pytest.mark.parametrize("error,status,public_message", [
    ("contract", 400, "invalid local conversation request"),
    ("missing", 404, "unknown offline conversation"),
    ("conflict", 409, "local conversation conflict"),
    ("value", 400, "local model request rejected"),
    ("offline", 400, "local model request rejected"),
])
def test_authenticated_http_exception_boundary_does_not_echo_private_details(
    error, status, public_message, monkeypatch, tmp_path
):
    """Failure classification survives while backend-specific payloads do not."""
    from http.client import HTTPConnection
    import json
    from scripts.qualify_jeeves_live_local import _LiveServer
    from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
    from skeleton.app.local_ai import OfflineAIError

    private = "/private/jeeves/weights.gguf?credential=API-SECRET"
    cases = {
        "contract": RuntimeContractError("model bootstrap failed " + private),
        "missing": RuntimeContractError("unknown offline conversation " + private),
        "conflict": RuntimeContractError("offline conversation revision conflict " + private),
        "value": ValueError("tokenizer failed: " + private),
        "offline": OfflineAIError("model invocation failed: " + private),
    }
    token = "t" * 64
    with _LiveServer(native_model(), tmp_path / "http-redaction.sqlite3", token) as server:
        def raise_internal(*args, **kwargs):
            raise cases[error]
        monkeypatch.setattr(server.app, "dispatch", raise_internal)
        connection = HTTPConnection("127.0.0.1", server.port, timeout=5)
        try:
            connection.request(
                "GET", "/v1/status", headers={"Authorization": "Bearer " + token},
            )
            response = connection.getresponse()
            actual_status = response.status
            raw = response.read()
        finally:
            connection.close()
    assert actual_status == status
    assert private.encode() not in raw
    assert b"API-SECRET" not in raw
    assert json.loads(raw) == {"error": public_message}


@pytest.mark.parametrize("failure_kind,expected_public_error", [
    ("http", "local model or durable storage unavailable"),
    ("system-exit", "local generation failed; inspect the model and retry"),
    ("keyboard-interrupt", "local generation failed; inspect the model and retry"),
])
def test_async_unexpected_worker_exit_never_leaks_or_strands_local_chat(
    failure_kind, expected_public_error, monkeypatch, tmp_path,
):
    """A worker crash must not leak paths, strand a ticket or block later inference."""
    import time
    from skeleton.app.offline_http import OfflineHTTPApplication, OfflineHTTPError

    model = native_model()
    app = OfflineHTTPApplication(
        model, tmp_path / ("worker-" + failure_kind + ".sqlite3"), token="t" * 64,
    )
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        original = app._perform_turn
        secret = "/private/local/weights.gguf?secret=CANARY-PRIVATE"
        errors = {
            "http": OfflineHTTPError(503, secret),
            "system-exit": SystemExit(secret),
            "keyboard-interrupt": KeyboardInterrupt(secret),
        }
        def explode(*_args, **_kwargs):
            raise errors[failure_kind]
        monkeypatch.setattr(app, "_perform_turn", explode)
        status, ticket = app.submit_turn(sid, {
            "message": "This worker should fail closed",
            "request_id": "abnormal-native-worker-1",
            "max_output_tokens": 2,
        })
        assert status == 202 and ticket["request_id"] == "abnormal-native-worker-1"
        deadline = time.monotonic() + 8
        while True:
            observed = app.turn_status(sid, "abnormal-native-worker-1")
            if observed["terminal"] and observed["finished_at"] is not None:
                break
            assert time.monotonic() < deadline, "failed worker stranded its turn ticket"
            time.sleep(0.01)
        assert observed["state"] == "failed"
        assert observed["error"] == expected_public_error
        assert "CANARY-PRIVATE" not in str(observed)
        assert "/private/local/" not in str(observed)

        # One failed thread must free the single-device worker slot, and a
        # subsequent genuine native execution must commit to SQLite normally.
        monkeypatch.setattr(app, "_perform_turn", original)
        status, next_ticket = app.submit_turn(sid, {
            "message": "Real local recovery after a failed worker",
            "request_id": "native-worker-recovered-2",
            "max_output_tokens": 2,
        })
        assert status == 202 and next_ticket["request_id"] == "native-worker-recovered-2"
        deadline = time.monotonic() + 30
        while True:
            recovered = app.turn_status(sid, "native-worker-recovered-2")
            if recovered["terminal"] and recovered["finished_at"] is not None:
                break
            assert time.monotonic() < deadline, "recovered worker did not finish"
            time.sleep(0.02)
        assert recovered["state"] == "complete", recovered["error"]
        assert recovered["result"]["replayed"] is False
        assert recovered["result"]["local_execution_receipt"]["model_digest"] == model.model_digest
        assert app._session(sid).revision == 1
    finally:
        app.close()


def test_browser_live_self_test_proves_actual_native_and_committed_history(tmp_path):
    """The web acceptance feature is backed by real, nonmocked local inference."""
    import time
    from hashlib import sha256
    from skeleton.app.offline_http import OfflineHTTPApplication

    model = native_model()
    app = OfflineHTTPApplication(model, tmp_path / "browser-live.sqlite3", token="t" * 64)
    try:
        status, observed = app.dispatch("GET", "/v1/status")
        assert status == 200
        assert observed["ready"] is True and observed["local_only"] is True
        assert observed["readiness_is_live_inference_proof"] is False
        assert observed["model_digest"] == model.model_digest
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        rid = "actual-browser-native-selftest-2026"
        status, accepted = app.submit_turn(sid, {
            "request_id": rid,
            "message": "Local inference acceptance: respond with one brief sentence about offline computing.",
            "max_output_tokens": 2,
            "grounded": False,
        })
        assert status == 202
        assert accepted["request_id"] == rid
        deadline = time.monotonic() + 30
        while True:
            observed_turn = app.turn_status(sid, rid)
            if observed_turn["terminal"] and observed_turn["finished_at"] is not None:
                break
            assert time.monotonic() < deadline, "local native worker did not settle"
            time.sleep(0.02)
        assert observed_turn["state"] == "complete"
        response = observed_turn["result"]
        assert response["replayed"] is False
        assert response["text"] and response["output_tokens"] >= 1
        assert response["model_digest"] == model.model_digest
        assert response["output_digest"] == sha256(response["text"].encode("utf-8")).hexdigest()
        receipt = response["local_execution_receipt"]
        assert receipt["model_digest"] == model.model_digest
        assert receipt["output_sha256"] == response["output_digest"]
        assert receipt["revision"] == 1
        assert len(receipt["execution_receipt_digest"]) == 64
        _, readback = app.dispatch("GET", "/v1/sessions/" + sid)
        assert readback["revision"] == 1
        assistant = [r["content"] for r in readback["messages"] if r["role"] == "assistant"]
        assert assistant == [response["text"]]
        # This is the exact immutable verification performed by the browser.
        # It never asks a remote provider to manufacture an acceptance reply.
    finally:
        app.close()


def test_browser_self_test_is_user_triggered_private_and_never_fake_ready():
    from skeleton.app.offline_web import HTML, JAVASCRIPT
    assert 'id="selftest-start"' in HTML
    assert 'id="selftest-export"' in HTML
    assert 'id="selftest-result"' in HTML
    assert "addEventListener('click', () => run(startSelfTest))" in JAVASCRIPT
    assert "const observed = await api('GET', '/v1/status')" in JAVASCRIPT
    assert "const created = await api('POST', '/v1/sessions', {})" in JAVASCRIPT
    assert "state.turn = await api('POST', '/v1/sessions/' + session_id + '/turns', body)" in JAVASCRIPT
    assert "const saved = await api('GET', '/v1/sessions/' + claim.session_id)" in JAVASCRIPT
    assert "crypto.subtle.digest('SHA-256', binary)" in JAVASCRIPT
    assert "provider_fallback_used: false" in JAVASCRIPT
    assert "operator_gguf_quality_certified: false" in JAVASCRIPT
    assert "if (!state.connected || unresolved() || state.health?.ready !== true)" in JAVASCRIPT
    # A successful HTTP health GET alone must never certify model generation.
    assert JAVASCRIPT.index("const saved = await api('GET', '/v1/sessions/' + claim.session_id)") > JAVASCRIPT.index("async function completeSelfTest(")


def test_installed_local_browser_exposes_executable_sha_verified_inference_acceptance():
    """Browser control must use genuine async local HTTP and committed SQLite.

    This source contract is not a substitute for a real operator GGUF/UI run;
    it catches disconnected mock buttons and false green read-only pings.
    """
    from skeleton.app.offline_web import HTML, JAVASCRIPT, CSS

    for control in ("selftest-start", "selftest-panel",
                    "selftest-result", "selftest-export"):
        assert f'id="{control}"' in HTML
    assert "selftest-panel" in CSS
    assert "get('selftest-start').addEventListener('click', () => run(startSelfTest))" in JAVASCRIPT
    assert "async function startSelfTest()" in JAVASCRIPT
    assert "async function completeSelfTest(ticket, epoch)" in JAVASCRIPT
    assert "observed.local_only !== true" in JAVASCRIPT
    assert "state.health?.ready !== true" in JAVASCRIPT
    assert "'/v1/sessions/' + session_id + '/turns'" in JAVASCRIPT
    assert "'/v1/sessions/' + claim.session_id" in JAVASCRIPT
    assert "crypto.subtle.digest('SHA-256', binary)" in JAVASCRIPT
    assert "receipt?.output_sha256 !== result.output_digest" in JAVASCRIPT
    assert "receipt?.model_digest !== claim.model_digest" in JAVASCRIPT
    assert "result.replayed !== false" in JAVASCRIPT
    assert "state.selfTestReport = null;" in JAVASCRIPT
    assert "operator_gguf_quality_certified: false" in JAVASCRIPT
    assert "independent_device_release_certified: false" in JAVASCRIPT
    assert "Download nonsecret qualification receipt" in HTML
    assert "localhost" in HTML
    # CSP intentionally allows no remote script, origin or exfiltration sink.
    assert "script-src 'self'; style-src 'self';" in JAVASCRIPT or "script-src" not in JAVASCRIPT
    assert "fetch('https://" not in JAVASCRIPT


def test_real_model_reference_receipt_matches_selftest_browser_integrity_contract():
    """The actual native/SQLite contract has the fields used in browser verification."""
    import hashlib
    from skeleton.app.offline_http import OfflineHTTPApplication

    model = native_model()
    from tempfile import TemporaryDirectory
    from pathlib import Path

    with TemporaryDirectory() as directory:
        app = OfflineHTTPApplication(
            model, Path(directory) / "local-browser-selftest.sqlite3",
            token="s" * 64,
        )
        try:
            _, created = app.dispatch("POST", "/v1/sessions", {})
            sid = created["session_id"]
            status, turn = app.dispatch("POST", "/v1/sessions/" + sid + "/turn", {
                "message": "Local inference acceptance: respond with one brief sentence about offline computing.",
                "request_id": "browser-live-acceptance-2026",
                "max_output_tokens": 2,
                "grounded": False,
            })
            assert status == 200
            assert turn["text"].strip()
            assert turn["replayed"] is False
            assert turn["output_tokens"] >= 1
            assert turn["output_digest"] == hashlib.sha256(
                turn["text"].encode("utf-8"),
            ).hexdigest()
            receipt = turn["local_execution_receipt"]
            assert receipt["model_digest"] == turn["model_digest"]
            assert receipt["output_sha256"] == turn["output_digest"]
            assert receipt["revision"] == turn["revision"]
            assert len(receipt["execution_receipt_digest"]) == 64
            status, stored = app.dispatch("GET", "/v1/sessions/" + sid)
            assert status == 200
            assert stored["revision"] == turn["revision"]
            assert [m["content"] for m in stored["messages"] if m["role"] == "assistant"][-1] == turn["text"]
        finally:
            app.close()
