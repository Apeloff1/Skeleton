"""Local, credential-free model inference.

This module is deliberately independent from hosted model providers.  It owns a
small local inference contract, a learned reference language model used for
portable acceptance, a callable bridge for real open-weight runtimes, bounded
caching/batching, cooperative cancellation, and an adapter into Skeleton's
existing provider-neutral cognitive execution contract.

The reference n-gram model is not a quality target.  It is an executable model
that learns weights from a corpus and proves the complete local-model path can
run with the network and provider credentials absent.  Production open-weight
runtimes plug into CallableLocalModel without changing cognitive orchestration.
"""

from __future__ import annotations

import asyncio
from collections import Counter, OrderedDict
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
import random
import re
import threading
import time
from typing import Any, Callable, Mapping, Protocol, Sequence

from skeleton.provider_runtime import (
    ProviderAdapter,
    ProviderInvocationError,
    ProviderProtocolViolationError,
    ProviderRequest,
    ProviderResponse,
)
from skeleton.providers.contract import FinishReason, ProviderToolCall, ProviderUsage


_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_EOS = "<|eos|>"


class LocalInferenceCancelled(RuntimeError):
    """Cooperative local inference cancellation was observed."""


def _stable_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _tokenize(text: str) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(text))


def _detokenize(tokens: Sequence[str]) -> str:
    text = " ".join(tokens)
    for mark in (".", ",", "!", "?", ";", ":", ")", "]", "}"):
        text = text.replace(" " + mark, mark)
    for mark in ("(", "[", "{"):
        text = text.replace(mark + " ", mark)
    return text.strip()


@dataclass(frozen=True, slots=True)
class LocalToolCall:
    call_id: str
    tool_id: str
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.call_id.strip() or not self.tool_id.strip():
            raise ValueError("local tool call ids must be non-empty")
        encoded = _stable_json(dict(self.arguments))
        if len(encoded.encode("utf-8")) > 512 * 1024:
            raise ValueError("local tool call arguments exceed size limit")
        object.__setattr__(self, "arguments", dict(self.arguments))


@dataclass(frozen=True, slots=True)
class LocalInferenceRequest:
    prompt: str
    instructions: str = ""
    history: tuple[tuple[str, str], ...] = ()
    max_output_tokens: int = 256
    seed: int = 0
    stop: tuple[str, ...] = ()
    tools: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise ValueError("local inference prompt must be non-empty")
        if not isinstance(self.instructions, str):
            raise TypeError("instructions must be text")
        if (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or not 1 <= self.max_output_tokens <= 8192
        ):
            raise ValueError("max_output_tokens must be in [1, 8192]")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be an integer")
        normalized_history: list[tuple[str, str]] = []
        for role, content in self.history:
            if role not in {"user", "assistant"}:
                raise ValueError("local history role must be user or assistant")
            if not content.strip():
                raise ValueError("local history content must be non-empty")
            normalized_history.append((role, content))
        object.__setattr__(self, "history", tuple(normalized_history))
        object.__setattr__(
            self,
            "stop",
            tuple(dict.fromkeys(item for item in self.stop if isinstance(item, str) and item)),
        )
        object.__setattr__(self, "tools", tuple(dict(item) for item in self.tools))

    @property
    def rendered_input(self) -> str:
        parts: list[str] = []
        if self.instructions.strip():
            parts.append("system: " + self.instructions.strip())
        parts.extend(f"{role}: {content}" for role, content in self.history)
        parts.append("user: " + self.prompt.strip())
        parts.append("assistant:")
        return "\n".join(parts)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "prompt": self.prompt,
                "instructions": self.instructions,
                "history": self.history,
                "max_output_tokens": self.max_output_tokens,
                "seed": self.seed,
                "stop": self.stop,
                "tools": self.tools,
            }
        )


@dataclass(frozen=True, slots=True)
class LocalInferenceResult:
    text: str | None
    model_id: str
    model_digest: str
    input_tokens: int
    output_tokens: int
    finish_reason: str = "completed"
    response_id: str | None = None
    tool_calls: tuple[LocalToolCall, ...] = ()
    structured_output: Mapping[str, Any] | None = None
    latency_ms: float | None = None
    cached: bool = False

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("model_id must be non-empty")
        if len(self.model_digest) != 64:
            raise ValueError("model_digest must be sha256")
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("token counts must be non-negative")
        if self.finish_reason not in {
            "completed",
            "tool_calls",
            "length",
            "cancelled",
            "deadline",
        }:
            raise ValueError("invalid local finish_reason")
        if self.text is None and not self.tool_calls and self.structured_output is None:
            raise ValueError("local inference result must contain output")
        if self.structured_output is not None:
            object.__setattr__(self, "structured_output", dict(self.structured_output))


