from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
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
from skeleton import provider_runtime
from skeleton.provider_runtime import (
    OpenAIProviderAdapter,
    OpenAISyncProviderAdapter,
    ProviderImageRequest,
    ProviderInvocationError,
    ProviderRequest,
    ProviderSpeechRequest,
)
from skeleton.kernel.runtime_supervision import (
    RuntimeAdmissionMiddleware,
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


def test_work_leases_are_generation_bound_and_stop_requires_quiescence() -> None:
    lifecycle = RuntimeServiceLifecycle("skeleton")
    lifecycle.mark_ready()
    first = lifecycle.acquire_work("work:b")
    second = lifecycle.acquire_work("work:a")

    assert lifecycle.active_work() == (second, first)
    assert lifecycle.snapshot()["active_work_ids"] == ["work:a", "work:b"]
    assert lifecycle.inflight_work == 2

    with pytest.raises(RuntimeSupervisionError, match="already leased"):
        lifecycle.acquire_work("work:a")

    lifecycle.begin_drain(reason="upgrade")
    with pytest.raises(RuntimeSupervisionError, match="in-flight work leases"):
        lifecycle.mark_stopped()

    assert lifecycle.release_work(second) is True
    assert lifecycle.release_work(second) is False
    assert lifecycle.release_work(first) is True
    lifecycle.mark_stopped()
    restarted = lifecycle.restart()
    assert restarted.generation == 2


def test_generated_work_ids_are_monotonic_and_generation_bound() -> None:
    lifecycle = RuntimeServiceLifecycle("backend")
    lifecycle.mark_ready()

    first = lifecycle.acquire_generated_work("http")
    second = lifecycle.acquire_generated_work("http")
    assert first.work_id == "http:1:1"
    assert second.work_id == "http:1:2"
    assert first.generation == second.generation == 1

    lifecycle.release_work(first)
    lifecycle.release_work(second)
    lifecycle.begin_drain(reason="restart")
    lifecycle.mark_stopped()
    lifecycle.restart()
    lifecycle.mark_ready()

    third = lifecycle.acquire_generated_work("http")
    assert third.work_id == "http:2:3"
    assert third.generation == 2
    lifecycle.release_work(third)

    with pytest.raises(ValueError, match="must not contain"):
        lifecycle.acquire_generated_work("http:unsafe")


@pytest.mark.asyncio
async def test_bounded_provider_call_rejects_expired_work_before_dispatch() -> None:
    calls: list[str] = []

    async def operation():
        calls.append("dispatched")
        return object()

    with pytest.raises(ProviderInvocationError, match="deadline exceeded"):
        await provider_runtime._await_bounded_provider_call(
            operation,
            deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
            configured_timeout=10.0,
            label="test provider",
        )
    assert calls == []


@pytest.mark.asyncio
async def test_bounded_provider_call_cancels_slow_operation_at_timeout() -> None:
    finalized = asyncio.Event()

    async def operation():
        try:
            await asyncio.sleep(60)
        finally:
            finalized.set()

    with pytest.raises(ProviderInvocationError, match="deadline exceeded"):
        await provider_runtime._await_bounded_provider_call(
            operation,
            deadline=None,
            configured_timeout=0.01,
            label="test provider",
        )
    assert finalized.is_set()


@pytest.mark.asyncio
async def test_all_provider_media_operations_reject_expired_deadline_before_io() -> None:
    adapter = OpenAIProviderAdapter(client=object())
    expired = datetime.now(timezone.utc) - timedelta(seconds=1)

    calls = (
        adapter.generate_image(
            ProviderImageRequest(
                prompt="image",
                deadline=expired,
            )
        ),
        adapter.create_image_variation(
            b"image-bytes",
            deadline=expired,
        ),
        adapter.edit_image(
            b"image-bytes",
            prompt="edit",
            deadline=expired,
        ),
        adapter.synthesize_speech(
            ProviderSpeechRequest(
                text="speech",
                deadline=expired,
            )
        ),
    )
    for call in calls:
        with pytest.raises(
            ProviderInvocationError,
            match="deadline exceeded",
        ):
            await call


def test_sync_provider_pre_cancelled_request_never_reaches_architecture_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = OpenAISyncProviderAdapter(api_key="secret")
    token = CancellationToken()
    token.cancel(CancellationReason.USER, detail="operator stop")

    monkeypatch.setattr(
        adapter,
        "_ensure_architecture",
        lambda: (_ for _ in ()).throw(
            AssertionError("architecture should not be touched")
        ),
    )
    monkeypatch.setattr(
        provider_runtime.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("network should not be opened")
        ),
    )

    with pytest.raises(CancellationError):
        adapter.generate_sync(
            ProviderRequest(instructions="system", prompt="user"),
            cancellation=token,
        )


