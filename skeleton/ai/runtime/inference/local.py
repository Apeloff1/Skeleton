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
import hashlib
import json
import math
import os
import random
import re
import secrets
import threading
import time
from collections import Counter, OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from skeleton.compat.datetime_utc import UTC
from datetime import datetime
from typing import Any, Protocol

from skeleton.provider_runtime import (
    ProviderAdapter,
    ProviderPolicyError,
    ProviderProtocolViolationError,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
    _provider_tool_choice_payload,
    _provider_tool_definitions,
    _validate_request,
)
from skeleton.providers.contract import FinishReason, ProviderToolCall, ProviderUsage
from skeleton.skills.tool_contract import ToolContractError, validate_json_value

from .adaptive_serving import AdaptiveServingController, ServingResources

_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_EOS = "<|eos|>"
_RESOURCE_SAMPLE_LOCK = threading.Lock()
_RESOURCE_CPU_SAMPLE: tuple[float, int, float | None] | None = None


class LocalInferenceCancelled(RuntimeError):
    """Cooperative local inference cancellation was observed."""


class LocalInferenceOverloaded(ProviderUnavailableError):
    """The configured local worker and waiting capacity is already reserved."""


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
        # Own nested JSON as well as the outer mapping. A model/caller must
        # not be able to change a previously admitted tool call by aliasing.
        object.__setattr__(self, "arguments", json.loads(encoded))


@dataclass(frozen=True, slots=True)
class LocalInferenceRequest:
    prompt: str
    instructions: str = ""
    history: tuple[tuple[str, str], ...] = ()
    max_output_tokens: int = 256
    seed: int = 0
    stop: tuple[str, ...] = ()
    tools: tuple[Mapping[str, Any], ...] = ()
    structured_output_schema: Mapping[str, Any] | None = None
    context_digest: str | None = None
    tool_choice: str = "auto"
    specific_tool_id: str | None = None
    temperature: float = 1.0
    top_k: int = 0
    top_p: float = 1.0
    min_p: float = 0.0
    repetition_penalty: float = 1.0

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
        if len(self.stop) > 16 or any(
            len(marker) > 256 or any(0xD800 <= ord(char) <= 0xDFFF for char in marker) for marker in self.stop
        ):
            raise ValueError("stop supports at most 16 valid Unicode markers of 256 characters")
        tools = tuple(json.loads(_stable_json(dict(item))) for item in self.tools)
        if len(tools) > 256:
            raise ValueError("local inference supports at most 256 offered tools")
        if len(_stable_json(tools).encode("utf-8")) > 512 * 1024:
            raise ValueError("local inference tools exceed size limit")
        ids = [item.get("tool_id") for item in tools]
        if any(not isinstance(tool_id, str) or not tool_id.strip() for tool_id in ids) or len(ids) != len(
            set(ids)
        ):
            raise ValueError("local tools must have unique non-empty string tool_id values")
        if self.tool_choice not in {"none", "auto", "required", "specific"}:
            raise ValueError("invalid local tool_choice")
        offered = {item.get("tool_id") for item in tools}
        if self.tool_choice in {"required", "specific"} and not offered:
            raise ValueError("local tool choice requires offered tools")
        if self.tool_choice == "specific":
            if not isinstance(self.specific_tool_id, str) or self.specific_tool_id not in offered:
                raise ValueError("specific local tool choice must reference an offered tool")
        elif self.specific_tool_id is not None:
            raise ValueError("specific_tool_id requires specific local tool choice")
        if self.tool_choice == "none":
            tools = ()
        elif self.tool_choice == "specific":
            tools = tuple(item for item in tools if item["tool_id"] == self.specific_tool_id)
        object.__setattr__(self, "tools", tools)
        if self.structured_output_schema is not None:
            if not isinstance(self.structured_output_schema, Mapping):
                raise TypeError("structured_output_schema must be an object")
            schema = dict(self.structured_output_schema)
            encoded = _stable_json(schema)
            if len(encoded.encode("utf-8")) > 512 * 1024:
                raise ValueError("structured_output_schema exceeds size limit")
            object.__setattr__(self, "structured_output_schema", json.loads(encoded))
        if self.context_digest is not None and (
            len(self.context_digest) != 64 or any(ch not in "0123456789abcdef" for ch in self.context_digest)
        ):
            raise ValueError("context_digest must be lowercase sha256")
        if (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not math.isfinite(float(self.temperature))
            or not 0.0 <= float(self.temperature) <= 100.0
        ):
            raise ValueError("temperature outside supported range")
        if isinstance(self.top_k, bool) or not isinstance(self.top_k, int) or self.top_k < 0:
            raise ValueError("top_k must be a non-negative integer")
        if (
            isinstance(self.top_p, bool)
            or not isinstance(self.top_p, (int, float))
            or not math.isfinite(float(self.top_p))
            or not 0.0 < float(self.top_p) <= 1.0
        ):
            raise ValueError("top_p outside supported range")
        if (
            isinstance(self.min_p, bool)
            or not isinstance(self.min_p, (int, float))
            or not math.isfinite(float(self.min_p))
            or not 0.0 <= float(self.min_p) <= 1.0
        ):
            raise ValueError("min_p outside supported range")
        if (
            isinstance(self.repetition_penalty, bool)
            or not isinstance(self.repetition_penalty, (int, float))
            or not math.isfinite(float(self.repetition_penalty))
            or not 0.01 <= float(self.repetition_penalty) <= 100.0
        ):
            raise ValueError("repetition_penalty outside supported range")
        object.__setattr__(self, "temperature", float(self.temperature))
        object.__setattr__(self, "top_p", float(self.top_p))
        object.__setattr__(self, "min_p", float(self.min_p))
        object.__setattr__(self, "repetition_penalty", float(self.repetition_penalty))

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
                "structured_output_schema": self.structured_output_schema,
                "context_digest": self.context_digest,
                "tool_choice": self.tool_choice,
                "specific_tool_id": self.specific_tool_id,
            }
            | (
                {"temperature": self.temperature} if self.temperature != 1.0 else {}
            )
            | ({"top_k": self.top_k} if self.top_k else {})
            | ({"top_p": self.top_p} if self.top_p != 1.0 else {})
            | ({"min_p": self.min_p} if self.min_p != 0.0 else {})
            | (
                {"repetition_penalty": self.repetition_penalty}
                if self.repetition_penalty != 1.0
                else {}
            )
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
    execution_receipt_digest: str | None = None
    usage_source: str = "local_model"

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("model_id must be non-empty")
        if self.usage_source not in {"local_model", "local_model_estimate"}:
            raise ValueError("invalid local inference usage_source")
        if self.text is not None and (
            not isinstance(self.text, str) or len(self.text.encode("utf-8")) > 4 * 1024 * 1024
        ):
            raise ValueError("local inference text must fit the 4 MiB output bound")
        if self.execution_receipt_digest is not None and (
            not isinstance(self.execution_receipt_digest, str)
            or len(self.execution_receipt_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.execution_receipt_digest)
        ):
            raise ValueError("execution_receipt_digest must be lowercase sha256")

        if len(self.model_digest) != 64 or any(ch not in "0123456789abcdef" for ch in self.model_digest):
            raise ValueError("model_digest must be lowercase sha256")
        if (
            isinstance(self.input_tokens, bool)
            or isinstance(self.output_tokens, bool)
            or not isinstance(self.input_tokens, int)
            or not isinstance(self.output_tokens, int)
            or self.input_tokens < 0
            or self.output_tokens < 0
        ):
            raise ValueError("token counts must be non-negative integers")
        if self.finish_reason not in {
            "completed",
            "tool_calls",
            "length",
            "cancelled",
            "deadline",
        }:
            raise ValueError("invalid local finish_reason")
        supplied_calls = tuple(self.tool_calls)
        if len(supplied_calls) > 256:
            raise ValueError("local inference result exceeds tool-call protocol bound")
        if any(not isinstance(call, LocalToolCall) for call in supplied_calls):
            raise TypeError("tool_calls must contain LocalToolCall values")
        calls = tuple(replace(call) for call in supplied_calls)
        call_ids = [call.call_id for call in calls]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("local tool call ids must be unique")
        if self.finish_reason == "tool_calls" and not calls:
            raise ValueError("tool_calls finish reason requires tool calls")
        if calls and self.finish_reason != "tool_calls":
            raise ValueError("tool calls require tool_calls finish reason")
        if self.text is None and not calls and self.structured_output is None:
            raise ValueError("local inference result must contain output")
        object.__setattr__(self, "tool_calls", calls)
        if self.structured_output is not None:
            encoded = _stable_json(dict(self.structured_output))
            if len(encoded.encode("utf-8")) > 4 * 1024 * 1024:
                raise ValueError("local structured output exceeds 4 MiB output bound")
            object.__setattr__(self, "structured_output", json.loads(encoded))
        if self.latency_ms is not None:
            latency = float(self.latency_ms)
            if not math.isfinite(latency) or latency < 0:
                raise ValueError("latency_ms must be finite and non-negative")
            object.__setattr__(self, "latency_ms", latency)


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

    model_family = "reference_ngram"
    protocol_capabilities = ("text-generation",)
    tokenizer_kind = "reference_tokens"

    @staticmethod
    def count_input_tokens(request: LocalInferenceRequest) -> int:
        return len(_tokenize(request.rendered_input))

    def assert_identity(self) -> None:
        if _digest(self.to_dict(include_digest=False)) != self.model_digest:
            raise ValueError("reference model content changed behind its digest")

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
    ) -> ReferenceNGramModel:
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
                for width in range(min(order, len(prefix)) + 1):
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
    def from_dict(cls, payload: Mapping[str, Any]) -> ReferenceNGramModel:
        if not isinstance(payload, Mapping):
            raise TypeError("local model payload must be a mapping")
        allowed_top_level = {
            "schema_version",
            "kind",
            "model_id",
            "order",
            "transitions",
            "model_digest",
        }
        unknown_top_level = set(payload) - allowed_top_level
        if unknown_top_level:
            raise ValueError(
                "unsupported local model artifact key(s): " + ", ".join(sorted(map(str, unknown_top_level)))
            )
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported local model schema_version")
        if payload.get("kind") != "reference_ngram":
            raise ValueError("unsupported local model kind")

        order = payload.get("order")
        if isinstance(order, bool) or not isinstance(order, int) or not 1 <= order <= 8:
            raise ValueError("order must be an integer in [1, 8]")
        model_id = payload.get("model_id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("model_id must be non-empty text")

        rows = payload.get("transitions")
        if not isinstance(rows, list) or not rows:
            raise ValueError("transitions must be a non-empty list")
        transitions: dict[tuple[str, ...], dict[str, int]] = {}
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise ValueError(  # noqa: TRY004 -- artifact validation compatibility
                    f"transition row {index} must be an object"
                )
            unknown_row_keys = set(row) - {"context", "counts"}
            if unknown_row_keys:
                raise ValueError(
                    f"transition row {index} contains unsupported key(s): "
                    + ", ".join(sorted(map(str, unknown_row_keys)))
                )
            context_raw = row.get("context")
            counts_raw = row.get("counts")
            if not isinstance(context_raw, list) or any(not isinstance(token, str) for token in context_raw):
                raise ValueError(f"transition row {index} context must contain only strings")
            context = tuple(context_raw)
            if len(context) > order:
                raise ValueError(f"transition row {index} context exceeds model order")
            if context in transitions:
                raise ValueError(f"duplicate transition context at row {index}")
            if not isinstance(counts_raw, Mapping) or not counts_raw:
                raise ValueError(f"transition row {index} counts must be a non-empty object")
            counts: dict[str, int] = {}
            for token, value in counts_raw.items():
                if not isinstance(token, str) or not token:
                    raise ValueError(f"transition row {index} token ids must be non-empty strings")
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    raise ValueError(f"transition row {index} counts must be positive integers")
                counts[token] = value
            transitions[context] = counts

        model = cls(
            order=order,
            transitions=transitions,
            model_id=model_id,
        )
        claimed = payload.get("model_digest")
        if claimed is not None:
            if (
                not isinstance(claimed, str)
                or len(claimed) != 64
                or any(ch not in "0123456789abcdef" for ch in claimed)
            ):
                raise ValueError("model_digest must be lowercase sha256")
            if claimed != model.model_digest:
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
        response_id = (
            "local:"
            + _digest(
                {
                    "model": self.model_digest,
                    "request": request.digest,
                    "text": text,
                }
            )[:32]
        )
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
        protocol_capabilities: Sequence[str] = ("text-generation",),
    ) -> None:
        if not model_id.strip():
            raise ValueError("model_id must be non-empty")
        if len(model_digest) != 64 or any(ch not in "0123456789abcdef" for ch in model_digest):
            raise ValueError("model_digest must be lowercase sha256")
        self.model_id = model_id.strip()
        self._model_digest = model_digest
        self._runner = runner
        capabilities = tuple(dict.fromkeys(protocol_capabilities))
        if not capabilities or set(capabilities) - {"text-generation", "tool-calls", "structured-output"}:
            raise ValueError("callable local model protocol capabilities are invalid")
        self.protocol_capabilities = capabilities
        self.model_family = "operator_callable"

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


