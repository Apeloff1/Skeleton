"""Regression coverage for provider streaming retry and load semantics."""
from __future__ import annotations

import asyncio

from skeleton.frontier import model_runtime as runtime
from skeleton.testing.provider_stream_reliability_profiles import (
    run_provider_stream_profile,
)


def test_stream_retries_only_before_first_event() -> None:
    class Adapter:
        name = "pre-emission-retry"
        capabilities = frozenset(
            {runtime.ModelCapability.CHAT, runtime.ModelCapability.STREAMING}
        )

        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, request):
            raise AssertionError

        async def embed(self, request):
            raise AssertionError

        async def stream_chat(self, request):
            self.calls += 1
            if self.calls < 3:
                await asyncio.sleep(0)
                raise runtime.TransientProviderError("temporary")
            yield runtime.StreamEvent(kind="text_delta", text_delta="ok")
            yield runtime.StreamEvent(
                kind="completed",
                response=runtime.ChatResponse(model=request.model, text="ok"),
            )

    async def run() -> None:
        adapter = Adapter()
        model_runtime = runtime.ModelRuntime()
        model_runtime.register(adapter)
        request = runtime.ChatRequest(
            "m",
            (runtime.ModelMessage("user", "x"),),
        )
        events = [
            event
            async for event in model_runtime.stream_chat(
                adapter.name,
                request,
                retry_policy=runtime.RetryPolicy(max_attempts=3),
            )
        ]
        assert adapter.calls == 3
        assert [event.kind for event in events] == ["text_delta", "completed"]
        assert events[0].text_delta == "ok"

    asyncio.run(run())


def test_stream_never_retries_after_output_started() -> None:
    class Adapter:
        name = "post-emission-failure"
        capabilities = frozenset(
            {runtime.ModelCapability.CHAT, runtime.ModelCapability.STREAMING}
        )

        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, request):
            raise AssertionError

        async def embed(self, request):
            raise AssertionError

        async def stream_chat(self, request):
            self.calls += 1
            yield runtime.StreamEvent(kind="text_delta", text_delta="partial")
            raise runtime.TransientProviderError("stream broke after output")

    async def run() -> None:
        adapter = Adapter()
        model_runtime = runtime.ModelRuntime()
        model_runtime.register(adapter)
        request = runtime.ChatRequest(
            "m",
            (runtime.ModelMessage("user", "x"),),
        )
        seen: list[str] = []
        try:
            async for event in model_runtime.stream_chat(
                adapter.name,
                request,
                retry_policy=runtime.RetryPolicy(max_attempts=5),
            ):
                seen.append(event.text_delta)
        except runtime.TransientProviderError:
            pass
        else:
            raise AssertionError("post-emission provider failure was swallowed")

        assert seen == ["partial"]
        assert adapter.calls == 1

    asyncio.run(run())


def test_stream_retry_budget_is_exact_under_exhaustion() -> None:
    class Adapter:
        name = "stream-exhaustion"
        capabilities = frozenset(
            {runtime.ModelCapability.CHAT, runtime.ModelCapability.STREAMING}
        )

        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, request):
            raise AssertionError

        async def embed(self, request):
            raise AssertionError

        async def stream_chat(self, request):
            self.calls += 1
            if False:
                yield runtime.StreamEvent(kind="text_delta", text_delta="never")
            raise runtime.TransientProviderError("still unavailable")

    async def run() -> None:
        adapter = Adapter()
        model_runtime = runtime.ModelRuntime()
        model_runtime.register(adapter)
        request = runtime.ChatRequest(
            "m",
            (runtime.ModelMessage("user", "x"),),
        )
        try:
            async for _event in model_runtime.stream_chat(
                adapter.name,
                request,
                retry_policy=runtime.RetryPolicy(max_attempts=4),
            ):
                raise AssertionError("exhausted stream emitted data")
        except runtime.TransientProviderError:
            pass
        else:
            raise AssertionError("stream exhaustion unexpectedly succeeded")
        assert adapter.calls == 4

    asyncio.run(run())


def test_stream_retry_shares_one_total_deadline() -> None:
    class Adapter:
        name = "stream-deadline"
        capabilities = frozenset(
            {runtime.ModelCapability.CHAT, runtime.ModelCapability.STREAMING}
        )

        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, request):
            raise AssertionError

        async def embed(self, request):
            raise AssertionError

        async def stream_chat(self, request):
            self.calls += 1
            if False:
                yield runtime.StreamEvent(kind="text_delta", text_delta="never")
            raise runtime.TransientProviderError("retry me")

    async def run() -> None:
        adapter = Adapter()
        model_runtime = runtime.ModelRuntime()
        model_runtime.register(adapter)
        request = runtime.ChatRequest(
            "m",
            (runtime.ModelMessage("user", "x"),),
        )
        try:
            async for _event in model_runtime.stream_chat(
                adapter.name,
                request,
                timeout_seconds=0.01,
                retry_policy=runtime.RetryPolicy(
                    max_attempts=10,
                    backoff_seconds=0.05,
                ),
            ):
                raise AssertionError("deadline stream emitted data")
        except runtime.ProviderTimeoutError:
            pass
        else:
            raise AssertionError("shared stream deadline did not fire")
        assert adapter.calls == 1

    asyncio.run(run())


def test_provider_stream_pressure_recovers_with_exact_attempts() -> None:
    result = asyncio.run(
        run_provider_stream_profile(
            runs=32,
            concurrency=8,
            chunks_per_run=3,
            transient_failures=2,
            max_attempts=3,
        )
    )
    assert result.invariants_passed
    assert result.completed == 32
    assert result.failed == 0
    assert result.total_provider_attempts == 96
    assert result.max_provider_attempts == 3
    assert result.total_events == 128


def test_provider_stream_pressure_fails_closed_at_retry_budget() -> None:
    result = asyncio.run(
        run_provider_stream_profile(
            runs=24,
            concurrency=6,
            chunks_per_run=2,
            transient_failures=5,
            max_attempts=2,
        )
    )
    assert result.invariants_passed
    assert result.completed == 0
    assert result.failed == 24
    assert result.total_provider_attempts == 48
    assert result.total_events == 0