def test_sync_provider_discards_response_cancelled_during_blocking_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = OpenAISyncProviderAdapter(api_key="secret", max_retries=2)
    token = CancellationToken()

    monkeypatch.setattr(
        adapter,
        "_ensure_architecture",
        lambda: SimpleNamespace(provider_id="openai"),
    )
    monkeypatch.setattr(
        provider_runtime,
        "require_provider_transfer",
        lambda *_args, **_kwargs: SimpleNamespace(
            decision_id="governance:test",
            data_class="internal",
        ),
    )
    monkeypatch.setattr(
        provider_runtime,
        "_admit_provider_request",
        lambda *_args, **_kwargs: (
            SimpleNamespace(
                decision=SimpleNamespace(decision_id="admission:test")
            ),
            SimpleNamespace(),
        ),
    )
    quarantined: list[str] = []
    monkeypatch.setattr(
        provider_runtime,
        "_quarantine_provider_usage",
        lambda *_args, **kwargs: quarantined.append(
            str(kwargs.get("reason") or "")
        ),
    )

    monkeypatch.setattr(
        provider_runtime.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            {"output": []},
            on_read=lambda: token.cancel(
                CancellationReason.SUPERSEDED,
                detail="newer synchronous run owns authority",
            ),
        ),
    )

    with pytest.raises(CancellationError):
        adapter.generate_sync(
            ProviderRequest(instructions="system", prompt="user"),
            cancellation=token,
        )
    assert quarantined == ["provider-dispatch-or-response-ambiguous"]


def _run_asgi(middleware, *, path: str):
    messages: list[dict[str, object]] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(dict(message))

    async def run():
        await middleware(
            {
                "type": "http",
                "method": "GET",
                "path": path,
                "headers": [],
            },
            receive,
            send,
        )

    asyncio.run(run())
    return messages


def test_runtime_admission_middleware_admits_ready_and_releases_lease() -> None:
    lifecycle = RuntimeServiceLifecycle("backend")
    lifecycle.mark_ready()
    calls: list[str] = []

    async def app(_scope, _receive, send):
        calls.append("called")
        assert lifecycle.inflight_work == 1
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    middleware = RuntimeAdmissionMiddleware(
        app,
        lifecycle=lifecycle,
        exempt_prefixes=("/api/health",),
    )
    messages = _run_asgi(middleware, path="/api/projects")

    assert calls == ["called"]
    assert messages[0]["status"] == 204
    assert lifecycle.inflight_work == 0


def test_runtime_admission_middleware_rejects_starting_and_drain() -> None:
    lifecycle = RuntimeServiceLifecycle("backend")
    calls: list[str] = []

    async def app(_scope, _receive, _send):
        calls.append("called")

    middleware = RuntimeAdmissionMiddleware(
        app,
        lifecycle=lifecycle,
        exempt_prefixes=("/api/health",),
    )

    for path in ("/api/projects", "/api/healthcheck"):
        messages = _run_asgi(middleware, path=path)
        assert messages[0]["status"] == 503
        headers = dict(messages[0]["headers"])
        assert headers[b"retry-after"] == b"1"
    assert calls == []

    lifecycle.mark_ready()
    lifecycle.begin_drain(reason="shutdown")
    messages = _run_asgi(middleware, path="/api/projects")
    assert messages[0]["status"] == 503
    assert calls == []


def test_runtime_admission_health_exemption_is_segment_safe() -> None:
    lifecycle = RuntimeServiceLifecycle("backend")
    calls: list[str] = []

    async def app(scope, _receive, send):
        calls.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    middleware = RuntimeAdmissionMiddleware(
        app,
        lifecycle=lifecycle,
        exempt_prefixes=("/api/health",),
    )

    for path in ("/api/health", "/api/health/live", "/api/health/ready"):
        messages = _run_asgi(middleware, path=path)
        assert messages[0]["status"] == 200
    assert calls == ["/api/health", "/api/health/live", "/api/health/ready"]

    messages = _run_asgi(middleware, path="/api/healthz")
    assert messages[0]["status"] == 503


def test_runtime_admission_releases_lease_when_handler_raises() -> None:
    lifecycle = RuntimeServiceLifecycle("skeleton")
    lifecycle.mark_ready()

    async def app(_scope, _receive, _send):
        assert lifecycle.inflight_work == 1
        raise RuntimeError("handler failed")

    middleware = RuntimeAdmissionMiddleware(app, lifecycle=lifecycle)

    with pytest.raises(RuntimeError, match="handler failed"):
        _run_asgi(middleware, path="/api/v1/engine/executions")
    assert lifecycle.inflight_work == 0


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
from __future__ import annotations