@dataclass(slots=True)
class _ServingTicket:
    sequence: int
    work_class: str
    scope_id: str
    preemption_scope_id: str
    enqueued_at: float
    deadline: float
    cancel: threading.Event
    retired: str | None = None
    started_at: float | None = None


@dataclass(frozen=True, slots=True)
class _CachedInference:
    result: LocalInferenceResult
    created_at: float
    expires_at: float
    size_bytes: int


def sample_serving_resources() -> ServingResources:
    """Best-effort bounded local samples; missing host signals stay unknown."""
    global _RESOURCE_CPU_SAMPLE  # disposable process-local measurement only
    memory_used = None
    available = None
    rss = None
    cpu = None
    sources: list[str] = []

    def read(path: str) -> str:
        with open(path, encoding="ascii") as handle:
            return handle.read(16_384).strip()

    host_cpus = float(os.cpu_count() or 1)
    cpus = host_cpus
    try:
        quota, period = read("/sys/fs/cgroup/cpu.max").split()
        if quota != "max" and float(period) > 0:
            cpus = min(cpus, max(0.01, float(quota) / float(period)))
    except (OSError, ValueError):
        pass
    try:
        cpu = max(0.0, os.getloadavg()[0] / host_cpus)
        sources.append("host_load")
    except (AttributeError, OSError, ValueError):
        pass
    try:
        usage = next(
            int(line.split()[1]) for line in read("/sys/fs/cgroup/cpu.stat").splitlines()
            if line.startswith("usage_usec ")
        )
        now = time.monotonic()
        with _RESOURCE_SAMPLE_LOCK:
            previous = _RESOURCE_CPU_SAMPLE
            if previous is not None and now - previous[0] >= 0.25:
                elapsed = now - previous[0]
                cpu = max(0.0, (usage - previous[1]) / 1_000_000.0 / elapsed / cpus)
                _RESOURCE_CPU_SAMPLE = (now, usage, cpu)
            elif previous is None:
                _RESOURCE_CPU_SAMPLE = (now, usage, cpu)
            else:
                cpu = previous[2]
        sources.append("cgroup_cpu")
    except (OSError, ValueError, IndexError, StopIteration):
        pass
    try:
        values = {}
        for line in read("/proc/meminfo").splitlines():
            name, _, value = line.partition(":")
            if name in {"MemTotal", "MemAvailable"}:
                values[name] = int(value.strip().split()[0]) * 1024
        total = values.get("MemTotal", 0)
        if total > 0 and "MemAvailable" in values:
            available = max(0, values["MemAvailable"])
            memory_used = min(1.0, max(0.0, 1.0 - available / total))
            sources.append("host_memory")
    except (OSError, ValueError, IndexError):
        pass
    try:
        maximum = read("/sys/fs/cgroup/memory.max")
        current = int(read("/sys/fs/cgroup/memory.current"))
        if maximum != "max" and int(maximum) > 0:
            total = int(maximum)
            remaining = max(0, total - current)
            fraction = min(1.0, max(0.0, current / total))
            available = remaining if available is None else min(available, remaining)
            memory_used = fraction if memory_used is None else max(memory_used, fraction)
            sources.append("cgroup_memory")
    except (OSError, ValueError):
        pass
    try:
        rss = int(read("/proc/self/statm").split()[1]) * int(os.sysconf("SC_PAGE_SIZE"))
    except (OSError, AttributeError, ValueError, IndexError):
        pass
    return ServingResources(memory_used, cpu, rss, available, ",".join(sources) or "unavailable")


