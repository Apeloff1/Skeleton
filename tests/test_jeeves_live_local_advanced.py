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