import asyncio
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
    RuntimeAdmissionMiddleware,
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


def test_work_leases_are_generation_bound_and_stop_requires_quiescence() -> None:
    lifecycle = RuntimeServiceLifecycle("skeleton")
    lifecycle.mark_ready()
    first = lifecycle.acquire_work("work:b")
    second = lifecycle.acquire_work("work:a")

    assert lifecycle.active_work() == (second, first)
    assert lifecycle.snapshot()["active_work_ids"] == ["work:a", "work:b"]
    assert lifecycle.inflight_work == 2

    with pytest.raises(RuntimeSupervisionError, match="already leased"):
        lifecycle.acquire_work("work:a")

    lifecycle.begin_drain(reason="upgrade")
    with pytest.raises(RuntimeSupervisionError, match="in-flight work leases"):
        lifecycle.mark_stopped()

    assert lifecycle.release_work(second) is True
    assert lifecycle.release_work(second) is False
    assert lifecycle.release_work(first) is True
    lifecycle.mark_stopped()
    restarted = lifecycle.restart()
    assert restarted.generation == 2


def _run_asgi(middleware, *, path: str):
    messages: list[dict[str, object]] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(dict(message))

    async def run():
        await middleware(
            {
                "type": "http",
                "method": "GET",
                "path": path,
                "headers": [],
            },
            receive,
            send,
        )

    asyncio.run(run())
    return messages


def test_runtime_admission_middleware_admits_ready_and_releases_lease() -> None:
    lifecycle = RuntimeServiceLifecycle("backend")
    lifecycle.mark_ready()
    calls: list[str] = []

    async def app(_scope, _receive, send):
        calls.append("called")
        assert lifecycle.inflight_work == 1
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    middleware = RuntimeAdmissionMiddleware(
        app,
        lifecycle=lifecycle,
        exempt_prefixes=("/api/health",),
    )
    messages = _run_asgi(middleware, path="/api/projects")

    assert calls == ["called"]
    assert messages[0]["status"] == 204
    assert lifecycle.inflight_work == 0


def test_runtime_admission_middleware_rejects_starting_and_drain() -> None:
    lifecycle = RuntimeServiceLifecycle("backend")
    calls: list[str] = []

    async def app(_scope, _receive, _send):
        calls.append("called")

    middleware = RuntimeAdmissionMiddleware(
        app,
        lifecycle=lifecycle,
        exempt_prefixes=("/api/health",),
    )

    for path in ("/api/projects", "/api/healthcheck"):
        messages = _run_asgi(middleware, path=path)
        assert messages[0]["status"] == 503
        headers = dict(messages[0]["headers"])
        assert headers[b"retry-after"] == b"1"
    assert calls == []

    lifecycle.mark_ready()
    hidden = lifecycle.acquire_work("secret:execution-identity")
    lifecycle.begin_drain(reason="shutdown")
    messages = _run_asgi(middleware, path="/api/projects")
    assert messages[0]["status"] == 503
    payload = json.loads(messages[1]["body"].decode("utf-8"))
    assert payload["lifecycle"]["inflight_work"] == 1
    assert "active_work_ids" not in payload["lifecycle"]
    assert "cancellation" not in payload["lifecycle"]
    assert "secret:execution-identity" not in messages[1]["body"].decode("utf-8")
    assert calls == []
    lifecycle.release_work(hidden)


def test_runtime_admission_health_exemption_is_segment_safe() -> None:
    lifecycle = RuntimeServiceLifecycle("backend")
    calls: list[str] = []

    async def app(scope, _receive, send):
        calls.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    middleware = RuntimeAdmissionMiddleware(
        app,
        lifecycle=lifecycle,
        exempt_prefixes=("/api/health",),
    )

    for path in ("/api/health", "/api/health/live", "/api/health/ready"):
        messages = _run_asgi(middleware, path=path)
        assert messages[0]["status"] == 200
    assert calls == ["/api/health", "/api/health/live", "/api/health/ready"]

    messages = _run_asgi(middleware, path="/api/healthz")
    assert messages[0]["status"] == 503


def test_runtime_admission_releases_lease_when_handler_raises() -> None:
    lifecycle = RuntimeServiceLifecycle("skeleton")
    lifecycle.mark_ready()

    async def app(_scope, _receive, _send):
        assert lifecycle.inflight_work == 1
        raise RuntimeError("handler failed")

    middleware = RuntimeAdmissionMiddleware(app, lifecycle=lifecycle)

    with pytest.raises(RuntimeError, match="handler failed"):
        _run_asgi(middleware, path="/api/v1/engine/executions")
    assert lifecycle.inflight_work == 0


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