class LocalInferenceEngine:
    def __init__(
        self,
        model: LocalModelBackend,
        *,
        cache_size: int = 128,
        max_concurrency: int = 1,
        max_batch_size: int = 256,
        max_queue_size: int = 256,
    ) -> None:
        if not hasattr(model, "infer") or not hasattr(model, "model_digest"):
            raise TypeError("model must implement LocalModelBackend")
        if isinstance(cache_size, bool) or not isinstance(cache_size, int) or cache_size < 0:
            raise ValueError("cache_size must be a non-negative integer")
        if (
            isinstance(max_queue_size, bool)
            or not isinstance(max_queue_size, int)
            or not 0 <= max_queue_size <= 65536
        ):
            raise ValueError("max_queue_size must be an integer in [0, 65536]")
        for name, value, upper in (
            ("max_concurrency", max_concurrency, 32),
            ("max_batch_size", max_batch_size, 4096),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper:
                raise ValueError(f"{name} must be between 1 and {upper}")
        self.model = model
        self.cache_size = cache_size
        self.max_concurrency = max_concurrency
        self.max_batch_size = max_batch_size
        self.max_queue_size = max_queue_size
        self._execution_slots = threading.BoundedSemaphore(max_concurrency)
        self._cache: OrderedDict[str, _CachedInference] = OrderedDict()
        # Every critical section is synchronous. A thread lock, unlike an
        # asyncio lock, has one authority across desktop/event-loop lifetimes.
        self._cache_lock = threading.Lock()
        self._capacity_lock = threading.Lock()
        self._serving = AdaptiveServingController(max_concurrency)
        self._tickets: OrderedDict[int, _ServingTicket] = OrderedDict()
        self._interactive_tickets: OrderedDict[int, _ServingTicket] = OrderedDict()
        self._background_tickets: OrderedDict[int, _ServingTicket] = OrderedDict()
        self._running: dict[int, _ServingTicket] = {}
        self._next_ticket = 0
        self._draining = False
        self._preemptions = 0
        self._queue_expired = 0
        self._cache_bytes = 0
        self._cache_evictions = 0
        self._cache_expirations = 0
        self._identity_invalidations = 0
        self._cache_identity: str | None = None
        self._singleflight: dict[tuple[str, asyncio.AbstractEventLoop], asyncio.Future[LocalInferenceResult]] = {}
        self._singleflight_hits = 0
        self._singleflight_waiters = 0
        self._cache_epoch = 0
        self._active = 0
        self._queued = 0
        self._completed = 0
        self._failed = 0
        self._cancelled = 0
        self._overloaded = 0
        self._cache_hits = 0

    def _sample_pressure_locked(self, now: float) -> None:
        if self._serving.sample_due(now):
            self._serving.update(sample_serving_resources(), now=now, queued=self._queued)

    def _effective_cache_limit_locked(self) -> int:
        maximum = self._serving.policy.cache_max_bytes
        if not self._serving.policy.enabled:
            return maximum
        if self._serving.level == "critical":
            return 0
        return maximum // 2 if self._serving.level == "elevated" else maximum

    def snapshot(self) -> dict[str, Any]:
        """Return bounded operational counts without prompts or model output."""
        with self._capacity_lock:
            self._sample_pressure_locked(time.monotonic())
            background_active = sum(item.work_class == "background" for item in self._running.values())
            background_queued = len(self._background_tickets)
            snapshot = {
                "active": self._active,
                "queued": self._queued,
                "completed": self._completed,
                "failed": self._failed,
                "cancelled": self._cancelled,
                "overloaded": self._overloaded,
                "cache_hits": self._cache_hits,
                "preemptions": self._preemptions,
                "queue_expired": self._queue_expired,
            }
            cache_limit = self._effective_cache_limit_locked()
            serving = {
                "policy": self._serving.policy.as_dict(),
                "capacity": {
                    "operator_max_concurrency": self.max_concurrency,
                    "effective_concurrency": self._serving.effective_concurrency,
                    "background_limit": self._serving.background_limit,
                    "active_interactive": self._active - background_active,
                    "active_background": background_active,
                    "queued_interactive": self._queued - background_queued,
                    "queued_background": background_queued,
                },
                "pressure": self._serving.pressure_snapshot(),
                "draining": self._draining,
            }
        with self._cache_lock:
            snapshot["cache_entries"] = len(self._cache)
            serving["cache"] = {
                "entries": len(self._cache),
                "bytes": self._cache_bytes,
                "max_bytes": serving["policy"]["cache_max_bytes"],
                "effective_max_bytes": cache_limit,
                "ttl_seconds": serving["policy"]["cache_ttl_seconds"],
                "evictions": self._cache_evictions,
                "expirations": self._cache_expirations,
                "identity_invalidations": self._identity_invalidations,
                "singleflight_active": len(self._singleflight),
                "singleflight_hits": self._singleflight_hits,
                "singleflight_waiters": self._singleflight_waiters,
            }
        snapshot["serving"] = serving
        return snapshot

    def configure_serving(self, policy: Mapping[str, Any]) -> dict[str, Any]:
        """Change derived serving policy without changing activated identity."""
        with self._capacity_lock:
            self._serving.configure(policy, time.monotonic())
        self._trim_cache()
        return self.snapshot()

    def maintain(self, action: str = "trim_cache") -> dict[str, Any]:
        """Apply bounded maintenance to disposable state, never model weights."""
        if action not in {"trim_cache", "clear_cache", "drain", "resume"}:
            raise ValueError("unknown local inference maintenance action")
        if action == "clear_cache":
            with self._cache_lock:
                self._cache_evictions += len(self._cache)
                self._cache.clear()
                self._cache_bytes = 0
                self._cache_epoch += 1
        elif action == "trim_cache":
            self._trim_cache()
        else:
            with self._capacity_lock:
                self._draining = action == "drain"
                if self._draining:
                    for ticket in self._tickets.values():
                        ticket.retired = "draining"
                    self._queued -= len(self._tickets)
                    self._tickets.clear()
                    self._interactive_tickets.clear()
                    self._background_tickets.clear()
                    # Active workers keep their reservations and physical
                    # ownership until their own finally block completes.
        return self.snapshot()

    def _reserve(
        self,
        work_class: str,
        scope_id: str,
        preemption_scope_id: str,
        deadline: float | None,
        cancel: threading.Event,
    ) -> _ServingTicket:
        now = time.monotonic()
        with self._capacity_lock:
            self._sample_pressure_locked(now)
            if self._draining:
                self._overloaded += 1
                raise LocalInferenceOverloaded("local inference is draining")
            queue_deadline = now + self._serving.policy.max_queue_wait_seconds
            if deadline is not None:
                queue_deadline = min(queue_deadline, deadline)
            if queue_deadline <= now:
                self._queue_expired += 1
                raise LocalInferenceCancelled("local inference queue deadline exceeded")
            if work_class == "background" and self._serving.policy.background_max_concurrency == 0:
                self._overloaded += 1
                raise LocalInferenceOverloaded("local background inference is paused")
            background_queue_limit = max(1, self.max_queue_size * 3 // 4)
            if work_class == "background" and len(self._background_tickets) >= background_queue_limit:
                self._overloaded += 1
                raise LocalInferenceOverloaded("local background waiting capacity is full")
            full = self._active + self._queued >= self.max_concurrency + self.max_queue_size
            if full and work_class == "interactive":
                # Replace queued work only inside the same authority scope.
                victim = next((item for item in reversed(self._background_tickets.values()) if (
                    item.preemption_scope_id == preemption_scope_id
                )), None)
                if victim is not None:
                    victim.retired = "preempted"
                    del self._tickets[victim.sequence]
                    del self._background_tickets[victim.sequence]
                    self._queued -= 1
                    self._preemptions += 1
                    full = False
            if full:
                self._overloaded += 1
                raise LocalInferenceOverloaded("local inference waiting capacity is full")
            self._next_ticket += 1
            ticket = _ServingTicket(
                self._next_ticket, work_class, scope_id, preemption_scope_id,
                now, queue_deadline, cancel,
            )
            self._tickets[ticket.sequence] = ticket
            priority_queue = self._interactive_tickets if work_class == "interactive" else self._background_tickets
            priority_queue[ticket.sequence] = ticket
            self._queued += 1
            if work_class == "interactive" and self._active >= self._serving.effective_concurrency:
                victim = next((item for item in self._running.values() if (
                    item.work_class == "background"
                    and item.preemption_scope_id == preemption_scope_id
                    and not item.cancel.is_set()
                )), None)
                if victim is not None:
                    victim.cancel.set()
                    self._preemptions += 1
            return ticket

    def _infer_admitted(
        self,
        request: LocalInferenceRequest,
        cancel: threading.Event,
        started: threading.Event,
        ticket: _ServingTicket,
    ) -> LocalInferenceResult:
        started.set()
        failed = False
        try:
            if cancel.is_set():
                raise LocalInferenceCancelled("local inference cancelled before execution")
            result = self.model.infer(request, cancel)
            if not isinstance(result, LocalInferenceResult):
                raise TypeError("local backend must return LocalInferenceResult")
            if cancel.is_set():
                raise LocalInferenceCancelled("local inference cancelled during execution")
            with self._capacity_lock:
                self._completed += 1
            return result
        except LocalInferenceCancelled:
            with self._capacity_lock:
                self._cancelled += 1
            raise
        except BaseException:
            failed = True
            with self._capacity_lock:
                self._failed += 1
            raise
        finally:
            with self._capacity_lock:
                self._active -= 1
                self._running.pop(ticket.sequence, None)
                now = time.monotonic()
                admitted_at = ticket.started_at if ticket.started_at is not None else now
                self._serving.observe(
                    elapsed_ms=(now - admitted_at) * 1000.0,
                    queue_wait_ms=(admitted_at - ticket.enqueued_at) * 1000.0,
                    failed=failed,
                )
            self._execution_slots.release()

    async def _acquire_execution_slot(self, ticket: _ServingTicket) -> None:
        # Keep waiting requests off the process-wide default executor. The
        # same thread semaphore still fences capacity across event loops.
        try:
            while True:
                with self._capacity_lock:
                    now = time.monotonic()
                    self._sample_pressure_locked(now)
                    if ticket.retired is not None:
                        raise LocalInferenceCancelled("local inference queue " + ticket.retired)
                    if now >= ticket.deadline:
                        self._tickets.pop(ticket.sequence, None)
                        self._interactive_tickets.pop(ticket.sequence, None)
                        self._background_tickets.pop(ticket.sequence, None)
                        self._queued -= 1
                        self._queue_expired += 1
                        ticket.retired = "deadline exceeded"
                        raise LocalInferenceCancelled("local inference queue deadline exceeded")
                    interactive = next(iter(self._interactive_tickets.values()), None)
                    head = interactive or next(iter(self._tickets.values()), None)
                    background_active = sum(item.work_class == "background" for item in self._running.values())
                    allowed = (
                        head is ticket
                        and self._active < self._serving.effective_concurrency
                        and (ticket.work_class != "background" or background_active < self._serving.background_limit)
                    )
                    if allowed and self._execution_slots.acquire(blocking=False):
                        del self._tickets[ticket.sequence]
                        self._interactive_tickets.pop(ticket.sequence, None)
                        self._background_tickets.pop(ticket.sequence, None)
                        self._queued -= 1
                        self._active += 1
                        ticket.started_at = now
                        self._running[ticket.sequence] = ticket
                        return
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            with self._capacity_lock:
                if self._tickets.pop(ticket.sequence, None) is not None:
                    self._queued -= 1
                self._interactive_tickets.pop(ticket.sequence, None)
                self._background_tickets.pop(ticket.sequence, None)
                self._cancelled += 1
            raise
        except LocalInferenceCancelled:
            with self._capacity_lock:
                self._cancelled += 1
            raise

    @staticmethod
    async def _await_worker(worker: asyncio.Task[Any], cancel: threading.Event) -> Any:
        """Keep ownership of an OS worker until it actually leaves its boundary."""
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancel.set()
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    continue
                except Exception:  # noqa: BLE001 -- wait for any backend failure to quiesce
                    break
            if worker.done() and not worker.cancelled():
                # Retrieve a failed backend outcome without replacing the
                # caller's cancellation after actual worker quiescence.
                worker.exception()
            raise

    def _assert_cached_admitted(
        self,
        check: Callable[[], Any],
        ticket: _ServingTicket,
        started: threading.Event,
    ) -> None:
        started.set()
        try:
            if ticket.cancel.is_set():
                raise LocalInferenceCancelled("local cache identity admission cancelled")
            check()
            if ticket.cancel.is_set():
                raise LocalInferenceCancelled("local cache identity admission cancelled")
        except LocalInferenceCancelled:
            with self._capacity_lock:
                self._cancelled += 1
            raise
        except BaseException:
            with self._capacity_lock:
                self._failed += 1
            raise
        finally:
            with self._capacity_lock:
                self._active -= 1
                self._running.pop(ticket.sequence, None)
            self._execution_slots.release()

    async def _admit_cached_identity(
        self,
        check: Callable[[], Any],
        *,
        work_class: str,
        scope_id: str,
        preemption_scope_id: str,
        deadline: float | None,
    ) -> None:
        cancel = threading.Event()
        ticket = self._reserve(work_class, scope_id, preemption_scope_id, deadline, cancel)
        await self._acquire_execution_slot(ticket)
        started = threading.Event()
        timeout = None
        try:
            worker = asyncio.create_task(asyncio.to_thread(self._assert_cached_admitted, check, ticket, started))
            if deadline is not None:
                timeout = asyncio.get_running_loop().call_later(
                    max(0.0, deadline - time.monotonic()), cancel.set,
                )
            await self._await_worker(worker, cancel)
        except BaseException:
            if not started.is_set():
                with self._capacity_lock:
                    self._active -= 1
                    self._running.pop(ticket.sequence, None)
                    self._failed += 1
                self._execution_slots.release()
            raise
        finally:
            if timeout is not None:
                timeout.cancel()
        if deadline is not None and time.monotonic() >= deadline:
            raise LocalInferenceCancelled("local cache identity admission deadline exceeded")

    def _model_identity(self) -> str:
        # Native runtime identities include tokenizer, architecture and policy.
        # Read before cache lookup so model drift invalidates old cached output.
        runtime_digest = getattr(self.model, "runtime_digest", None)
        if runtime_digest is not None and (
            not isinstance(runtime_digest, str)
            or len(runtime_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in runtime_digest)
        ):
            raise ValueError("local runtime digest must be lowercase sha256")
        identity = {
            "model": self.model.model_digest,
            "runtime": runtime_digest,
        }
        profile = getattr(self.model, "execution_profile_digest", None)
        if profile is not None:
            if (
                not isinstance(profile, str)
                or len(profile) != 64
                or any(ch not in "0123456789abcdef" for ch in profile)
            ):
                raise ValueError("execution profile digest must be lowercase sha256")
            identity["execution_profile"] = profile
        return _digest(identity)

    def _key(self, request: LocalInferenceRequest, scope_id: str = "local") -> str:
        return _digest({"identity": self._model_identity(), "request": request.digest, "scope": scope_id})

    def _trim_cache(self) -> None:
        with self._capacity_lock:
            self._sample_pressure_locked(time.monotonic())
            policy = self._serving.policy
            byte_limit = self._effective_cache_limit_locked()
        now = time.monotonic()
        with self._cache_lock:
            for key, item in tuple(self._cache.items()):
                if now >= min(item.expires_at, item.created_at + policy.cache_ttl_seconds):
                    self._cache_bytes -= item.size_bytes
                    del self._cache[key]
                    self._cache_expirations += 1
            while self._cache and (
                len(self._cache) > self.cache_size or self._cache_bytes > byte_limit
            ):
                _, item = self._cache.popitem(last=False)
                self._cache_bytes -= item.size_bytes
                self._cache_evictions += 1

    @staticmethod
    def _cache_size_bytes(result: LocalInferenceResult, maximum: int) -> int:
        # Avoid one potentially large serialization of a whole tool result.
        size = 1024 + len((result.text or "").encode("utf-8"))
        if result.structured_output is not None:
            size += len(_stable_json(dict(result.structured_output)).encode("utf-8"))
        for call in result.tool_calls:
            size += 256 + len(call.call_id.encode("utf-8")) + len(call.tool_id.encode("utf-8"))
            size += len(_stable_json(dict(call.arguments)).encode("utf-8"))
            if size > maximum:
                break
        return size

    async def generate(
        self,
        request: LocalInferenceRequest,
        *,
        work_class: str = "interactive",
        scope_id: str | None = None,
        preemption_scope_id: str | None = None,
        deadline: float | None = None,
    ) -> LocalInferenceResult:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        if work_class not in {"interactive", "background"}:
            raise ValueError("local work_class must be interactive or background")
        for name, value in (("scope_id", scope_id), ("preemption_scope_id", preemption_scope_id)):
            if value is not None and (not isinstance(value, str) or not value or len(value) > 512):
                raise ValueError(f"{name} must be a non-empty bounded string")
        if deadline is not None and (
            isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or not math.isfinite(deadline)
        ):
            raise ValueError("local inference deadline must be finite monotonic seconds")
        if deadline is not None and deadline <= time.monotonic():
            raise LocalInferenceCancelled("local inference deadline exceeded")
        with self._capacity_lock:
            if self._draining:
                self._overloaded += 1
                raise LocalInferenceOverloaded("local inference is draining")
            follower_wait_limit = self._serving.policy.max_queue_wait_seconds
        scope = scope_id or "local"
        preemption_scope = preemption_scope_id or scope
        identity = self._model_identity()
        key = self._key(request, scope)
        self._trim_cache()
        with self._cache_lock:
            if self._cache_identity != identity:
                if self._cache_identity is not None:
                    self._identity_invalidations += 1
                self._cache.clear()
                self._cache_bytes = 0
                self._cache_identity = identity
                self._cache_epoch += 1
            epoch = self._cache_epoch
        if self.cache_size:
            with self._cache_lock:
                cached = self._cache.get(key)
            if cached is not None:
                admit_cached = getattr(self.model, "assert_identity", None)
                if callable(admit_cached):
                    await self._admit_cached_identity(
                        admit_cached, work_class=work_class, scope_id=scope,
                        preemption_scope_id=preemption_scope, deadline=deadline,
                    )
                if self._key(request, scope) != key:
                    raise ValueError("local runtime identity changed before cache hit")
                with self._capacity_lock:
                    ttl = self._serving.policy.cache_ttl_seconds
                with self._cache_lock:
                    valid = (
                        self._cache.get(key) is cached
                        and epoch == self._cache_epoch
                        and time.monotonic() < min(cached.expires_at, cached.created_at + ttl)
                    )
                    if valid:
                        self._cache.move_to_end(key)
                if valid:
                    with self._capacity_lock:
                        self._cache_hits += 1
                    return replace(cached.result, cached=True)

        loop = asyncio.get_running_loop()
        flight_key = (key, loop)
        with self._cache_lock:
            future = self._singleflight.get(flight_key)
            leader = future is None
            if not leader and self._singleflight_waiters >= self.max_concurrency + self.max_queue_size:
                overloaded = True
            else:
                overloaded = False
                if future is None:
                    future = loop.create_future()
                    # An owner with no followers still retrieves its failure.
                    future.add_done_callback(lambda item: None if item.cancelled() else item.exception())
                    self._singleflight[flight_key] = future
                else:
                    self._singleflight_waiters += 1
                    self._singleflight_hits += 1
        if overloaded:
            with self._capacity_lock:
                self._overloaded += 1
            raise LocalInferenceOverloaded("local inference in-flight waiter capacity is full")
        assert future is not None
        try:
            if not leader:
                try:
                    remaining = follower_wait_limit
                    if deadline is not None:
                        remaining = min(remaining, deadline - time.monotonic())
                    if remaining <= 0:
                        raise LocalInferenceCancelled("local inference deadline exceeded")
                    result = await asyncio.wait_for(asyncio.shield(future), timeout=remaining)
                except TimeoutError as exc:
                    raise LocalInferenceCancelled("local inference deadline exceeded") from exc
                return replace(result)
            try:
                result = await self._generate_uncached(
                    request, key=key, scope_id=scope,
                    preemption_scope_id=preemption_scope, work_class=work_class,
                    deadline=deadline, cache_epoch=epoch,
                )
            except BaseException as exc:
                if not future.done():
                    if isinstance(exc, asyncio.CancelledError):
                        future.cancel()
                    else:
                        future.set_exception(exc)
                raise
            if not future.done():
                future.set_result(replace(result))
            return result
        finally:
            with self._cache_lock:
                if leader:
                    self._singleflight.pop(flight_key, None)
                else:
                    self._singleflight_waiters -= 1

    async def _generate_uncached(
        self,
        request: LocalInferenceRequest,
        *,
        key: str,
        scope_id: str,
        preemption_scope_id: str,
        work_class: str,
        deadline: float | None,
        cache_epoch: int,
    ) -> LocalInferenceResult:
        cancel = threading.Event()
        ticket = self._reserve(work_class, scope_id, preemption_scope_id, deadline, cancel)
        await self._acquire_execution_slot(ticket)
        started = threading.Event()
        try:
            worker = asyncio.create_task(asyncio.to_thread(self._infer_admitted, request, cancel, started, ticket))
            if deadline is None:
                result = await self._await_worker(worker, cancel)
            else:
                # Timer only requests cooperative cancellation. Await-worker
                # retains ownership through the backend's physical drain.
                timeout = None
                try:
                    timeout = asyncio.get_running_loop().call_later(
                        max(0.0, deadline - time.monotonic()), cancel.set,
                    )
                    result = await self._await_worker(worker, cancel)
                finally:
                    if timeout is not None:
                        timeout.cancel()
                if time.monotonic() >= deadline:
                    raise LocalInferenceCancelled("local inference deadline exceeded")
        except BaseException:
            # Executor rejection can occur before the worker owns its slot.
            # Once started, only the OS worker releases its own reservation.
            if not started.is_set():
                with self._capacity_lock:
                    self._active -= 1
                    self._failed += 1
                    self._running.pop(ticket.sequence, None)
                self._execution_slots.release()
            raise

        if result.model_id != self.model.model_id or result.model_digest != self.model.model_digest:
            raise ValueError("local inference result model identity drift")
        if self._key(request, scope_id) != key:
            raise ValueError("local runtime identity changed during inference")
        if result.usage_source == "local_model" and result.output_tokens > request.max_output_tokens:
            raise ValueError("local backend exceeded admitted output-token limit")

        declared_tools = {
            str(item.get("tool_id", "")).strip(): item
            for item in request.tools
            if str(item.get("tool_id", "")).strip()
        }
        for call in result.tool_calls:
            declared = declared_tools.get(call.tool_id)
            if declared is None:
                raise ValueError(f"local inference requested undeclared tool_id {call.tool_id!r}")
            schema = declared.get("input_schema")
            if schema is not None:
                if not isinstance(schema, Mapping):
                    raise ValueError(f"declared tool {call.tool_id!r} input_schema must be an object")
                try:
                    validate_json_value(
                        schema,
                        dict(call.arguments),
                        path=f"tool_call[{call.call_id}].arguments",
                    )
                except ToolContractError as exc:
                    raise ValueError(
                        f"local tool arguments violate schema for {call.tool_id!r}: {exc}"
                    ) from exc

        if request.tool_choice == "none" and result.tool_calls:
            raise ValueError("local backend returned tools when tool_choice is none")
        if request.tool_choice in {"required", "specific"} and not result.tool_calls:
            raise ValueError("local backend omitted required tool calls")
        if request.tool_choice == "specific" and any(
            call.tool_id != request.specific_tool_id for call in result.tool_calls
        ):
            raise ValueError("local backend returned a different specific tool")
        if (
            request.structured_output_schema is not None
            and not result.tool_calls
            and result.structured_output is None
        ):
            raise ValueError("local backend omitted required structured output")

        if result.structured_output is not None and request.structured_output_schema is not None:
            try:
                validate_json_value(
                    request.structured_output_schema,
                    dict(result.structured_output),
                    path="structured_output",
                )
            except ToolContractError as exc:
                raise ValueError(f"local structured output violates request schema: {exc}") from exc

        with self._capacity_lock:
            policy = self._serving.policy
            byte_limit = self._effective_cache_limit_locked()
        if (
            self.cache_size and byte_limit and policy.cache_ttl_seconds
            and result.finish_reason not in {"cancelled", "deadline"}
        ):
            size_bytes = self._cache_size_bytes(result, byte_limit)
            with self._cache_lock:
                if self._key(request, scope_id) != key:
                    raise ValueError("local runtime identity changed before caching")
                # The cached copy owns all nested structured/tool output;
                # application edits to the returned object cannot rewrite it.
                if size_bytes <= byte_limit and cache_epoch == self._cache_epoch:
                    previous = self._cache.pop(key, None)
                    if previous is not None:
                        self._cache_bytes -= previous.size_bytes
                    now = time.monotonic()
                    self._cache[key] = _CachedInference(
                        replace(result), now, now + policy.cache_ttl_seconds, size_bytes,
                    )
                    self._cache_bytes += size_bytes
                    while len(self._cache) > self.cache_size or self._cache_bytes > byte_limit:
                        _, discarded = self._cache.popitem(last=False)
                        self._cache_bytes -= discarded.size_bytes
                        self._cache_evictions += 1
        return result

    async def generate_many(
        self,
        requests: Sequence[LocalInferenceRequest],
        *,
        work_class: str = "interactive",
        scope_id: str | None = None,
        preemption_scope_id: str | None = None,
        deadline: float | None = None,
    ) -> tuple[LocalInferenceResult, ...]:
        if not requests:
            return ()
        if len(requests) > self.max_batch_size:
            raise ValueError("local inference batch exceeds configured max_batch_size")
        if any(not isinstance(item, LocalInferenceRequest) for item in requests):
            raise TypeError("batch requires LocalInferenceRequest values")
        tasks = [asyncio.create_task(self.generate(
            item, work_class=work_class, scope_id=scope_id,
            preemption_scope_id=preemption_scope_id, deadline=deadline,
        )) for item in requests]
        try:
            # A failed member must not detach still-running native workers.
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await _drain_inference_tasks(tasks)
            raise
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return tuple(results)


async def _drain_inference_tasks(tasks: Sequence[asyncio.Task]) -> None:
    """Keep ownership through repeated cancellation until native cleanup ends."""
    drained = asyncio.gather(*tasks, return_exceptions=True)
    while not drained.done():
        try:
            await asyncio.shield(drained)
        except asyncio.CancelledError:
            continue
    drained.result()


@dataclass(slots=True)
class _BatchItem:
    request: LocalInferenceRequest
    future: asyncio.Future[LocalInferenceResult]
    task: asyncio.Task[None] | None = None


class LocalInferenceScheduler:
    """Bounded micro-batching queue for local inference requests."""

    def __init__(
        self,
        engine: LocalInferenceEngine,
        *,
        max_batch_size: int = 8,
        batch_window_ms: float = 2.0,
    ) -> None:
        if (
            isinstance(max_batch_size, bool)
            or not isinstance(max_batch_size, int)
            or not 1 <= max_batch_size <= 256
        ):
            raise ValueError("max_batch_size must be in [1, 256]")
        if (
            isinstance(batch_window_ms, bool)
            or not isinstance(batch_window_ms, (int, float))
            or not math.isfinite(float(batch_window_ms))
            or not 0 <= batch_window_ms <= 1000
        ):
            raise ValueError("batch_window_ms must be in [0, 1000]")
        self.engine = engine
        self.max_batch_size = max_batch_size
        self.batch_window = batch_window_ms / 1000.0
        self._queue: asyncio.Queue[_BatchItem | None] = asyncio.Queue(maxsize=max_batch_size * 32)
        self._worker: asyncio.Task[None] | None = None
        self._admission_lock = asyncio.Lock()
        self._close_task: asyncio.Task[None] | None = None
        self._closed = False

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    async def submit(self, request: LocalInferenceRequest) -> LocalInferenceResult:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        if self._closed:
            raise RuntimeError("local inference scheduler is closed")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[LocalInferenceResult] = loop.create_future()
        item = _BatchItem(request=request, future=future)
        try:
            # A producer waiting for queue space cannot enqueue after the
            # shutdown sentinel. Close waits for accepted admission to finish.
            async with self._admission_lock:
                if self._closed:
                    raise RuntimeError("local inference scheduler is closed")
                self._ensure_worker()
                await self._queue.put(item)
            return await future
        except asyncio.CancelledError:
            future.cancel()
            if item.task is not None:
                item.task.cancel()
                await _drain_inference_tasks([item.task])
            raise

    async def _execute_item(self, item: _BatchItem) -> None:
        try:
            result = await self.engine.generate(item.request)
        except asyncio.CancelledError:
            item.future.cancel()
            raise
        except Exception as exc:  # noqa: BLE001 -- forward arbitrary model failures to their owning future
            if not item.future.done():
                item.future.set_exception(exc)
        else:
            if not item.future.done():
                item.future.set_result(result)

    async def _run(self) -> None:
        while True:
            first = await self._queue.get()
            if first is None:
                return
            batch = [first]
            close_after_batch = False
            deadline = asyncio.get_running_loop().time() + self.batch_window
            while len(batch) < self.max_batch_size:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    item = await asyncio.wait_for(self._queue.get(), remaining)
                except TimeoutError:
                    break
                if item is None:
                    close_after_batch = True
                    break
                batch.append(item)

            active = [item for item in batch if not item.future.cancelled()]
            if active:
                for item in active:
                    item.task = asyncio.create_task(self._execute_item(item))
                # Each caller owns its result and cancellation. A malformed
                # request must not fail unrelated requests sharing a batch.
                await asyncio.gather(*(item.task for item in active), return_exceptions=True)
            if close_after_batch:
                return

    async def close(self) -> None:
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(self._finish_close())
        try:
            await asyncio.shield(self._close_task)
        except asyncio.CancelledError:
            # Do not interrupt a saturated queue's sentinel insertion, or
            # expose completed shutdown while native inference is still live.
            await _drain_inference_tasks([self._close_task])
            raise

    async def _finish_close(self) -> None:
        async with self._admission_lock:
            if self._worker is not None and not self._worker.done():
                await self._queue.put(None)
        if self._worker is not None:
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

    def __init__(
        self,
        engine: LocalInferenceEngine,
        *,
        default_seed: int = 0,
        artifact_status: Mapping[str, object] | None = None,
    ) -> None:
        self.engine = engine
        self.model = engine.model.model_id
        self._activated_model_digest = engine.model.model_digest
        self.default_seed = default_seed
        self._artifact_status = None if artifact_status is None else dict(artifact_status)

    @property
    def available(self) -> bool:
        try:
            if self.engine.model.model_digest != self._activated_model_digest:
                return False
            self.generation_limits()
            check = getattr(self.engine.model, "check_readiness", None)
            if callable(check):
                check()
            else:
                check = getattr(self.engine.model, "assert_identity", None)
                if callable(check):
                    check()
            return True
        except (OSError, ValueError, RuntimeError):
            return False

    @property
    def supports_cooperative_cancellation(self) -> bool:
        return True

    @property
    def protocol_capabilities(self) -> tuple[str, ...]:
        supplied = getattr(self.engine.model, "protocol_capabilities", ("text-generation",))
        if (
            not isinstance(supplied, (tuple, list))
            or not supplied
            or set(supplied) - {"text-generation", "tool-calls", "structured-output"}
        ):
            raise ProviderPolicyError("local model protocol capabilities are invalid")
        return tuple(supplied)

    def generation_limits(self) -> dict[str, Any]:
        """Resolve limits from the activated backend, rather than a catalog guess."""
        model = self.engine.model
        resolve = getattr(model, "generation_limits", None)
        if callable(resolve):
            supplied = resolve()
            if not isinstance(supplied, Mapping):
                raise ProviderPolicyError("activated local generation limits must be an object")
            context = supplied.get("context_window")
            output = supplied.get("max_output_tokens")
            total = supplied.get("max_total_tokens")
            if (
                type(context) is not int or context < 1
                or type(output) is not int or output < 1
                or (total is not None and (type(total) is not int or total < 1))
                or type(supplied.get("shared_context", False)) is not bool
            ):
                raise ProviderPolicyError("activated local generation limits are invalid")
            tokenizer = supplied.get("tokenizer", "utf8_bytes_upper_bound")
            source = supplied.get("limits_source", "activated_local_backend")
            if any(not isinstance(item, str) or not item or len(item) > 256 for item in (tokenizer, source)):
                raise ProviderPolicyError("activated local generation-limit metadata is invalid")
            limits = {
                "context_window": context,
                "max_output_tokens": min(8_192, output, max(1, context // 2)),
                "max_total_tokens": total,
                "shared_context": supplied.get("shared_context", False),
                "tokenizer": tokenizer,
                "limits_source": source,
            }
            for name in ("tokenizer_max_chars", "tokenizer_max_tokens"):
                value = supplied.get(name)
                if value is not None:
                    if type(value) is not int or value < 1:
                        raise ProviderPolicyError("activated local tokenizer limit is invalid")
                    limits[name] = value
            return limits
        runtime = getattr(model, "runtime", None)
        native_limits = getattr(runtime, "limits", None)
        config = getattr(model, "config", None)
        context = getattr(native_limits, "max_context", None)
        if context is None:
            context = getattr(config, "context_size", None)
        declared_context = context is not None
        if not declared_context and getattr(model, "model_family", None) == "gguf_open_weight":
            raise ProviderPolicyError("activated GGUF serving requires an explicit context_size")
        if context is None:
            context = 16_384
        if type(context) is not int or context < 1:
            raise ProviderPolicyError("activated local context limit is invalid")
        output = getattr(native_limits, "max_new_tokens", 8_192)
        total = getattr(native_limits, "max_total_tokens", None)
        if (
            type(output) is not int
            or output < 1
            or (total is not None and (type(total) is not int or total < 1))
        ):
            raise ProviderPolicyError("activated local generation limits are invalid")
        # GGUF CLI admission conservatively reserves completion in its context;
        # native runtimes retain their explicit sliding-context/total limits.
        shared_context = native_limits is None and getattr(config, "context_size", None) is not None
        return {
            "context_window": context,
            "max_output_tokens": min(8_192, output, max(1, context // 2)),
            "max_total_tokens": context if shared_context else total,
            "shared_context": shared_context,
            "tokenizer": getattr(model, "tokenizer_kind", "utf8_bytes_upper_bound"),
            "limits_source": "activated_local_backend" if declared_context else "engine_chat_policy",
        }

    def status(self) -> dict[str, Any]:
        status = super().status()
        status["execution_mode"] = "local"
        status["network_policy"] = "none"
        status["model_digest"] = self.engine.model.model_digest
        status["runtime_digest"] = self.runtime_digest
        status["execution_profile_digest"] = getattr(
            self.engine.model,
            "execution_profile_digest",
            None,
        )
        status["capacity"] = {
            "max_concurrency": self.engine.max_concurrency,
            "max_batch_size": self.engine.max_batch_size,
            "cache_entries": self.engine.cache_size,
        }
        status["artifact"] = None if self._artifact_status is None else dict(self._artifact_status)
        status["model_family"] = getattr(self.engine.model, "model_family", "operator_callable")
        status["protocol_capabilities"] = list(self.protocol_capabilities)
        status["generation_limits"] = self.generation_limits()
        status["capacity"]["max_queue_size"] = self.engine.max_queue_size
        status["runtime"] = self.engine.snapshot()
        return status

    @property
    def runtime_digest(self) -> str | None:
        value = getattr(self.engine.model, "runtime_digest", None)
        if value is None:
            return None
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(ch not in "0123456789abcdef" for ch in value)
        ):
            raise ValueError("local runtime digest must be lowercase sha256")
        return value

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        started = time.monotonic()
        if not isinstance(request, ProviderRequest):
            raise TypeError("request must be ProviderRequest")
        if not self.available:
            raise ProviderUnavailableError("activated local model is unavailable")
        model_id = _validate_request(request, default_model=self.model)
        if model_id != self.model:
            raise ProviderPolicyError("local model override differs from activated model")
        if getattr(request, "temperature", None) is not None:
            raise ProviderPolicyError("local model does not support request temperature")
        budget = request.resource_budget
        limits = self.generation_limits()
        max_tokens = (
            min(256, budget.max_output_tokens, limits["max_output_tokens"])
            if request.max_output_tokens is None
            else request.max_output_tokens
        )
        if type(max_tokens) is not int or max_tokens < 1 or max_tokens > budget.max_output_tokens:
            raise ProviderPolicyError("local output token budget exceeded")
        if max_tokens > limits["max_output_tokens"]:
            raise ProviderPolicyError("local output exceeds activated model limit")
        tools = _provider_tool_definitions(request)
        _provider_tool_choice_payload(request, tools)
        choice = str(request.tool_choice or "auto").strip().lower()
        if choice == "none":
            tools = ()
        elif choice == "specific":
            tools = tuple(tool for tool in tools if tool.tool_id == str(request.specific_tool_id).strip())
        if tools and "tool-calls" not in self.protocol_capabilities:
            raise ProviderPolicyError("activated local model does not support tool-call protocol")
        if (
            request.structured_output_schema is not None
            and "structured-output" not in self.protocol_capabilities
        ):
            raise ProviderPolicyError("activated local model does not support structured-output protocol")
        seed_material = "|".join(
            item or ""
            for item in (
                request.operation_id,
                request.execution_id,
                request.turn_id,
                request.prompt,
            )
        )
        derived_seed = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16)
        local_request = LocalInferenceRequest(
            prompt=request.prompt,
            instructions=request.instructions,
            history=tuple((item.role, item.content) for item in request.history),
            max_output_tokens=max_tokens,
            seed=self.default_seed ^ derived_seed,
            tools=tuple(item.as_dict() for item in tools),
            structured_output_schema=(
                None if request.structured_output_schema is None else dict(request.structured_output_schema)
            ),
            context_digest=request.context_digest,
            tool_choice=choice,
            specific_tool_id=(str(request.specific_tool_id).strip() if choice == "specific" else None),
        )
        count_tokens = getattr(self.engine.model, "count_input_tokens", None)
        if callable(count_tokens):
            input_tokens = count_tokens(local_request)
        else:
            render = getattr(self.engine.model, "_render_prompt", None)
            full_prompt = render(local_request) if callable(render) else local_request.rendered_input
            input_tokens = len(full_prompt.encode("utf-8")) + 1
        if type(input_tokens) is not int or input_tokens < 0:
            raise ProviderPolicyError("local tokenizer returned an invalid token count")
        if "tokenizer_max_chars" in limits and len(local_request.rendered_input) > limits["tokenizer_max_chars"]:
            raise ProviderPolicyError("local input exceeds activated tokenizer character limit")
        if "tokenizer_max_tokens" in limits and input_tokens > limits["tokenizer_max_tokens"]:
            raise ProviderPolicyError("local input exceeds activated tokenizer token limit")
        if input_tokens > budget.max_input_tokens:
            raise ProviderPolicyError("local input token budget exceeded")
        if input_tokens > limits["context_window"]:
            raise ProviderPolicyError("local input exceeds activated context window")
        if limits["max_total_tokens"] is not None and input_tokens + max_tokens > limits["max_total_tokens"]:
            raise ProviderPolicyError("local request exceeds activated total-token limit")
        remaining = float(budget.max_wall_seconds) - (time.monotonic() - started)
        if request.deadline is not None:
            if (
                not isinstance(request.deadline, datetime)
                or request.deadline.tzinfo is None
                or request.deadline.utcoffset() is None
            ):
                raise ValueError("local inference deadline must be timezone-aware")
            remaining = min(
                remaining,
                (request.deadline.astimezone(UTC) - datetime.now(UTC)).total_seconds(),
            )
        if not math.isfinite(remaining) or remaining <= 0:
            raise LocalInferenceCancelled("local inference deadline exceeded")
        # Cache/coalescing authority is inherited from the validated provider
        # envelope. Anonymous requests receive an opaque scope rather than
        # sharing output merely because prompts or tenant labels coincide.
        governance = request.governance_context
        lineage = request.operation_id or request.execution_id
        governance_scope = None if governance is None else governance.as_dict()
        if governance_scope is not None:
            # Purpose remains in the cache identity below. It cannot make
            # foreground/background work from one operation unrelated.
            governance_scope.pop("purpose", None)
        authority = {
            "tenant": request.tenant_id,
            "data_class": request.data_class,
            "operation": lineage or secrets.token_hex(24),
            "governance": governance_scope,
        }
        preemption_scope = _digest(authority)
        cache_scope = _digest({
            "authority": authority,
            "purpose": request.purpose,
            "context_id": request.context_id,
            "context_digest": request.context_digest,
            "sources": request.context_source_snapshot,
            "compiler": request.context_compiler_version,
        })
        work_class = "background" if request.purpose.strip().lower() in {
            "idle-learning", "background-learning", "self-maintenance",
            "self-augmentation", "training", "simulation_training",
            "ratchet-learning", "idle-maintenance",
        } else "interactive"
        try:
            result = await asyncio.wait_for(
                self.engine.generate(
                    local_request,
                    work_class=work_class,
                    scope_id=cache_scope,
                    preemption_scope_id=preemption_scope,
                    deadline=time.monotonic() + remaining,
                ),
                timeout=remaining,
            )
        except TimeoutError as exc:
            raise LocalInferenceCancelled("local inference deadline exceeded") from exc
        if time.monotonic() - started > budget.max_wall_seconds or (
            request.deadline is not None and datetime.now(UTC) >= request.deadline.astimezone(UTC)
        ):
            raise LocalInferenceCancelled("local inference completed after its admitted deadline")
        if result.input_tokens > budget.max_input_tokens:
            raise ProviderPolicyError("local result exceeded admitted input-token budget")
        if result.usage_source == "local_model" and result.output_tokens > max_tokens:
            raise ProviderProtocolViolationError("local result exceeded admitted output-token budget")
        if len(result.tool_calls) > budget.max_tool_calls:
            raise ProviderPolicyError("local result exceeded admitted tool-call budget")
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
            execution_receipt_digest=result.execution_receipt_digest,
            structured_output=(
                dict(result.structured_output) if result.structured_output is not None else None
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
                usage_source=result.usage_source,
            ),
            latency_ms=result.latency_ms,
            data_class=request.data_class,
            context_id=request.context_id,
            context_digest=request.context_digest,
            context_source_snapshot=request.context_source_snapshot,
            context_compiler_version=request.context_compiler_version,
        )
