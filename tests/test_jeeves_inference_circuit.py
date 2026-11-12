"""November 2026 local Jeeves execution admission: fault-injection regressions.

This suite exercises native model failure isolation and real SQLite replay.
It does not claim to execute an operator-owned production GGUF or handset AI.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from skeleton.app.jeeves_inference_circuit import LocalInferenceCircuit
from skeleton.app.offline_http import OfflineHTTPApplication, OfflineHTTPError
from skeleton.app.local_ai import DurableOfflineAISession
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeBackendError
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.cortex.transformer import TinyTransformer


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def move(self, seconds: float) -> None:
        self.now += seconds


def native_model() -> NativeRuntimeLocalModel:
    return NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer",
               "local", "offline", "jeeves", "computer", ".", " "),
        dim=8, ctx=1024, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )))


def test_failed_native_inference_circuit_opens_and_single_probe_recovers():
    clock = Clock()
    circuit = LocalInferenceCircuit(clock=clock)
    for failures in (1, 2):
        circuit.record_failure()
        status = circuit.status()
        assert status["state"] == "closed"
        assert status["recent_runtime_failures"] == failures
        assert status["admit_new_inference"] is True
    circuit.record_failure()
    state = circuit.status()
    assert state["state"] == "open"
    assert state["retry_after_seconds"] == 10
    assert state["next_cooldown_seconds"] == 20
    assert state["admit_new_inference"] is False
    clock.move(9)
    assert circuit.status()["retry_after_seconds"] == 1
    clock.move(1)
    assert circuit.status()["state"] == "probe_ready"
    circuit.record_success()
    assert circuit.status() == {
        "state": "closed", "admit_new_inference": True,
        "recent_runtime_failures": 0, "failure_threshold": 3,
        "retry_after_seconds": 0, "window_seconds": 60,
        "next_cooldown_seconds": 10,
    }


def test_retry_probe_failure_doubles_cooldown_with_strict_upper_bound():
    clock = Clock()
    circuit = LocalInferenceCircuit(
        failure_threshold=2, cooldown_seconds=3,
        maximum_cooldown_seconds=7, clock=clock,
    )
    for attempt, cooldown in ((0, 3), (1, 6), (2, 7), (3, 7)):
        if attempt == 0:
            circuit.record_failure()
            circuit.record_failure()
        else:
            assert circuit.status()["state"] == "probe_ready"
            circuit.record_failure()
        assert circuit.status()["state"] == "open"
        assert circuit.status()["retry_after_seconds"] == cooldown
        clock.move(cooldown)
    assert circuit.status()["state"] == "probe_ready"
    circuit.record_success()
    circuit.record_failure()
    circuit.record_failure()
    assert circuit.status()["retry_after_seconds"] == 3


def test_failures_expire_outside_window_without_opening():
    clock = Clock()
    circuit = LocalInferenceCircuit(failure_threshold=3, window_seconds=5, clock=clock)
    circuit.record_failure()
    circuit.record_failure()
    clock.move(5)
    assert circuit.status()["recent_runtime_failures"] == 0
    circuit.record_failure()
    assert circuit.status()["state"] == "closed"
    assert circuit.status()["recent_runtime_failures"] == 1


@pytest.mark.parametrize("overrides", [
    {"failure_threshold": 1},
    {"failure_threshold": True},
    {"failure_threshold": 21},
    {"window_seconds": 4},
    {"window_seconds": True},
    {"cooldown_seconds": 0},
    {"maximum_cooldown_seconds": 0},
    {"maximum_cooldown_seconds": True},
    {"cooldown_seconds": 20, "maximum_cooldown_seconds": 10},
    {"clock": "not-a-clock"},
])
def test_rejects_invalid_circuit_policies(overrides):
    with pytest.raises(ValueError, match="invalid bounded"):
        LocalInferenceCircuit(**overrides)


def test_circuit_status_does_not_serialize_prompts_paths_credentials_or_errors():
    clock = Clock()
    circuit = LocalInferenceCircuit(clock=clock)
    circuit.record_failure()
    circuit.record_failure()
    circuit.record_failure()
    state = circuit.status()
    assert all(type(v) in (str, int, bool) for v in state.values())
    assert "prompt" not in repr(state)
    assert "exception" not in repr(state)
    assert "credentials" not in repr(state)
    assert "model_path" not in state
    assert state["retry_after_seconds"] > 0


def test_local_http_health_refuses_new_generation_but_replays_saved_sqlite(tmp_path):
    model = native_model()
    app = OfflineHTTPApplication(model, tmp_path / "circuit-chat.sqlite3", token="x" * 64)
    try:
        _, session = app.dispatch("POST", "/v1/sessions", {})
        sid = session["session_id"]
        request = {"message": "hello", "request_id": "before-circuit-1",
                   "max_output_tokens": 2}
        result_status, committed = app.dispatch(
            "POST", f"/v1/sessions/{sid}/turn", request,
        )
        assert result_status == 200 and committed["revision"] == 1
        for _ in range(3):
            app._inference_circuit.record_failure()
        status, health = app.dispatch("GET", "/v1/status")
        assert status == 200 and health["ready"] is False
        assert health["model_readiness_code"] == "local_execution_circuit_open"
        assert health["inference_circuit"]["state"] == "open"
        with pytest.raises(OfflineHTTPError, match="local_execution_circuit_open") as rejected:
            app.dispatch("POST", f"/v1/sessions/{sid}/turns", {
                **request, "request_id": "model-must-not-run",
            })
        assert rejected.value.status == 503
        # Both synchronous and asynchronous committed retries must survive
        # the circuit without starting native inference again.
        _, sync_replay = app.dispatch("POST", f"/v1/sessions/{sid}/turn", request)
        assert sync_replay["replayed"] is True
        assert sync_replay["output_digest"] == committed["output_digest"]
        status, async_replay = app.dispatch(
            "POST", f"/v1/sessions/{sid}/turns", request,
        )
        assert status == 200 and async_replay["result"]["replayed"] is True
        assert async_replay["result"]["output_digest"] == committed["output_digest"]
        _, saved = app.dispatch("GET", f"/v1/sessions/{sid}")
        assert saved["revision"] == 1
    finally:
        app.close()


def test_actual_backend_failure_trips_http_circuit_without_leaking_details(
    tmp_path, monkeypatch,
):
    model = native_model()
    app = OfflineHTTPApplication(model, tmp_path / "fail-chat.sqlite3", token="x" * 64)
    secret = "/owner/private-weights/API-SECRET.gguf"
    async def fail_backend(self, *args, **kwargs):
        raise NativeRuntimeBackendError("native execution failed: " + secret)
    monkeypatch.setattr(DurableOfflineAISession, "ask", fail_backend)
    try:
        _, session = app.dispatch("POST", "/v1/sessions", {})
        sid = session["session_id"]
        for i in range(3):
            with pytest.raises(NativeRuntimeBackendError):
                app.dispatch("POST", f"/v1/sessions/{sid}/turn", {
                    "message": "hello", "request_id": f"native-fault-{i}",
                    "max_output_tokens": 2,
                })
            _, state = app.dispatch("GET", "/v1/status")
            assert secret not in repr(state)
            assert state["inference_circuit"]["recent_runtime_failures"] == i + 1
        assert state["model_readiness_code"] == "local_execution_circuit_open"
        assert state["ready"] is False
        with pytest.raises(OfflineHTTPError) as refused:
            app.dispatch("POST", f"/v1/sessions/{sid}/turn", {
                "message": "hello", "request_id": "native-fault-4",
                "max_output_tokens": 2,
            })
        assert refused.value.status == 503
    finally:
        app.close()


def test_cancel_and_invalid_requests_do_not_trip_native_circuit(tmp_path, monkeypatch):
    model = native_model()
    app = OfflineHTTPApplication(model, tmp_path / "cancel-chat.sqlite3", token="x" * 64)
    try:
        _, session = app.dispatch("POST", "/v1/sessions", {})
        sid = session["session_id"]
        with pytest.raises(OfflineHTTPError):
            app.dispatch("POST", f"/v1/sessions/{sid}/turn", {
                "message": "", "request_id": "invalid-prompt", "max_output_tokens": 2,
            })
        assert app._inference_circuit.status()["recent_runtime_failures"] == 0
        async def cancel_backend(self, *args, **kwargs):
            raise asyncio.CancelledError()
        monkeypatch.setattr(DurableOfflineAISession, "ask", cancel_backend)
        with pytest.raises(asyncio.CancelledError):
            app.dispatch("POST", f"/v1/sessions/{sid}/turn", {
                "message": "hello", "request_id": "cancelled-prompt",
                "max_output_tokens": 2,
            })
        assert app._inference_circuit.status()["recent_runtime_failures"] == 0
    finally:
        app.close()


def test_sync_exact_replay_remains_available_while_different_turn_runs(
    tmp_path, monkeypatch,
):
    """An active native worker cannot starve committed SQLite replay."""
    import threading
    model = native_model()
    app = OfflineHTTPApplication(model, tmp_path / "active-replay.sqlite3", token="x" * 64)
    begin = threading.Event()
    release = threading.Event()
    failures = []
    try:
        _, session = app.dispatch("POST", "/v1/sessions", {})
        sid = session["session_id"]
        original = {
            "message": "hello", "request_id": "already-committed",
            "max_output_tokens": 2,
        }
        _, first = app.dispatch("POST", f"/v1/sessions/{sid}/turn", original)
        real_ask = DurableOfflineAISession.ask

        async def blocked_native_ask(session, prompt, *args, **kwargs):
            if prompt == "world":
                # Pause INSIDE the actual generation-wide _perform_turn lock.
                # A replay that calls _perform_turn will deadlock here until
                # release, proving the old implementation was insufficient.
                begin.set()
                if not await asyncio.to_thread(release.wait, 10):
                    raise RuntimeError("test fixture release not signalled")
            return await real_ask(session, prompt, *args, **kwargs)

        monkeypatch.setattr(DurableOfflineAISession, "ask", blocked_native_ask)

        def run_new_turn():
            try:
                app.dispatch("POST", f"/v1/sessions/{sid}/turn", {
                    "message": "world", "request_id": "competing-live-turn",
                    "max_output_tokens": 2,
                })
            except BaseException as exc:
                failures.append(exc)

        worker = threading.Thread(target=run_new_turn)
        worker.start()
        assert begin.wait(timeout=5)
        # Read-only idempotent replay does not wait for the live worker.
        status, old = app.dispatch("POST", f"/v1/sessions/{sid}/turn", original)
        assert status == 200 and old["replayed"] is True
        assert old["output_digest"] == first["output_digest"]
        with pytest.raises(OfflineHTTPError) as concurrent:
            app.dispatch("POST", f"/v1/sessions/{sid}/turn", {
                "message": "another", "request_id": "competing-third-turn",
                "max_output_tokens": 2,
            })
        assert concurrent.value.status == 409
    finally:
        release.set()
        if "worker" in locals():
            worker.join(timeout=12)
            assert not worker.is_alive()
        app.close()
    assert not failures


def test_offline_workspace_displays_real_model_health_not_just_connected_socket():
    """New work is gated by measured readiness; saved sessions remain selectable."""
    from skeleton.app.offline_web import HTML, JAVASCRIPT

    assert 'id="health-refresh"' in HTML
    assert "async function refreshHealth()" in JAVASCRIPT
    assert "'local_execution_circuit_open'" in JAVASCRIPT
    assert "state.health?.ready !== true" in JAVASCRIPT
    assert "LOCAL • DEGRADED" in JAVASCRIPT
    assert "No hosted fallback" in JAVASCRIPT or "no hosted fallback" in JAVASCRIPT
    assert "get('retry-turn').disabled = locked || working" in JAVASCRIPT


def test_completed_live_ticket_requires_current_durable_execution_receipt(tmp_path):
    """No in-memory 'complete' may survive corrupted SQLite execution custody."""
    import time
    from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError

    app = OfflineHTTPApplication(
        native_model(), tmp_path / "live-ticket-integrity.sqlite3", token="x" * 64
    )
    try:
        _, session = app.dispatch("POST", "/v1/sessions", {})
        sid = session["session_id"]
        rid = "native-live-ticket-integrity"
        status, queued = app.dispatch("POST", f"/v1/sessions/{sid}/turns", {
            "message": "hello", "request_id": rid, "max_output_tokens": 2,
        })
        assert status == 202 and queued["request_id"] == rid
        deadline = time.monotonic() + 10
        while True:
            verified = app.turn_status(sid, rid)
            if verified["terminal"] or time.monotonic() >= deadline:
                break
            time.sleep(0.01)
        assert verified["state"] == "complete"
        assert verified["result"]["replayed"] is False
        assert verified["result"]["local_execution_receipt"] is not None
        with app._store._transaction():
            removed = app._store._db.execute(
                "DELETE FROM offline_turn_execution_receipts "
                "WHERE session_id=? AND request_id=?", (sid, rid),
            )
            assert removed.rowcount == 1
        with pytest.raises(RuntimeContractError, match="required local execution receipt"):
            app.turn_status(sid, rid)
    finally:
        app.close()
