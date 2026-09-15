from __future__ import annotations

import asyncio
from types import SimpleNamespace

from skeleton.frontier import model_runtime as runtime


class _AsyncStream:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        self._iterator = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _OpenAICompletions:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return _AsyncStream(
                [
                    {"choices": [{"delta": {"content": "hel"}}]},
                    {"choices": [{"delta": {"content": "lo"}}]},
                ]
            )
        return {
            "model": kwargs["model"],
            "choices": [
                {
                    "message": {
                        "content": '{"answer": "ok"}',
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "lookup",
                                    "arguments": '{"q":"x"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        }


class _OpenAIEmbeddings:
    async def create(self, **kwargs):
        return {
            "model": kwargs["model"],
            "data": [{"embedding": [1, 2]}, {"embedding": [3, 4]}],
            "usage": {"prompt_tokens": 4},
        }


class _OpenAIClient:
    def __init__(self):
        self.completions = _OpenAICompletions()
        self.chat = SimpleNamespace(completions=self.completions)
        self.embeddings = _OpenAIEmbeddings()


class _LiteLLMClient:
    def __init__(self):
        self.calls = []

    async def acompletion(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return _AsyncStream(
                [
                    {"choices": [{"delta": {"content": "hel"}}]},
                    {"choices": [{"delta": {"content": "lo"}}]},
                ]
            )
        return {
            "model": kwargs["model"],
            "choices": [
                {
                    "message": {
                        "content": '{"answer": "ok"}',
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "lookup",
                                    "arguments": '{"q":"x"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        }

    async def aembedding(self, **kwargs):
        return {
            "model": kwargs["model"],
            "data": [{"embedding": [1, 2]}, {"embedding": [3, 4]}],
            "usage": {"prompt_tokens": 4},
        }


async def _adapter_contract(adapter):
    request = runtime.ChatRequest(
        model="model-x",
        messages=(runtime.ModelMessage("user", "hello"),),
        tools=(
            runtime.ToolDefinition(
                name="lookup",
                description="lookup",
                input_schema={"type": "object"},
            ),
        ),
        response_schema={"type": "object"},
    )
    response = await adapter.chat(request)
    assert response.text == '{"answer": "ok"}'
    assert response.structured == {"answer": "ok"}
    assert response.tool_calls[0].name == "lookup"
    assert response.tool_calls[0].arguments == {"q": "x"}
    assert response.usage.total_tokens == 5
    assert not hasattr(response, "choices")

    embedding = await adapter.embed(
        runtime.EmbeddingRequest(model="embed-x", inputs=("a", "b"))
    )
    assert embedding.vectors == ((1.0, 2.0), (3.0, 4.0))

    events = [event async for event in adapter.stream_chat(request)]
    assert [event.kind for event in events] == [
        "text_delta",
        "text_delta",
        "completed",
    ]
    assert events[-1].response.text == "hello"


def test_openai_and_litellm_pass_same_contract():
    async def run():
        await _adapter_contract(runtime.OpenAIChatCompletionsAdapter(_OpenAIClient()))
        await _adapter_contract(runtime.LiteLLMAdapter(_LiteLLMClient()))

    asyncio.run(run())


def test_runtime_retries_transient_failure_once():
    class Adapter:
        name = "retry"
        capabilities = frozenset({runtime.ModelCapability.CHAT})

        def __init__(self):
            self.calls = 0

        async def chat(self, request):
            self.calls += 1
            if self.calls == 1:
                raise runtime.TransientProviderError("temporary")
            return runtime.ChatResponse(model=request.model, text="ok")

        async def embed(self, request):
            raise AssertionError

        async def stream_chat(self, request):
            if False:
                yield None

    async def run():
        adapter = Adapter()
        model_runtime = runtime.ModelRuntime()
        model_runtime.register(adapter)
        response = await model_runtime.chat(
            "retry",
            runtime.ChatRequest("m", (runtime.ModelMessage("user", "x"),)),
            retry_policy=runtime.RetryPolicy(max_attempts=2),
        )
        assert response.text == "ok"
        assert adapter.calls == 2

    asyncio.run(run())


def test_timeout_and_precancel_are_deterministic():
    class Adapter:
        name = "slow"
        capabilities = frozenset({runtime.ModelCapability.CHAT})

        def __init__(self):
            self.calls = 0

        async def chat(self, request):
            self.calls += 1
            await asyncio.sleep(1)
            return runtime.ChatResponse(model=request.model, text="late")

        async def embed(self, request):
            raise AssertionError

        async def stream_chat(self, request):
            if False:
                yield None

    async def run():
        adapter = Adapter()
        model_runtime = runtime.ModelRuntime()
        model_runtime.register(adapter)
        request = runtime.ChatRequest("m", (runtime.ModelMessage("user", "x"),))
        try:
            await model_runtime.chat("slow", request, timeout_seconds=0.01)
        except runtime.ProviderTimeoutError:
            pass
        else:
            raise AssertionError("timeout did not fail")

        token = runtime.CancellationToken()
        token.cancel()
        before = adapter.calls
        try:
            await model_runtime.chat("slow", request, cancellation=token)
        except runtime.ProviderCancelledError:
            pass
        else:
            raise AssertionError("cancellation did not fail")
        assert adapter.calls == before

    asyncio.run(run())


def test_structured_and_stream_fallbacks_are_explicit():
    class Adapter:
        name = "chat-only"
        capabilities = frozenset({runtime.ModelCapability.CHAT})

        async def chat(self, request):
            return runtime.ChatResponse(model=request.model, text='{"ok": true}')

        async def embed(self, request):
            raise AssertionError

        async def stream_chat(self, request):
            if False:
                yield None

    async def run():
        model_runtime = runtime.ModelRuntime()
        model_runtime.register(Adapter())
        request = runtime.ChatRequest(
            "m",
            (runtime.ModelMessage("user", "x"),),
            response_schema={"type": "object"},
        )
        try:
            await model_runtime.chat("chat-only", request)
        except runtime.UnsupportedCapabilityError:
            pass
        else:
            raise AssertionError("structured capability unexpectedly implicit")

        response = await model_runtime.chat(
            "chat-only", request, allow_structured_fallback=True
        )
        assert response.structured == {"ok": True}

        plain = runtime.ChatRequest("m", (runtime.ModelMessage("user", "x"),))
        events = [
            event
            async for event in model_runtime.stream_chat(
                "chat-only", plain, allow_nonstream_fallback=True
            )
        ]
        assert [event.kind for event in events] == ["text_delta", "completed"]

    asyncio.run(run())
