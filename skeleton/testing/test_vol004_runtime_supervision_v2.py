from __future__ import annotations

import json
from types import SimpleNamespace
import urllib.error

import pytest

from skeleton.automation import chatgpt_adapter, free_model
from skeleton.automation.chatgpt_adapter import (
    ChatGPTReasoner,
    ReasoningRequest,
)
from skeleton.automation.free_model import FreeModelClient
from skeleton.automation.shift_supervisor import model_gateway
from skeleton.automation.shift_supervisor.model_gateway import ModelGateway
from skeleton.kernel.runtime_supervision import (
    RuntimeServiceLifecycle,
    RuntimeSupervisionError,
    ServicePhase,
)
from skeleton.shells.cancellation import (
    CancellationError,
    CancellationReason,
    CancellationToken,
)


class _Response:
    def __init__(self, payload: dict[str, object], *, on_read=None) -> None:
        self._payload = json.dumps(payload).encode("utf-8")
        self._on_read = on_read

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _limit: int) -> bytes:
        if self._on_read is not None:
            self._on_read()
        return self._payload


def test_shared_lifecycle_revokes_admission_before_shutdown_completion() -> None:
    now = [1.0]
    lifecycle = RuntimeServiceLifecycle("backend", clock=lambda: now[0])

    assert lifecycle.phase is ServicePhase.STARTING
    assert lifecycle.admits_work is False
    lifecycle.mark_ready()
    lifecycle.require_work_admission()
    assert lifecycle.admits_work is True

    now[0] = 2.0
    receipt = lifecycle.begin_drain(reason="rolling-shutdown")
    assert receipt.from_phase is ServicePhase.READY
    assert receipt.to_phase is ServicePhase.DRAINING
    assert receipt.cancellation.reason is CancellationReason.SHUTDOWN
    assert lifecycle.admits_work is False
    with pytest.raises(CancellationError):
        lifecycle.require_work_admission()

    now[0] = 3.0
    stopped = lifecycle.mark_stopped()
    assert stopped.to_phase is ServicePhase.STOPPED
    assert [item.sequence for item in lifecycle.receipts()] == [1, 2, 3]


def test_restart_creates_fresh_generation_and_stale_token_stays_cancelled() -> None:
    lifecycle = RuntimeServiceLifecycle("skeleton")
    lifecycle.mark_ready()
    old_token = lifecycle.cancellation
    lifecycle.begin_drain(reason="upgrade")
    lifecycle.mark_stopped()

    restarted = lifecycle.restart(reason="post-upgrade")
    assert restarted.generation == 2
    assert lifecycle.generation == 2
    assert lifecycle.phase is ServicePhase.STARTING
    assert lifecycle.cancellation is not old_token
    assert lifecycle.cancellation.cancelled is False
    assert old_token.cancelled is True


def test_lifecycle_rejects_impossible_or_reopening_transitions() -> None:
    lifecycle = RuntimeServiceLifecycle("backend")
    lifecycle.mark_ready()
    with pytest.raises(RuntimeSupervisionError):
        lifecycle.mark_ready()
    lifecycle.begin_drain()
    lifecycle.mark_stopped()
    with pytest.raises(RuntimeSupervisionError):
        lifecycle.begin_drain()
    with pytest.raises(RuntimeSupervisionError):
        lifecycle.mark_ready()


def _provider_receipt():
    return SimpleNamespace(as_dict=lambda: {"provider_id": "repository-automation"})


def test_free_model_pre_cancelled_request_never_opens_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_API_URL", "https://example.com/v1/chat/completions")
    monkeypatch.setenv("MODEL_API_KEY", "secret")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setattr(free_model, "load_provider_architecture", lambda *a, **k: _provider_receipt())
    opened = []
    monkeypatch.setattr(
        free_model.urllib.request,
        "urlopen",
        lambda *a, **k: opened.append(True),
    )
    token = CancellationToken()
    token.cancel(CancellationReason.USER, detail="operator stop")
    client = FreeModelClient()

    with pytest.raises(CancellationError):
        client.chat("system", "user", cancellation=token)
    assert opened == []


def test_free_model_discards_response_that_arrives_after_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_API_URL", "https://example.com/v1/chat/completions")
    monkeypatch.setenv("MODEL_API_KEY", "secret")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setattr(free_model, "load_provider_architecture", lambda *a, **k: _provider_receipt())
    token = CancellationToken()
    payload = {"choices": [{"message": {"content": "late-authoritative-text"}}]}
    monkeypatch.setattr(
        free_model.urllib.request,
        "urlopen",
        lambda *a, **k: _Response(
            payload,
            on_read=lambda: token.cancel(
                CancellationReason.SUPERSEDED,
                detail="newer run owns authority",
            ),
        ),
    )
    client = FreeModelClient()

    with pytest.raises(CancellationError):
        client.chat("system", "user", cancellation=token)


def test_shift_gateway_retry_backoff_is_immediately_cancellable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_gateway, "enforce_bot_activation_security", lambda: None)
    gateway = ModelGateway(
        timeout_seconds=1.0,
        max_attempts=3,
        max_non_rate_limit_attempts=3,
    )
    monkeypatch.setattr(
        gateway,
        "_config",
        lambda: ("https://example.com/v1/responses", "secret", "test-model"),
    )
    attempts = []
    def fail(*_args, **_kwargs):
        attempts.append(1)
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(model_gateway.urllib.request, "urlopen", fail)

    token = CancellationToken()
    def cancel_wait(_delay: float) -> bool:
        token.cancel(CancellationReason.SHUTDOWN, detail="runner draining")
        return True
    monkeypatch.setattr(token, "wait", cancel_wait)

    with pytest.raises(CancellationError):
        gateway.call_json(
            system_prompt="system",
            user_prompt="user",
            correlation_id="corr-1",
            cancellation=token,
        )
    assert len(attempts) == 1


def test_chatgpt_reasoner_discards_late_cancelled_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chatgpt_adapter, "enforce_bot_activation_security", lambda: None)
    monkeypatch.setattr(
        chatgpt_adapter,
        "load_provider_architecture",
        lambda *a, **k: _provider_receipt(),
    )
    token = CancellationToken()
    payload = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "late advice"}],
            }
        ]
    }
    monkeypatch.setattr(
        chatgpt_adapter.request,
        "urlopen",
        lambda *a, **k: _Response(
            payload,
            on_read=lambda: token.cancel(
                CancellationReason.POLICY,
                detail="policy changed",
            ),
        ),
    )
    reasoner = ChatGPTReasoner(api_key="secret", model="test-model")

    with pytest.raises(CancellationError):
        reasoner.reason(
            ReasoningRequest(task="inspect", evidence=("evidence",)),
            cancellation=token,
        )