class LocalModelBackend(Protocol):
    model_id: str

    @property
    def model_digest(self) -> str: ...

    def infer(
        self,
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult: ...


class ReferenceNGramModel:
    """A tiny learned language model used as a portable local execution witness."""

    def __init__(
        self,
        *,
        order: int,
        transitions: Mapping[tuple[str, ...], Mapping[str, int]],
        model_id: str = "skeleton-reference-ngram-v1",
    ) -> None:
        if isinstance(order, bool) or not isinstance(order, int) or not 1 <= order <= 8:
            raise ValueError("order must be in [1, 8]")
        if not model_id.strip():
            raise ValueError("model_id must be non-empty")
        normalized: dict[tuple[str, ...], dict[str, int]] = {}
        for context, counts in transitions.items():
            ctx = tuple(context)
            if len(ctx) > order:
                raise ValueError("transition context exceeds model order")
            clean = {
                str(token): int(count)
                for token, count in counts.items()
                if isinstance(count, int) and not isinstance(count, bool) and count > 0
            }
            if clean:
                normalized[ctx] = clean
        if not normalized:
            raise ValueError("reference model requires learned transitions")
        self.order = order
        self.model_id = model_id.strip()
        self._transitions = normalized
        self._model_digest = _digest(self.to_dict(include_digest=False))

    @classmethod
    def train(
        cls,
        corpus: Sequence[str],
        *,
        order: int = 2,
        model_id: str = "skeleton-reference-ngram-v1",
    ) -> "ReferenceNGramModel":
        if not corpus:
            raise ValueError("training corpus must be non-empty")
        tables: dict[tuple[str, ...], Counter[str]] = {}
        observed = 0
        for document in corpus:
            if not isinstance(document, str) or not document.strip():
                raise ValueError("training documents must be non-empty text")
            tokens = list(_tokenize(document)) + [_EOS]
            prefix: list[str] = []
            for token in tokens:
                for width in range(0, min(order, len(prefix)) + 1):
                    context = tuple(prefix[-width:]) if width else ()
                    tables.setdefault(context, Counter())[token] += 1
                prefix.append(token)
                observed += 1
        if observed == 0:
            raise ValueError("training corpus produced no tokens")
        return cls(
            order=order,
            transitions={key: dict(value) for key, value in tables.items()},
            model_id=model_id,
        )

    @property
    def model_digest(self) -> str:
        return self._model_digest

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        rows = [
            {
                "context": list(context),
                "counts": dict(sorted(counts.items())),
            }
            for context, counts in sorted(
                self._transitions.items(),
                key=lambda item: (len(item[0]), item[0]),
            )
        ]
        payload: dict[str, Any] = {
            "schema_version": 1,
            "kind": "reference_ngram",
            "model_id": self.model_id,
            "order": self.order,
            "transitions": rows,
        }
        if include_digest:
            payload["model_digest"] = self.model_digest
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReferenceNGramModel":
        if payload.get("kind") != "reference_ngram":
            raise ValueError("unsupported local model kind")
        transitions: dict[tuple[str, ...], dict[str, int]] = {}
        for row in payload.get("transitions", []):
            if not isinstance(row, Mapping):
                raise ValueError("invalid transition row")
            transitions[tuple(map(str, row.get("context", [])))] = {
                str(key): int(value)
                for key, value in dict(row.get("counts", {})).items()
            }
        model = cls(
            order=int(payload["order"]),
            transitions=transitions,
            model_id=str(payload["model_id"]),
        )
        claimed = payload.get("model_digest")
        if claimed is not None and claimed != model.model_digest:
            raise ValueError("local model digest mismatch")
        return model

    def _choose(self, context: Sequence[str], rng: random.Random) -> str:
        counts: Mapping[str, int] | None = None
        for width in range(min(self.order, len(context)), -1, -1):
            key = tuple(context[-width:]) if width else ()
            counts = self._transitions.get(key)
            if counts:
                break
        if not counts:
            return _EOS
        ordered = sorted(counts.items())
        total = sum(count for _, count in ordered)
        pick = rng.randrange(total)
        cursor = 0
        for token, count in ordered:
            cursor += count
            if pick < cursor:
                return token
        return ordered[-1][0]

    def infer(
        self,
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        start = time.perf_counter()
        input_tokens = list(_tokenize(request.rendered_input))
        # The portable reference model conditions generation on the immediate
        # user prompt rather than the synthetic role trailer in rendered_input.
        # Full rendered_input still owns usage accounting and identity.
        context = list(_tokenize(request.prompt))
        rng = random.Random(request.seed ^ int(self.model_digest[:16], 16))
        output: list[str] = []
        finish = "length"
        for _ in range(request.max_output_tokens):
            if cancel.is_set():
                raise LocalInferenceCancelled("local generation cancelled")
            token = self._choose(context, rng)
            if token == _EOS:
                finish = "completed"
                break
            output.append(token)
            context.append(token)
            rendered = _detokenize(output)
            if any(rendered.endswith(marker) for marker in request.stop):
                finish = "completed"
                break
        text = _detokenize(output)
        if not text:
            text = "I do not have enough learned local context to answer."
        response_id = "local:" + _digest(
            {
                "model": self.model_digest,
                "request": request.digest,
                "text": text,
            }
        )[:32]
        return LocalInferenceResult(
            text=text,
            model_id=self.model_id,
            model_digest=self.model_digest,
            input_tokens=len(input_tokens),
            output_tokens=len(output),
            finish_reason=finish,
            response_id=response_id,
            latency_ms=(time.perf_counter() - start) * 1000.0,
        )


class CallableLocalModel:
    """Bridge an operator-owned local/open-weight runtime into the same contract."""

    def __init__(
        self,
        *,
        model_id: str,
        model_digest: str,
        runner: Callable[[LocalInferenceRequest, threading.Event], LocalInferenceResult],
    ) -> None:
        if not model_id.strip():
            raise ValueError("model_id must be non-empty")
        if len(model_digest) != 64 or any(ch not in "0123456789abcdef" for ch in model_digest):
            raise ValueError("model_digest must be lowercase sha256")
        self.model_id = model_id.strip()
        self._model_digest = model_digest
        self._runner = runner

    @property
    def model_digest(self) -> str:
        return self._model_digest

    def infer(
        self,
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        result = self._runner(request, cancel)
        if not isinstance(result, LocalInferenceResult):
            raise TypeError("local model runner must return LocalInferenceResult")
        if result.model_id != self.model_id or result.model_digest != self.model_digest:
            raise ValueError("local model runner returned mismatched model identity")
        return result


class LocalInferenceEngine:
    def __init__(self, model: LocalModelBackend, *, cache_size: int = 128) -> None:
        if not hasattr(model, "infer") or not hasattr(model, "model_digest"):
            raise TypeError("model must implement LocalModelBackend")
        if isinstance(cache_size, bool) or not isinstance(cache_size, int) or cache_size < 0:
            raise ValueError("cache_size must be a non-negative integer")
        self.model = model
        self.cache_size = cache_size
        self._cache: OrderedDict[str, LocalInferenceResult] = OrderedDict()
        self._cache_lock = asyncio.Lock()

    def _key(self, request: LocalInferenceRequest) -> str:
        return _digest({"model": self.model.model_digest, "request": request.digest})

    async def generate(self, request: LocalInferenceRequest) -> LocalInferenceResult:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        key = self._key(request)
        if self.cache_size:
            async with self._cache_lock:
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    return replace(cached, cached=True)

        cancel = threading.Event()
        worker = asyncio.create_task(asyncio.to_thread(self.model.infer, request, cancel))
        try:
            # Keep the worker task alive long enough to signal cooperative
            # cancellation into the backend rather than cancelling the Task
            # wrapper before the thread can observe its event.
            result = await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancel.set()
            try:
                await asyncio.wait_for(
                    asyncio.shield(worker),
                    timeout=0.25,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                # Python threads cannot be force-killed. The local backend
                # contract is cooperative; after a bounded grace period detach
                # and consume any eventual exception so the cancelled caller is
                # never held open indefinitely.
                def _consume(done: asyncio.Task[LocalInferenceResult]) -> None:
                    if done.cancelled():
                        return
                    try:
                        done.exception()
                    except Exception:
                        pass

                worker.add_done_callback(_consume)
            raise

        if result.model_digest != self.model.model_digest:
            raise ValueError("local inference result model identity drift")
        if self.cache_size:
            async with self._cache_lock:
                self._cache[key] = result
                self._cache.move_to_end(key)
                while len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
        return result

    async def generate_many(
        self,
        requests: Sequence[LocalInferenceRequest],
    ) -> tuple[LocalInferenceResult, ...]:
        if not requests:
            return ()
        return tuple(await asyncio.gather(*(self.generate(item) for item in requests)))


@dataclass(slots=True)
class _BatchItem:
    request: LocalInferenceRequest
    future: asyncio.Future[LocalInferenceResult]


class LocalInferenceScheduler:
    """Bounded micro-batching queue for local inference requests."""

    def __init__(
        self,
        engine: LocalInferenceEngine,
        *,
        max_batch_size: int = 8,
        batch_window_ms: float = 2.0,
    ) -> None:
        if not 1 <= max_batch_size <= 256:
            raise ValueError("max_batch_size must be in [1, 256]")
        if not 0 <= batch_window_ms <= 1000:
            raise ValueError("batch_window_ms must be in [0, 1000]")
        self.engine = engine
        self.max_batch_size = max_batch_size
        self.batch_window = batch_window_ms / 1000.0
        self._queue: asyncio.Queue[_BatchItem | None] = asyncio.Queue(
            maxsize=max_batch_size * 32
        )
        self._worker: asyncio.Task[None] | None = None
        self._closed = False

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    async def submit(self, request: LocalInferenceRequest) -> LocalInferenceResult:
        if self._closed:
            raise RuntimeError("local inference scheduler is closed")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[LocalInferenceResult] = loop.create_future()
        self._ensure_worker()
        await self._queue.put(_BatchItem(request=request, future=future))
        return await future

    async def _run(self) -> None:
        while True:
            first = await self._queue.get()
            if first is None:
                return
            batch = [first]
            deadline = asyncio.get_running_loop().time() + self.batch_window
            while len(batch) < self.max_batch_size:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    item = await asyncio.wait_for(self._queue.get(), remaining)
                except asyncio.TimeoutError:
                    break
                if item is None:
                    self._closed = True
                    break
                batch.append(item)

            active = [item for item in batch if not item.future.cancelled()]
            if not active:
                continue
            try:
                results = await self.engine.generate_many([item.request for item in active])
            except Exception as exc:
                for item in active:
                    if not item.future.done():
                        item.future.set_exception(exc)
            else:
                for item, result in zip(active, results):
                    if not item.future.done():
                        item.future.set_result(result)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._worker is not None and not self._worker.done():
            await self._queue.put(None)
            await self._worker


_FINISH_MAP = {
    "completed": FinishReason.COMPLETED,
    "tool_calls": FinishReason.TOOL_CALLS,
    "length": FinishReason.LENGTH,
    "cancelled": FinishReason.CANCELLED,
    "deadline": FinishReason.DEADLINE,
}


class LocalModelAdapter(ProviderAdapter):
    """Expose a local model to the existing cognitive runtime without network I/O."""

    provider_id = "local"

    def __init__(self, engine: LocalInferenceEngine, *, default_seed: int = 0) -> None:
        self.engine = engine
        self.model = engine.model.model_id
        self.default_seed = default_seed

    @property
    def available(self) -> bool:
        return True

    def status(self) -> dict[str, Any]:
        payload = super().status()
        payload["network_policy"] = "none"
        payload["execution_mode"] = "local"
        receipt = getattr(self, "artifact_receipt", None)
        if receipt is not None and hasattr(receipt, "as_dict"):
            payload["artifact"] = receipt.as_dict()
        return payload

    @staticmethod
    def _validate_request(request: ProviderRequest, *, model_id: str) -> None:
        if not isinstance(request.instructions, str) or not request.instructions.strip():
            raise ProviderProtocolViolationError(
                "local model instructions must be non-empty"
            )
        if not isinstance(request.prompt, str) or not request.prompt.strip():
            raise ProviderProtocolViolationError(
                "local model prompt must be non-empty"
            )
        if request.model is not None:
            if not isinstance(request.model, str) or request.model.strip() != model_id:
                raise ProviderProtocolViolationError(
                    "local model request identity does not match activated artifact"
                )
        if request.max_output_tokens is not None and (
            isinstance(request.max_output_tokens, bool)
            or not isinstance(request.max_output_tokens, int)
            or request.max_output_tokens <= 0
        ):
            raise ProviderProtocolViolationError(
                "local model max_output_tokens must be positive"
            )
        for message in request.history:
            role = getattr(message, "role", None)
            content = getattr(message, "content", None)
            if (
                role not in {"user", "assistant"}
                or not isinstance(content, str)
                or not content.strip()
            ):
                raise ProviderProtocolViolationError(
                    "local model history contains an invalid message"
                )
        offered = {tool.tool_id for tool in request.tools}
        if len(offered) != len(request.tools):
            raise ProviderProtocolViolationError(
                "local model request contains duplicate offered tools"
            )
        choice = str(request.tool_choice or "auto").strip().lower()
        if choice not in {"none", "auto", "required", "specific"}:
            raise ProviderProtocolViolationError(
                "local model tool_choice is invalid"
            )
        if choice == "required" and not offered:
            raise ProviderProtocolViolationError(
                "required local tool choice has no offered tools"
            )
        if choice == "specific":
            if not request.specific_tool_id or request.specific_tool_id not in offered:
                raise ProviderProtocolViolationError(
                    "specific local tool choice is not offered"
                )
        if request.deadline is not None:
            deadline = request.deadline
            if deadline.tzinfo is None or deadline.utcoffset() is None:
                raise ProviderProtocolViolationError(
                    "local model deadline must be timezone-aware"
                )

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        if not isinstance(request, ProviderRequest):
            raise TypeError("request must be ProviderRequest")
        self._validate_request(request, model_id=self.model)
        max_tokens = request.max_output_tokens or 256
        seed_material = "|".join(
            item or ""
            for item in (
                request.operation_id,
                request.execution_id,
                request.turn_id,
                request.prompt,
            )
        )
        derived_seed = int(
            hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16],
            16,
        )
        local_request = LocalInferenceRequest(
            prompt=request.prompt,
            instructions=request.instructions,
            history=tuple((item.role, item.content) for item in request.history),
            max_output_tokens=max_tokens,
            seed=self.default_seed ^ derived_seed,
            tools=tuple(item.as_dict() for item in request.tools),
        )

        if request.deadline is None:
            result = await self.engine.generate(local_request)
        else:
            remaining = (
                request.deadline.astimezone(timezone.utc)
                - datetime.now(timezone.utc)
            ).total_seconds()
            if remaining <= 0:
                raise ProviderInvocationError(
                    "local model deadline exceeded"
                )
            try:
                result = await asyncio.wait_for(
                    self.engine.generate(local_request),
                    timeout=remaining,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderInvocationError(
                    "local model deadline exceeded"
                ) from exc

        offered = {tool.tool_id for tool in request.tools}
        returned = {item.tool_id for item in result.tool_calls}
        if returned - offered:
            raise ProviderProtocolViolationError(
                "local model returned an unoffered tool call"
            )
        choice = str(request.tool_choice or "auto").strip().lower()
        if choice == "none" and result.tool_calls:
            raise ProviderProtocolViolationError(
                "local model returned tool calls when tools were disabled"
            )
        if choice == "required" and not result.tool_calls:
            raise ProviderProtocolViolationError(
                "local model omitted a required tool call"
            )
        if choice == "specific" and any(
            item.tool_id != request.specific_tool_id
            for item in result.tool_calls
        ):
            raise ProviderProtocolViolationError(
                "local model returned a non-selected tool"
            )
        if (
            request.structured_output_schema is not None
            and result.structured_output is None
        ):
            raise ProviderProtocolViolationError(
                "local model omitted required structured output"
            )

        tool_calls = tuple(
            ProviderToolCall(
                call_id=item.call_id,
                tool_id=item.tool_id,
                arguments=dict(item.arguments),
            )
            for item in result.tool_calls
        )
        total = result.input_tokens + result.output_tokens
        return ProviderResponse(
            text=result.text,
            provider=self.provider_id,
            model=result.model_id,
            request_id="local-request:" + local_request.digest[:24],
            response_id=result.response_id,
            structured_output=(
                dict(result.structured_output)
                if result.structured_output is not None
                else None
            ),
            tool_calls=tool_calls,
            finish_reason=_FINISH_MAP[result.finish_reason],
            usage=ProviderUsage(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                total_tokens=total,
                estimated_cost="0",
                billed_cost="0",
                currency="USD",
                usage_source="local_model",
            ),
            latency_ms=result.latency_ms,
            data_class=request.data_class,
            context_id=request.context_id,
            context_digest=request.context_digest,
            context_source_snapshot=request.context_source_snapshot,
            context_compiler_version=request.context_compiler_version,
        )

