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
import sys
import threading
import time
from collections import Counter, OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from skeleton.compat.datetime_utc import UTC
from datetime import datetime
from typing import Any, Protocol, TypedDict

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
_RESOURCE_CPU_SAMPLES: dict[str, tuple[float, float, float | None, float | None]] = {}
_RESOURCE_COLLECTION_LOCK = threading.Lock()
_RESOURCE_COLLECTION: tuple[float, ServingResources] | None = None
_ANONYMOUS_TENANT_SCOPE = hashlib.sha256(b"skeleton-local-anonymous-tenant-v1").hexdigest()


class LocalInferenceCancelled(RuntimeError):
    """Cooperative local inference cancellation was observed."""


class LocalInferenceOverloaded(ProviderUnavailableError):
    """The configured local worker and waiting capacity is already reserved."""


class LocalInputBudgetError(ValueError):
    """A declared local request exceeds its finite token/character allowance."""


@dataclass(frozen=True, slots=True)
class LocalInputBudget:
    """Pure numeric admission shared by provider and native preparation.

    Construction never tokenizes text or reserves capacity. Request-specific
    execution grants can only tighten the activated limits at validation time.
    """

    context_window: int
    max_output_tokens: int
    max_total_tokens: int | None = None
    tokenizer_max_tokens: int | None = None
    tokenizer_max_chars: int | None = None

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if value is None and name not in {"context_window", "max_output_tokens"}:
                continue
            if type(value) is not int or not 1 <= value <= 9_007_199_254_740_991:
                raise LocalInputBudgetError("local input budget requires bounded positive integer limits")

    @classmethod
    def from_limits(cls, limits: Mapping[str, Any]) -> LocalInputBudget:
        if not isinstance(limits, Mapping):
            raise LocalInputBudgetError("local generation limits must be an object")
        try:
            candidate = cls(**{name: limits.get(name) for name in cls.__dataclass_fields__})
        except TypeError as exc:
            raise LocalInputBudgetError("local generation limits are incomplete") from exc
        shared = limits.get("shared_context", False)
        if type(shared) is not bool:
            raise LocalInputBudgetError("local shared-context policy must be boolean")
        if shared:
            candidate = replace(
                candidate,
                max_total_tokens=min(
                    candidate.context_window,
                    (
                        candidate.max_total_tokens
                        if candidate.max_total_tokens is not None
                        else candidate.context_window
                    ),
                ),
            )
        return candidate

    def validate_characters(self, input_characters: int) -> None:
        if type(input_characters) is not int or not 0 <= input_characters <= 4 * 1024 * 1024:
            raise LocalInputBudgetError(
                "local tokenizer character count exceeds its bounded non-negative allowance"
            )
        if self.tokenizer_max_chars is not None and input_characters > self.tokenizer_max_chars:
            raise LocalInputBudgetError("local input exceeds activated tokenizer character limit")

    def validate_tokens(
        self,
        input_tokens: int,
        output_tokens: int,
        *,
        resource_max_input_tokens: int | None = None,
        resource_max_output_tokens: int | None = None,
    ) -> None:
        for name, value, lower in (("input", input_tokens, 0), ("output", output_tokens, 1)):
            if type(value) is not int or not lower <= value <= 9_007_199_254_740_991:
                raise LocalInputBudgetError("local " + name + " token count is invalid")
        for name, value in (("input", resource_max_input_tokens), ("output", resource_max_output_tokens)):
            if value is not None and (type(value) is not int or not 1 <= value <= 9_007_199_254_740_991):
                raise LocalInputBudgetError("local " + name + " resource ceiling is invalid")
        if resource_max_input_tokens is not None and input_tokens > resource_max_input_tokens:
            raise LocalInputBudgetError("local input token budget exceeded")
        if resource_max_output_tokens is not None and output_tokens > resource_max_output_tokens:
            raise LocalInputBudgetError("local output token budget exceeded")
        if output_tokens > self.max_output_tokens:
            raise LocalInputBudgetError("local output exceeds activated model limit")
        if self.tokenizer_max_tokens is not None and input_tokens > self.tokenizer_max_tokens:
            raise LocalInputBudgetError("local input exceeds activated tokenizer token limit")
        if input_tokens > self.context_window:
            raise LocalInputBudgetError("local input exceeds activated context window")
        if self.max_total_tokens is not None and input_tokens + output_tokens > self.max_total_tokens:
            raise LocalInputBudgetError("local request exceeds activated total-token limit")

    def validate_request(
        self,
        request: LocalInferenceRequest,
        input_tokens: int,
        *,
        rendered: str | None = None,
        resource_max_input_tokens: int | None = None,
        resource_max_output_tokens: int | None = None,
    ) -> None:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        text = request.rendered_input if rendered is None else rendered
        if not isinstance(text, str):
            raise LocalInputBudgetError("local rendered input must be text")
        self.validate_characters(len(text))
        # Bound encoded input before allocating an entire potentially large
        # UTF-8 copy; native tokenizers and GGUF share the same outer ceiling.
        encoded = 0
        try:
            for offset in range(0, len(text), 8192):
                encoded += len(text[offset : offset + 8192].encode("utf-8", errors="strict"))
                if encoded > 4 * 1024 * 1024:
                    raise LocalInputBudgetError("local rendered input exceeds 4 MiB")
        except UnicodeError as exc:
            raise LocalInputBudgetError("local rendered input must be valid UTF-8") from exc
        self.validate_tokens(
            input_tokens,
            request.max_output_tokens,
            resource_max_input_tokens=resource_max_input_tokens,
            resource_max_output_tokens=resource_max_output_tokens,
        )


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
        if any(
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 256
            or any(ord(character) < 32 for character in value)
            for value in (self.call_id, self.tool_id)
        ):
            raise ValueError("local tool call ids must be bounded non-empty text")
        if not isinstance(self.arguments, Mapping):
            raise TypeError("local tool arguments must be an object")
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
        if (
            not isinstance(self.model_id, str)
            or not self.model_id.strip()
            or len(self.model_id) > 256
            or any(ord(character) < 32 for character in self.model_id)
        ):
            raise ValueError("model_id must be bounded non-empty text")
        if self.response_id is not None and (
            not isinstance(self.response_id, str)
            or not self.response_id.strip()
            or len(self.response_id) > 512
            or any(ord(character) < 32 for character in self.response_id)
        ):
            raise ValueError("local response_id must be bounded non-empty text")
        if type(self.cached) is not bool:
            raise ValueError("local cached flag must be boolean")
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

        if (
            not isinstance(self.model_digest, str)
            or len(self.model_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.model_digest)
        ):
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
        if not isinstance(self.tool_calls, (tuple, list)) or len(self.tool_calls) > 256:
            raise ValueError("local inference result exceeds tool-call protocol bound")
        supplied_calls = tuple(self.tool_calls)
        if any(not isinstance(call, LocalToolCall) for call in supplied_calls):
            raise TypeError("tool_calls must contain LocalToolCall values")
        # Enforce one aggregate payload bound before copying nested call data.
        # Per-call limits alone allowed hundreds of individually valid objects
        # to exceed the complete inference output allowance.
        payload_bytes = len((self.text or "").encode("utf-8"))
        for call in supplied_calls:
            payload_bytes += len(call.call_id.encode("utf-8")) + len(call.tool_id.encode("utf-8"))
            payload_bytes += len(_stable_json(dict(call.arguments)).encode("utf-8"))
            if payload_bytes > 4 * 1024 * 1024:
                raise ValueError("local inference output exceeds its aggregate 4 MiB bound")
        calls = tuple(LocalToolCall(call.call_id, call.tool_id, call.arguments) for call in supplied_calls)
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
            if not isinstance(self.structured_output, Mapping):
                raise TypeError("local structured output must be an object")
            encoded = _stable_json(dict(self.structured_output))
            if payload_bytes + len(encoded.encode("utf-8")) > 4 * 1024 * 1024:
                raise ValueError("local structured output exceeds 4 MiB output bound")
            object.__setattr__(self, "structured_output", json.loads(encoded))
        if self.latency_ms is not None:
            if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, (int, float)):
                raise ValueError("latency_ms must be a finite non-negative number")
            latency = float(self.latency_ms)
            if not math.isfinite(latency) or latency < 0:
                raise ValueError("latency_ms must be finite and non-negative")
            object.__setattr__(self, "latency_ms", latency)


@dataclass(frozen=True, slots=True)
class LocalPreparedInput:
    """Per-request native tokenization, sealed by its backend and host scope.

    This value is never persisted, shared through a cache, or exposed in
    status. Native owners validate the immutable token payload before use.
    """

    request_digest: str
    model_digest: str
    runtime_digest: str
    execution_profile_digest: str | None
    tokenizer_digest: str
    source_digest: str
    sequence_digest: str
    input_tokens: int
    scope_digest: str | None
    token_sequence: Any = field(repr=False, compare=False)
    issuer: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in (
            "request_digest",
            "model_digest",
            "runtime_digest",
            "tokenizer_digest",
            "source_digest",
            "sequence_digest",
            "execution_profile_digest",
            "scope_digest",
        ):
            value = getattr(self, name)
            if value is None and name in {"execution_profile_digest", "scope_digest"}:
                continue
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ValueError("prepared local input requires immutable SHA-256 bindings")
        if type(self.input_tokens) is not int or not 1 <= self.input_tokens <= 1_048_576:
            raise ValueError("prepared local input token count is out of bounds")
        if self.issuer is None or self.token_sequence is None:
            raise ValueError("prepared local input requires backend ownership")

    def assert_binding(
        self,
        request: LocalInferenceRequest,
        *,
        issuer: object,
        model_digest: str,
        runtime_digest: str,
        execution_profile_digest: str | None,
        tokenizer_digest: str,
        source_digest: str,
    ) -> None:
        if self.issuer is not issuer or self.request_digest != request.digest:
            raise ValueError("prepared local input request or owner mismatch")
        if (
            self.model_digest != model_digest
            or self.runtime_digest != runtime_digest
            or self.execution_profile_digest != execution_profile_digest
            or self.tokenizer_digest != tokenizer_digest
            or self.source_digest != source_digest
        ):
            raise ValueError("prepared local input execution identity drift")


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
    tenant_scope_id: str
    enqueued_at: float
    deadline: float
    cancel: threading.Event
    retired: str | None = None
    started_at: float | None = None
    starvation_protected: bool = False
    coalesced: bool = False
    estimated_memory_bytes: int = 0
    memory_wait_observed: bool = False


class _BatchLimits(TypedDict):
    max_batch_size: int
    max_batch_tokens: int | None


@dataclass(frozen=True, slots=True)
class _CachedInference:
    result: LocalInferenceResult
    created_at: float
    expires_at: float
    size_bytes: int


def _resource_text(path: str, maximum: int = 16_384) -> str:
    with open(path, encoding="ascii") as handle:
        value = handle.read(maximum + 1)
    if len(value) > maximum:
        raise ValueError("resource metadata exceeds read bound")
    return value.strip()


def _cpu_counter_sample(
    key: str,
    total: float,
    *,
    idle: float | None = None,
    capacity: float = 1.0,
) -> float | None:
    """Measure a real counter delta; warmup, stale and reset values stay unknown."""
    now = time.monotonic()
    if not math.isfinite(total) or total < 0 or not math.isfinite(capacity) or capacity <= 0:
        return None
    with _RESOURCE_SAMPLE_LOCK:
        previous = _RESOURCE_CPU_SAMPLES.get(key)
        if (
            previous is None
            or now - previous[0] > 5.0
            or total < previous[1]
            or (idle is not None and (previous[2] is None or idle < previous[2]))
        ):
            if key not in _RESOURCE_CPU_SAMPLES and len(_RESOURCE_CPU_SAMPLES) >= 64:
                del _RESOURCE_CPU_SAMPLES[next(iter(_RESOURCE_CPU_SAMPLES))]
            _RESOURCE_CPU_SAMPLES[key] = (now, total, idle, None)
            return None
        elapsed = now - previous[0]
        if elapsed < 0.25:
            return previous[3]
        delta = total - previous[1]
        if idle is None:
            ratio = delta / elapsed / capacity
        elif delta > 0:
            ratio = min(1.0, max(0.0, 1.0 - (idle - previous[2]) / delta))
        else:
            ratio = None
        if ratio is not None and (not math.isfinite(ratio) or ratio < 0):
            ratio = None
        _RESOURCE_CPU_SAMPLES[key] = (now, total, idle, ratio)
        return ratio


def _cpu_set_size(value: str) -> int | None:
    if not value:
        return None
    count = 0
    for part in value.split(","):
        endpoints = part.split("-")
        if len(endpoints) not in {1, 2}:
            raise ValueError("invalid CPU set")
        first = int(endpoints[0])
        last = int(endpoints[-1])
        if not 0 <= first <= last <= 1_048_576:
            raise ValueError("invalid CPU set range")
        count += last - first + 1
    return count or None


def _linux_cgroup_paths() -> dict[str, tuple[str, str]]:
    """Resolve this process's cgroup mounts without assuming container roots."""
    memberships: dict[str, str] = {}
    for line in _resource_text("/proc/self/cgroup").splitlines():
        hierarchy, controllers, path = line.split(":", 2)
        if not path.startswith("/") or ".." in path.split("/"):
            continue
        if hierarchy == "0" and not controllers:
            memberships["v2"] = path
        for controller in controllers.split(","):
            if controller:
                memberships[controller] = path
    result: dict[str, tuple[str, str]] = {}
    for line in _resource_text("/proc/self/mountinfo", 131_072).splitlines():
        left, separator, right = line.partition(" - ")
        if not separator:
            continue
        fields, extra = left.split(), right.split()
        if len(fields) < 5 or len(extra) < 3 or extra[0] not in {"cgroup", "cgroup2"}:
            continue

        def unescape(value: str) -> str:
            for old, new in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
                value = value.replace(old, new)
            return value

        mount_root, mount = unescape(fields[3]), unescape(fields[4])
        controllers = ("v2",) if extra[0] == "cgroup2" else tuple(extra[2].split(","))
        for controller in controllers:
            path = memberships.get(controller)
            if path is None:
                continue
            if path == "/":
                relative = ""
            elif mount_root == "/":
                relative = path.lstrip("/")
            elif path == mount_root:
                relative = ""
            elif path.startswith(mount_root.rstrip("/") + "/"):
                relative = path[len(mount_root) :].lstrip("/")
            else:
                continue
            resolved = os.path.normpath(os.path.join(mount, relative))
            if os.path.commonpath((mount, resolved)) == mount:
                result[controller] = (resolved, mount)
    if memberships and not result:
        raise ValueError("active cgroup membership has no readable mount")
    return result


def _cgroup_ancestors(path: str, mount: str) -> tuple[str, ...]:
    result = []
    current = path
    for _ in range(32):
        result.append(current)
        if current == mount:
            return tuple(reversed(result))
        parent = os.path.dirname(current)
        if parent == current or os.path.commonpath((mount, parent)) != mount:
            break
        current = parent
    raise ValueError("cgroup ancestry exceeds sampling bound")


def _sample_linux_resources() -> ServingResources:
    memory = available = rss = cpu = None
    sources: list[str] = []
    reported_cpus = os.cpu_count()
    host_cpus = float(reported_cpus) if type(reported_cpus) is int and reported_cpus > 0 else None
    process_cpus = host_cpus
    try:
        affinity = len(os.sched_getaffinity(0))
        if affinity > 0:
            process_cpus = float(affinity) if host_cpus is None else min(host_cpus, float(affinity))
    except (AttributeError, OSError, ValueError):
        pass
    try:
        with open("/proc/stat", encoding="ascii") as handle:
            first = handle.readline(16_384).split()
        values = [int(value) for value in first[1:9]]
        if first[0] == "cpu" and len(values) >= 4:
            cpu = _cpu_counter_sample(
                "linux_host",
                float(sum(values)),
                idle=float(values[3] + (values[4] if len(values) > 4 else 0)),
            )
            sources.append("linux_cpu" if cpu is not None else "linux_cpu_warming")
    except (OSError, ValueError, IndexError):
        pass
    process_cpu = (
        None
        if process_cpus is None
        else _cpu_counter_sample(
            "linux_process_" + str(process_cpus),
            time.process_time(),
            capacity=process_cpus,
        )
    )
    if process_cpu is not None:
        cpu = process_cpu if cpu is None else max(cpu, process_cpu)
    try:
        values = {}
        for line in _resource_text("/proc/meminfo").splitlines():
            name, _, raw = line.partition(":")
            if name in {"MemTotal", "MemAvailable"}:
                values[name] = int(raw.strip().split()[0]) * 1024
        total = values.get("MemTotal", 0)
        if total > 0 and "MemAvailable" in values:
            available = min(total, max(0, values["MemAvailable"]))
            memory = 1.0 - available / total
            sources.append("linux_memory")
    except (OSError, ValueError, IndexError):
        pass
    try:
        rss = int(_resource_text("/proc/self/statm").split()[1]) * int(os.sysconf("SC_PAGE_SIZE"))
        sources.append("linux_rss")
    except (OSError, ValueError, IndexError):
        pass
    try:
        groups = _linux_cgroup_paths()
    except (OSError, ValueError):
        groups = {}
        cpu = memory = available = None
        sources.append("cgroup_layout_unknown")
    unified = groups.get("v2")
    memory_group = unified or groups.get("memory")
    if memory_group is not None:
        try:
            for directory in _cgroup_ancestors(*memory_group):
                name = "memory.max" if unified else "memory.limit_in_bytes"
                current_name = "memory.current" if unified else "memory.usage_in_bytes"
                try:
                    maximum = _resource_text(os.path.join(directory, name))
                except FileNotFoundError:
                    continue  # Root/disabled controllers have no own limit.
                if maximum == "max":
                    continue
                limit = int(maximum)
                if limit <= 0 or limit >= 1 << 60:
                    continue
                used = int(_resource_text(os.path.join(directory, current_name)))
                remaining = max(0, limit - used)
                available = remaining if available is None else min(available, remaining)
                fraction = min(1.0, max(0.0, used / limit))
                memory = fraction if memory is None else max(memory, fraction)
            sources.append("cgroup_memory")
        except (OSError, ValueError):
            memory = available = None
            sources.append("cgroup_memory_unknown")
    cpu_group = unified or groups.get("cpu")
    if cpu_group is not None:
        try:
            capacity = host_cpus if host_cpus is not None else math.inf
            group_cpu: list[float] = []
            pending = False
            for directory in _cgroup_ancestors(*cpu_group):
                if unified:
                    try:
                        quota, period = _resource_text(os.path.join(directory, "cpu.max")).split()
                    except FileNotFoundError:
                        quota, period = "max", "100000"
                    if quota != "max":
                        if int(quota) <= 0 or int(period) <= 0:
                            raise ValueError("invalid cgroup CPU quota")
                        capacity = min(capacity, int(quota) / int(period))
                else:
                    quota = int(_resource_text(os.path.join(directory, "cpu.cfs_quota_us")))
                    period = int(_resource_text(os.path.join(directory, "cpu.cfs_period_us")))
                    if quota > 0 and period > 0:
                        capacity = min(capacity, quota / period)
                try:
                    cpus = _cpu_set_size(
                        _resource_text(
                            os.path.join(
                                directory, "cpuset.cpus.effective" if unified else "cpuset.effective_cpus"
                            )
                        )
                    )
                    if cpus is not None:
                        capacity = min(capacity, float(cpus))
                except FileNotFoundError:
                    pass
                if unified:
                    statistics = dict(
                        line.split()
                        for line in _resource_text(os.path.join(directory, "cpu.stat")).splitlines()
                    )
                    usage = int(statistics["usage_usec"]) / 1_000_000.0
                    counter_directory = directory
                else:
                    # cpu and cpuacct can have separate v1 controller mounts.
                    cpuacct = groups.get("cpuacct")
                    if cpuacct is None:
                        raise ValueError("cgroup CPU accounting unavailable")
                    if directory != cpu_group[0]:
                        continue
                    counter_directory = cpuacct[0]
                    usage = (
                        int(_resource_text(os.path.join(counter_directory, "cpuacct.usage")))
                        / 1_000_000_000.0
                    )
                key = (
                    "cgroup_"
                    + hashlib.sha256((counter_directory + ":" + str(capacity)).encode("utf-8")).hexdigest()[
                        :16
                    ]
                )
                fraction = _cpu_counter_sample(key, usage, capacity=capacity)
                if fraction is not None:
                    group_cpu.append(fraction)
                else:
                    pending = True
            if pending:
                cpu = None
                sources.append("cgroup_cpu_warming")
            elif group_cpu:
                cpu = max(group_cpu + ([cpu] if cpu is not None else []))
                sources.append("cgroup_cpu")
            elif cpu is None:
                sources.append("cgroup_cpu_warming")
        except (OSError, ValueError, KeyError):
            cpu = None
            sources.append("cgroup_cpu_unknown")
    return ServingResources(memory, cpu, rss, available, ",".join(sources) or "unavailable")


def _sample_windows_resources() -> ServingResources:
    import ctypes
    from ctypes import wintypes

    memory = available = rss = cpu = None
    sources: list[str] = []
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [
            (name, ctypes.c_ulonglong)
            for name in (
                "total",
                "available",
                "total_pagefile",
                "available_pagefile",
                "total_virtual",
                "available_virtual",
                "available_extended",
            )
        ]

    class ProcessMemory(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "peak_working",
                "working",
                "peak_paged",
                "paged",
                "peak_nonpaged",
                "nonpaged",
                "pagefile",
                "peak_pagefile",
                "private",
            )
        ]

    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    process = kernel.GetCurrentProcess()
    kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
    kernel.GlobalMemoryStatusEx.restype = wintypes.BOOL
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if kernel.GlobalMemoryStatusEx(ctypes.byref(status)) and status.total > 0:
        available = int(status.available)
        memory = min(1.0, max(0.0, 1.0 - available / status.total))
        sources.append("windows_memory")
    counters = ProcessMemory()
    counters.cb = ctypes.sizeof(counters)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    private = None
    if psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        rss, private = int(counters.working), int(counters.private)
        sources.append("windows_rss")
    kernel.GetSystemTimes.argtypes = [ctypes.POINTER(wintypes.FILETIME)] * 3
    kernel.GetSystemTimes.restype = wintypes.BOOL
    idle, system, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if kernel.GetSystemTimes(ctypes.byref(idle), ctypes.byref(system), ctypes.byref(user)):

        def ticks(value: Any) -> int:
            return int(value.dwHighDateTime) << 32 | int(value.dwLowDateTime)

        cpu = _cpu_counter_sample(
            "windows_system", float(ticks(system) + ticks(user)), idle=float(ticks(idle))
        )
        sources.append("windows_cpu" if cpu is not None else "windows_cpu_warming")
    reported_cpus = os.cpu_count()
    host_capacity = float(reported_cpus) if type(reported_cpus) is int and reported_cpus > 0 else None
    process_capacity = host_capacity
    kernel.GetProcessAffinityMask.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel.GetProcessAffinityMask.restype = wintypes.BOOL
    process_mask, system_mask = ctypes.c_size_t(), ctypes.c_size_t()
    if (
        kernel.GetProcessAffinityMask(process, ctypes.byref(process_mask), ctypes.byref(system_mask))
        and process_mask.value
    ):
        mask_capacity = float(bin(process_mask.value).count("1"))
        process_capacity = mask_capacity if process_capacity is None else min(process_capacity, mask_capacity)
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    created, exited, process_system, process_user = (wintypes.FILETIME() for _ in range(4))
    if process_capacity is not None and kernel.GetProcessTimes(
        process,
        ctypes.byref(created),
        ctypes.byref(exited),
        ctypes.byref(process_system),
        ctypes.byref(process_user),
    ):

        def seconds(value: Any) -> float:
            return ((int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)) / 10_000_000.0

        process_cpu = _cpu_counter_sample(
            "windows_process_" + str(process_capacity),
            seconds(process_system) + seconds(process_user),
            capacity=process_capacity,
        )
        if process_cpu is not None:
            cpu = process_cpu if cpu is None else max(cpu, process_cpu)
    kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    kernel.IsProcessInJob.restype = wintypes.BOOL
    in_job = wintypes.BOOL()
    if not kernel.IsProcessInJob(process, None, ctypes.byref(in_job)):
        return ServingResources(None, None, rss, None, ",".join(sources + ["windows_job_unknown"]))
    if in_job.value:

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_longlong),
                ("job_time", ctypes.c_longlong),
                ("flags", wintypes.DWORD),
                ("minimum_working", ctypes.c_size_t),
                ("maximum_working", ctypes.c_size_t),
                ("active_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("basic", BasicLimits),
                ("io", ctypes.c_ulonglong * 6),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        class Accounting(ctypes.Structure):
            _fields_ = [
                ("user", ctypes.c_longlong),
                ("system", ctypes.c_longlong),
                ("period_user", ctypes.c_longlong),
                ("period_system", ctypes.c_longlong),
                ("faults", wintypes.DWORD),
                ("total", wintypes.DWORD),
                ("active", wintypes.DWORD),
                ("terminated", wintypes.DWORD),
            ]

        kernel.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel.QueryInformationJobObject.restype = wintypes.BOOL

        def query(kind: int, value: Any) -> bool:
            return bool(
                kernel.QueryInformationJobObject(None, kind, ctypes.byref(value), ctypes.sizeof(value), None)
            )

        limits = ExtendedLimits()
        limits_known = query(9, limits)
        if limits_known:
            requirements: list[tuple[int, int | None]] = []
            if limits.basic.flags & 0x100:
                requirements.append((int(limits.process_memory), private))
            if limits.basic.flags & 0x200:
                usage = (ctypes.c_ulonglong * 2)()
                requirements.append((int(limits.job_memory), int(usage[0]) if query(28, usage) else None))
            unknown = False
            for limit, used in requirements:
                if limit <= 0 or used is None:
                    unknown = True
                    continue
                remaining = max(0, limit - used)
                available = remaining if available is None else min(available, remaining)
                fraction = min(1.0, max(0.0, used / limit))
                memory = fraction if memory is None else max(memory, fraction)
            if unknown:
                memory = available = None
                sources.append("windows_job_memory_unknown")
            elif requirements:
                sources.append("windows_job_memory")
        else:
            memory = available = None
            sources.append("windows_job_memory_unknown")
        rate = (wintypes.DWORD * 2)()
        accounting = Accounting()
        if query(15, rate) and query(1, accounting):
            flags, raw_rate = int(rate[0]), int(rate[1])
            # Job accounting covers all its processes. Use the job's own
            # affinity and ceiling rather than one member's process mask.
            capacity = host_capacity
            if not limits_known:
                capacity = None
            elif limits.basic.flags & 0x10:
                job_cpus = float(bin(limits.basic.affinity).count("1"))
                capacity = (
                    None if job_cpus <= 0 else (job_cpus if capacity is None else min(capacity, job_cpus))
                )
            if flags & 1 and flags & (4 | 0x10):
                maximum = (raw_rate >> 16) if flags & 0x10 else raw_rate
                if not 0 < maximum <= 10000 or host_capacity is None:
                    capacity = None
                else:
                    ceiling = host_capacity * maximum / 10000.0
                    capacity = None if capacity is None else min(capacity, ceiling)
            ratio = (
                None
                if capacity is None
                else _cpu_counter_sample(
                    "windows_job_" + str(capacity),
                    (accounting.user + accounting.system) / 10_000_000.0,
                    capacity=capacity,
                )
            )
            if ratio is not None:
                cpu = max(ratio, cpu) if cpu is not None else ratio
                sources.append("windows_job_cpu")
            else:
                cpu = None
                sources.append("windows_job_cpu_unknown" if capacity is None else "windows_job_cpu_warming")
        else:
            cpu = None
            sources.append("windows_job_cpu_unknown")
    return ServingResources(memory, cpu, rss, available, ",".join(sources) or "unavailable")


def _sample_darwin_resources() -> ServingResources:
    import ctypes

    memory = available = rss = cpu = None
    sources: list[str] = []
    library = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    library.mach_host_self.restype = ctypes.c_uint32
    task = ctypes.c_uint32.in_dll(library, "mach_task_self_").value
    library.mach_port_deallocate.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    library.mach_port_deallocate.restype = ctypes.c_int
    host = library.mach_host_self()
    try:
        library.host_statistics.argtypes = [
            ctypes.c_uint32,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        library.host_statistics.restype = ctypes.c_int
        cpu_ticks = (ctypes.c_uint32 * 4)()
        count = ctypes.c_uint32(4)
        if (
            library.host_statistics(host, 3, ctypes.byref(cpu_ticks), ctypes.byref(count)) == 0
            and count.value == 4
        ):
            cpu = _cpu_counter_sample("darwin_host", float(sum(cpu_ticks)), idle=float(cpu_ticks[2]))
            sources.append("darwin_cpu" if cpu is not None else "darwin_cpu_warming")

        class VMStatistics(ctypes.Structure):
            _fields_ = (
                [(name, ctypes.c_uint32) for name in ("free", "active", "inactive", "wired")]
                + [
                    (name, ctypes.c_uint64)
                    for name in (
                        "zero_fill",
                        "reactivations",
                        "pageins",
                        "pageouts",
                        "faults",
                        "cow",
                        "lookups",
                        "hits",
                    )
                ]
                + [
                    ("purgeable", ctypes.c_uint32),
                    ("purges", ctypes.c_uint64),
                    ("speculative", ctypes.c_uint32),
                ]
                + [
                    (name, ctypes.c_uint64)
                    for name in ("decompressions", "compressions", "swapins", "swapouts")
                ]
                + [(name, ctypes.c_uint32) for name in ("compressor", "throttled", "external", "internal")]
                + [("uncompressed", ctypes.c_uint64)]
            )

        library.host_statistics64.argtypes = [
            ctypes.c_uint32,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        library.host_statistics64.restype = ctypes.c_int
        library.host_page_size.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
        library.host_page_size.restype = ctypes.c_int
        library.sysctlbyname.argtypes = [
            ctypes.c_char_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_void_p,
            ctypes.c_size_t,
        ]
        library.sysctlbyname.restype = ctypes.c_int
        statistics, page_size, total = VMStatistics(), ctypes.c_uint32(), ctypes.c_uint64()
        count, total_size = ctypes.c_uint32(ctypes.sizeof(statistics) // 4), ctypes.c_size_t(
            ctypes.sizeof(total)
        )
        if (
            library.host_statistics64(host, 4, ctypes.byref(statistics), ctypes.byref(count)) == 0
            and library.host_page_size(host, ctypes.byref(page_size)) == 0
            and library.sysctlbyname(b"hw.memsize", ctypes.byref(total), ctypes.byref(total_size), None, 0)
            == 0
            and total.value > 0
            and page_size.value > 0
        ):
            available = min(
                int(total.value), int(statistics.free + statistics.inactive) * int(page_size.value)
            )
            memory = 1.0 - available / total.value
            sources.append("darwin_memory")

        class TaskBasicInfo(ctypes.Structure):
            _fields_ = [
                ("virtual", ctypes.c_uint64),
                ("resident", ctypes.c_uint64),
                ("maximum_resident", ctypes.c_uint64),
                ("user_seconds", ctypes.c_int32),
                ("user_microseconds", ctypes.c_int32),
                ("system_seconds", ctypes.c_int32),
                ("system_microseconds", ctypes.c_int32),
                ("policy", ctypes.c_int32),
                ("suspend_count", ctypes.c_int32),
            ]

        library.task_info.argtypes = [
            ctypes.c_uint32,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        library.task_info.restype = ctypes.c_int
        info = TaskBasicInfo()
        count = ctypes.c_uint32(ctypes.sizeof(info) // 4)
        if library.task_info(task, 20, ctypes.byref(info), ctypes.byref(count)) == 0:
            rss = int(info.resident)
            sources.append("darwin_rss")
        return ServingResources(memory, cpu, rss, available, ",".join(sources) or "unavailable")
    finally:
        library.mach_port_deallocate(task, host)


def sample_serving_resources() -> ServingResources:
    """Sample fresh native counters; preserve unavailable restriction signals."""
    global _RESOURCE_COLLECTION
    with _RESOURCE_COLLECTION_LOCK:
        now = time.monotonic()
        if _RESOURCE_COLLECTION is not None and now - _RESOURCE_COLLECTION[0] < 0.2:
            return _RESOURCE_COLLECTION[1]
        try:
            if os.name == "nt":
                measured = _sample_windows_resources()
            elif sys.platform == "darwin":
                measured = _sample_darwin_resources()
            elif sys.platform.startswith("linux"):
                measured = _sample_linux_resources()
            else:
                measured = ServingResources(source="platform_telemetry_unavailable")
        except (OSError, ValueError, AttributeError, ImportError):
            measured = ServingResources(source="platform_telemetry_unavailable")
        _RESOURCE_COLLECTION = (now, measured)
        return measured


def _local_protocol_capabilities(model: LocalModelBackend) -> tuple[str, ...]:
    supplied = getattr(model, "protocol_capabilities", ("text-generation",))
    if (
        not isinstance(supplied, (tuple, list))
        or not 1 <= len(supplied) <= 3
        or any(type(value) is not str for value in supplied)
        or len(set(supplied)) != len(supplied)
        or set(supplied) - {"text-generation", "tool-calls", "structured-output"}
    ):
        raise ProviderPolicyError("local model protocol capabilities are invalid")
    return tuple(supplied)


def _validated_generation_limits(limits: dict[str, Any]) -> dict[str, Any]:
    try:
        LocalInputBudget.from_limits(limits)
    except LocalInputBudgetError as exc:
        raise ProviderPolicyError(str(exc)) from exc
    for name in ("tokenizer", "limits_source"):
        value = limits.get(name)
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 256
            or any(ord(character) < 32 for character in value)
        ):
            raise ProviderPolicyError("activated local generation-limit metadata is invalid")
    return limits


def _local_generation_limits(
    model: LocalModelBackend,
    *,
    verify_identity: bool = True,
) -> dict[str, Any]:
    """Resolve limits from the activated backend, rather than a catalog guess."""
    resolve = getattr(model, "generation_limits", None)
    declared = getattr(model, "_declared_generation_limits", None)
    if not verify_identity and callable(declared):
        # Native configuration inspection need not serialize/hash all model
        # weights. Actual dispatch/cache admission retains identity checks.
        resolve = declared
    if callable(resolve):
        supplied = resolve()
        if not isinstance(supplied, Mapping):
            raise ProviderPolicyError("activated local generation limits must be an object")
        context = supplied.get("context_window")
        output = supplied.get("max_output_tokens")
        total = supplied.get("max_total_tokens")
        if (
            type(context) is not int
            or context < 1
            or type(output) is not int
            or output < 1
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
        maximum_bytes = supplied.get("max_output_utf8_bytes")
        if maximum_bytes is not None:
            if type(maximum_bytes) is not int or maximum_bytes < 1:
                raise ProviderPolicyError("activated local output byte limit is invalid")
            limits["max_output_utf8_bytes"] = min(maximum_bytes, 4 * 1024 * 1024)
        return _validated_generation_limits(limits)
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
    if type(output) is not int or output < 1 or (total is not None and (type(total) is not int or total < 1)):
        raise ProviderPolicyError("activated local generation limits are invalid")
    # GGUF CLI admission conservatively reserves completion in its context;
    # native runtimes retain their explicit sliding-context/total limits.
    shared_context = native_limits is None and getattr(config, "context_size", None) is not None
    return _validated_generation_limits(
        {
            "context_window": context,
            "max_output_tokens": min(8_192, output, max(1, context // 2)),
            "max_total_tokens": context if shared_context else total,
            "shared_context": shared_context,
            "tokenizer": getattr(model, "tokenizer_kind", "utf8_bytes_upper_bound"),
            "limits_source": "activated_local_backend" if declared_context else "engine_chat_policy",
        }
    )


class LocalInferenceEngine:
    """Process-bounded workers with disposable tenant and operation queues.

    Scope identifiers are host-supplied authority, never inferred from model
    text. Tenant fairness, operation preemption and cache provenance remain
    separate; telemetry exposes only aggregate counts. Reducing limits gates
    future grants while every existing OS worker retains its reservation.
    """

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
        self._serving = AdaptiveServingController(max_concurrency, max_queue_size)
        self._tickets: OrderedDict[int, _ServingTicket] = OrderedDict()
        self._interactive_tickets: OrderedDict[int, _ServingTicket] = OrderedDict()
        self._background_tickets: OrderedDict[int, _ServingTicket] = OrderedDict()
        self._running: dict[int, _ServingTicket] = {}
        self._tenant_active: Counter[str] = Counter()
        self._tenant_queued: Counter[str] = Counter()
        self._operation_active: Counter[tuple[str, str]] = Counter()
        self._operation_queued: Counter[tuple[str, str]] = Counter()
        self._tenant_queues: dict[
            str, OrderedDict[str, OrderedDict[str, OrderedDict[int, _ServingTicket]]]
        ] = {
            "interactive": OrderedDict(),
            "background": OrderedDict(),
        }
        self._schedule_version = 0
        self._selected_version = -1
        self._selected_sequence: int | None = None
        self._selection_expires_at = 0.0
        self._fairness_rotations = 0
        self._operation_rotations = 0
        self._aged_background_admissions = 0
        self._tenant_limit_rejections = 0
        self._operation_limit_rejections = 0
        self._memory_shed_rejections = 0
        self._load_shed_rejections = 0
        self._max_queue_wait_ms = 0.0
        self._interactive_grants_since_background = 0
        self._preemption_deferrals = 0
        self._reserved_memory_bytes = 0
        self._memory_headroom_waits = 0
        self._next_ticket = 0
        self._draining = False
        self._closed = False
        self._preemptions = 0
        self._queue_expired = 0
        self._cache_bytes = 0
        self._cache_evictions = 0
        self._cache_expirations = 0
        self._identity_invalidations = 0
        self._cache_identity: str | None = None
        self._singleflight: dict[
            tuple[str, asyncio.AbstractEventLoop, int | None, int | None],
            asyncio.Future[LocalInferenceResult],
        ] = {}
        self._singleflight_hits = 0
        self._singleflight_waiters = 0
        self._singleflight_tenants: Counter[str] = Counter()
        self._cache_epoch = 0
        self._active = 0
        self._queued = 0
        self._completed = 0
        self._failed = 0
        self._cancelled = 0
        self._overloaded = 0
        self._cache_hits = 0
        self._preflight_active = 0
        self._preflight_completed = 0
        self._preflight_elapsed_ms = 0.0

    def _sample_pressure_locked(self, now: float) -> None:
        if self._serving.sample_due(now):
            self._serving.update(sample_serving_resources(), now=now, queued=self._queued)
            self._schedule_version += 1
            if self._memory_shedding_locked():
                for ticket in tuple(self._tickets.values()):
                    self._retire_queued_locked(ticket, "memory_pressure")
                    self._memory_shed_rejections += 1
                    self._overloaded += 1
            else:
                self._enforce_queue_limits_locked()

    def _memory_shedding_locked(self) -> bool:
        memory = self._serving.resources.memory_used_fraction
        return memory is not None and memory >= self._serving.policy.memory_shed_watermark

    def _memory_headroom_locked(self, ticket: _ServingTicket) -> bool:
        available = self._serving.resources.available_memory_bytes
        if not ticket.estimated_memory_bytes or available is None:
            return True
        # Reserve the conservative native KV estimate until physical drain.
        # Available memory already reflects some live allocations; counting
        # outstanding reservations again intentionally leaves safety headroom.
        required = ticket.estimated_memory_bytes + self._reserved_memory_bytes + 32 * 1024 * 1024
        if required <= available:
            return True
        if not ticket.memory_wait_observed:
            ticket.memory_wait_observed = True
            self._memory_headroom_waits += 1
        return False

    def _effective_queue_limit_locked(self) -> int:
        if self._memory_shedding_locked():
            return 0
        if self._serving.policy.enabled and self._serving.level in {"critical", "elevated"}:
            return min(self.max_queue_size, max(1, self._serving.effective_concurrency * 8))
        return self.max_queue_size

    def _background_starvation_seconds_locked(self) -> float:
        return min(
            self._serving.policy.background_starvation_seconds,
            self._serving.policy.max_queue_wait_seconds * 0.5,
        )

    def _operation_queue_limit_locked(self) -> int:
        maximum = self._serving.policy.max_queued_per_tenant
        return max(1, maximum * 3 // 4) if maximum else 0

    def _background_queue_limit_locked(self) -> int:
        maximum = self.max_queue_size * 3 // 4
        if self._serving.policy.enabled and self._serving.level in {"critical", "elevated"}:
            maximum = min(maximum, self._serving.effective_concurrency * 2)
        return maximum

    def _enforce_queue_limits_locked(self) -> None:
        def reject(ticket: _ServingTicket, reason: str) -> None:
            self._retire_queued_locked(ticket, reason)
            self._overloaded += 1
            if reason == "tenant_capacity":
                self._tenant_limit_rejections += 1
            elif reason == "operation_capacity":
                self._operation_limit_rejections += 1
            else:
                self._load_shed_rejections += 1

        # Retire newest background work before interactive work. Every index
        # is bounded by the operator queue ceiling and pruned on removal.
        for operation, count in tuple(self._operation_queued.items()):
            excess = count - self._operation_queue_limit_locked()
            for work_class in ("background", "interactive"):
                if excess <= 0:
                    break
                operations = self._tenant_queues[work_class].get(operation[0])
                queue = None if operations is None else operations.get(operation[1])
                while queue and excess > 0:
                    reject(next(reversed(queue.values())), "operation_capacity")
                    excess -= 1
        for tenant, count in tuple(self._tenant_queued.items()):
            excess = count - self._serving.policy.max_queued_per_tenant
            for work_class in ("background", "interactive"):
                if excess <= 0:
                    break
                operations = self._tenant_queues[work_class].get(tenant)
                while operations and excess > 0:
                    queue = next(reversed(operations.values()))
                    reject(next(reversed(queue.values())), "tenant_capacity")
                    excess -= 1
        while len(self._background_tickets) > self._background_queue_limit_locked():
            reject(next(reversed(self._background_tickets.values())), "load_pressure")
        while self._queued > self._effective_queue_limit_locked():
            queue = self._background_tickets or self._interactive_tickets
            reject(next(reversed(queue.values())), "load_pressure")

    def _remove_queued_locked(self, ticket: _ServingTicket) -> bool:
        if self._tickets.pop(ticket.sequence, None) is None:
            return False
        self._interactive_tickets.pop(ticket.sequence, None)
        self._background_tickets.pop(ticket.sequence, None)
        self._queued -= 1
        tenant = ticket.tenant_scope_id
        self._tenant_queued[tenant] -= 1
        if self._tenant_queued[tenant] == 0:
            del self._tenant_queued[tenant]
        operation = (tenant, ticket.preemption_scope_id)
        self._operation_queued[operation] -= 1
        if self._operation_queued[operation] == 0:
            del self._operation_queued[operation]
        tenants = self._tenant_queues[ticket.work_class]
        operations = tenants.get(tenant)
        queue = None if operations is None else operations.get(ticket.preemption_scope_id)
        if queue is not None:
            queue.pop(ticket.sequence, None)
            if not queue:
                del operations[ticket.preemption_scope_id]
            if not operations:
                del tenants[tenant]
        self._schedule_version += 1
        return True

    def _retire_queued_locked(self, ticket: _ServingTicket, reason: str) -> None:
        if self._remove_queued_locked(ticket):
            ticket.retired = reason

    def _release_running_locked(self, ticket: _ServingTicket) -> None:
        if self._running.pop(ticket.sequence, None) is None:
            raise RuntimeError("local inference reservation released without ownership")
        self._active -= 1
        self._reserved_memory_bytes -= ticket.estimated_memory_bytes
        tenant = ticket.tenant_scope_id
        self._tenant_active[tenant] -= 1
        if self._tenant_active[tenant] == 0:
            del self._tenant_active[tenant]
        operation = (tenant, ticket.preemption_scope_id)
        self._operation_active[operation] -= 1
        if self._operation_active[operation] == 0:
            del self._operation_active[operation]
        self._schedule_version += 1

    def _class_candidate_locked(self, work_class: str, now: float) -> _ServingTicket | None:
        tenants = self._tenant_queues[work_class]
        best: _ServingTicket | None = None
        best_score: tuple[int, int] | None = None
        starvation = self._background_starvation_seconds_locked()
        for tenant in tuple(tenants):
            operations = tenants.get(tenant)
            if operations is None:
                continue
            active = self._tenant_active.get(tenant, 0)
            if active >= self._serving.policy.max_active_per_tenant:
                continue
            tenant_head: _ServingTicket | None = None
            operation_score: tuple[int, int] | None = None
            for operation in tuple(operations):
                queue = operations.get(operation)
                if queue is None:
                    continue
                head = None
                for candidate in tuple(queue.values()):
                    if candidate.deadline <= now:
                        self._retire_queued_locked(candidate, "deadline exceeded")
                        self._queue_expired += 1
                    elif not candidate.coalesced:
                        head = candidate
                        break
                if head is None:
                    continue
                if not self._memory_headroom_locked(head):
                    continue
                self._selection_expires_at = min(self._selection_expires_at, head.deadline)
                if head.deadline > now + 0.25:
                    self._selection_expires_at = min(self._selection_expires_at, head.deadline - 0.25)
                urgent = head.deadline - now <= 0.25
                if work_class == "background":
                    aged = now - head.enqueued_at >= starvation
                    if not aged:
                        self._selection_expires_at = min(self._selection_expires_at, head.enqueued_at + starvation)
                    urgent = urgent or aged
                score = (self._operation_active.get((tenant, operation), 0), 0 if urgent else 1)
                if operation_score is None or score < operation_score:
                    tenant_head, operation_score = head, score
            if tenant_head is None:
                continue
            assert operation_score is not None
            # Lowest active share wins; rotation breaks equal-share ties.
            # Deadline urgency is local to an otherwise equal active share.
            score = (active, operation_score[1])
            if best_score is None or score < best_score:
                best, best_score = tenant_head, score
        return best

    def _selected_ticket_locked(self, now: float) -> _ServingTicket | None:
        if self._selected_version == self._schedule_version and now < self._selection_expires_at:
            return self._tickets.get(self._selected_sequence)
        self._selection_expires_at = now + 1.0
        if self._draining or self._memory_shedding_locked() or self._active >= self._serving.effective_concurrency:
            selected = None
        else:
            interactive = self._class_candidate_locked("interactive", now)
            background_active = sum(item.work_class == "background" for item in self._running.values())
            background = None
            if background_active < self._serving.background_limit:
                background = self._class_candidate_locked("background", now)
            selected = interactive or background
            if interactive is not None and background is not None:
                aged = now - background.enqueued_at >= self._background_starvation_seconds_locked()
                urgent = background.deadline - now <= 0.25 and background.deadline < interactive.deadline
                foreground_urgent = interactive.deadline - now <= 0.25 and interactive.deadline < background.deadline
                if aged and not foreground_urgent and (self._interactive_grants_since_background >= 3 or urgent):
                    selected = background
        self._selected_sequence = None if selected is None else selected.sequence
        self._selected_version = self._schedule_version
        return selected

    def _try_admit_locked(self, ticket: _ServingTicket, now: float) -> bool:
        if ticket.started_at is not None:
            return True
        if self._selected_ticket_locked(now) is not ticket:
            return False
        if not self._memory_headroom_locked(ticket):
            return False
        now = time.monotonic()
        if now >= ticket.deadline:
            self._retire_queued_locked(ticket, "deadline exceeded")
            self._queue_expired += 1
            return False
        if not self._execution_slots.acquire(blocking=False):
            return False
        tenants = self._tenant_queues[ticket.work_class]
        competing_tenants = len(tenants) > 1
        competing_operations = len(tenants[ticket.tenant_scope_id]) > 1
        aged = ticket.work_class == "background" and (
            now - ticket.enqueued_at >= self._background_starvation_seconds_locked()
        )
        ticket.starvation_protected = aged
        self._remove_queued_locked(ticket)
        if ticket.tenant_scope_id in tenants:
            operations = tenants[ticket.tenant_scope_id]
            if ticket.preemption_scope_id in operations:
                operations.move_to_end(ticket.preemption_scope_id)
            tenants.move_to_end(ticket.tenant_scope_id)
        if competing_tenants:
            self._fairness_rotations += 1
        if competing_operations:
            self._operation_rotations += 1
        if ticket.work_class == "background":
            self._interactive_grants_since_background = 0
            if aged:
                self._aged_background_admissions += 1
        else:
            self._interactive_grants_since_background = min(3, self._interactive_grants_since_background + 1)
        self._active += 1
        self._reserved_memory_bytes += ticket.estimated_memory_bytes
        self._tenant_active[ticket.tenant_scope_id] += 1
        self._operation_active[(ticket.tenant_scope_id, ticket.preemption_scope_id)] += 1
        ticket.started_at = now
        self._running[ticket.sequence] = ticket
        self._max_queue_wait_ms = max(self._max_queue_wait_ms, (now - ticket.enqueued_at) * 1000.0)
        self._schedule_version += 1
        return True

    def _effective_cache_limit_locked(self) -> int:
        maximum = self._serving.policy.cache_max_bytes
        if not self._serving.policy.enabled:
            return maximum
        if self._serving.level == "critical":
            return 0
        return maximum // 2 if self._serving.level == "elevated" else maximum

    def batch_limits(self) -> _BatchLimits:
        """Intersect operator batch policy with the activated native runtime."""
        native = getattr(getattr(self.model, "runtime", None), "limits", None)
        maximum = getattr(native, "max_batch_size", None)
        tokens = getattr(native, "max_batch_tokens", None)
        for name, value in (("max_batch_size", maximum), ("max_batch_tokens", tokens)):
            if value is not None and (type(value) is not int or value < 1):
                raise ProviderPolicyError("activated local " + name + " is invalid")
        return {
            "max_batch_size": self.max_batch_size if maximum is None else min(self.max_batch_size, maximum),
            "max_batch_tokens": tokens,
        }

    def execution_contract(self, *, model_id: str | None = None) -> dict[str, Any]:
        """Describe activated ceilings without tokenization or execution.

        This is a bounded configuration projection, not a readiness receipt,
        capacity reservation, throughput promise or independent model review.
        Catalog callers can bind a route alias while preserving the real source
        identity. Dynamic serving pressure is deliberately outside this digest.
        """
        source_model_id = self.model.model_id
        selected_model_id = source_model_id if model_id is None else model_id
        for identity in (source_model_id, selected_model_id):
            if (
                not isinstance(identity, str)
                or not identity
                or identity != identity.strip()
                or any(ord(character) < 32 for character in identity)
                or len(identity.encode("utf-8", errors="strict")) > 256
            ):
                raise ProviderPolicyError("local execution contract model identity is invalid")
        model_digest = self.model.model_digest
        declared = getattr(self.model, "_declared_generation_limits", None)
        runtime_digest = (
            getattr(self.model, "_runtime_digest", None)
            if callable(declared)
            else getattr(self.model, "runtime_digest", None)
        )
        profile_digest = getattr(self.model, "execution_profile_digest", None)
        for name, value in (
            ("model", model_digest),
            ("runtime", runtime_digest),
            ("profile", profile_digest),
        ):
            if value is None and name != "model":
                continue
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ProviderPolicyError("local execution contract " + name + " digest is invalid")
        limits = _local_generation_limits(self.model, verify_identity=False)
        # The same validator owns numeric ceilings during actual preparation.
        LocalInputBudget.from_limits(limits)
        batch = self.batch_limits()
        if batch["max_batch_tokens"] is not None and batch["max_batch_tokens"] > 9_007_199_254_740_991:
            raise ProviderPolicyError("local execution contract batch token ceiling is invalid")
        protocols = _local_protocol_capabilities(self.model)
        counter = callable(getattr(self.model, "count_input_tokens", None))
        prepared = all(
            callable(getattr(self.model, name, None))
            for name in (
                "prepare_input",
                "validate_prepared_input",
                "infer_prepared",
            )
        )
        tokenizer = limits["tokenizer"]
        exact: bool | None
        if tokenizer in {"native_tokenizer", "utf8_byte_tokens", "reference_tokens"} and counter:
            basis, exact = tokenizer, True
        elif tokenizer == "utf8_bytes_upper_bound" or not counter:
            basis, exact = "conservative_utf8_bytes", False
        else:
            basis, exact = "backend_token_counter", None
        contract = {
            "schema_version": "skeleton.local_inference.execution_contract.v1",
            "provider_id": "local",
            "model_id": selected_model_id,
            "source_model_id": source_model_id,
            "model_digest": model_digest,
            "runtime_digest": runtime_digest,
            "execution_profile_digest": profile_digest,
            "generation_limits": limits,
            "protocols": list(protocols),
            "input_accounting": {"basis": basis, "exact": exact, "prepared_input": prepared},
            "capacity": {
                "max_concurrency": self.max_concurrency,
                "max_queue_size": self.max_queue_size,
                "max_batch_size": batch["max_batch_size"],
                "max_batch_tokens": batch["max_batch_tokens"],
            },
            "lifecycle": {
                "cooperative_cancellation": True,
                "deadline_includes_preparation": True,
                "worker_slot_released_on_physical_drain": True,
                "cache_is_scope_bound": True,
                "preparation_admission_owner": "local_inference_engine",
                "preparation_runs_off_event_loop": True,
                "coalescing_pins_resource_ceilings": True,
                "permanent_close_waits_for_physical_drain": True,
            },
        }
        contract["contract_digest"] = _digest(contract)
        return contract

    def snapshot(self) -> dict[str, Any]:
        """Return bounded operational counts without prompts or model output."""
        memory_source = getattr(self.model, "memory_estimate_source", None)
        if not isinstance(memory_source, str) or memory_source not in {
            "gguf_process_weights_scratch_and_kv", "gguf_process_weights_scratch_kv_unknown",
        }:
            memory_source = "native_kv_upper_bound_when_available"
        batch_limits = self.batch_limits()
        with self._capacity_lock:
            now = time.monotonic()
            self._sample_pressure_locked(now)
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
                    "per_tenant_active_limit": min(
                        self._serving.policy.max_active_per_tenant,
                        self._serving.effective_concurrency,
                    ),
                    "per_tenant_queue_limit": self._serving.policy.max_queued_per_tenant,
                    "per_operation_queue_limit": self._operation_queue_limit_locked(),
                    "effective_queue_limit": self._effective_queue_limit_locked(),
                    "reserved_memory_bytes": self._reserved_memory_bytes,
                    "memory_estimated_active": sum(
                        bool(item.estimated_memory_bytes) for item in self._running.values()
                    ),
                    "effective_max_batch_size": batch_limits["max_batch_size"],
                    "effective_max_batch_tokens": batch_limits["max_batch_tokens"],
                },
                "pressure": self._serving.pressure_snapshot(),
                "fairness": {
                    "active_tenants": len(self._tenant_active),
                    "queued_tenants": len(self._tenant_queued),
                    "active_operations": len(self._operation_active),
                    "queued_operations": len(self._operation_queued),
                    "largest_tenant_active": max(self._tenant_active.values(), default=0),
                    "largest_tenant_queued": max(self._tenant_queued.values(), default=0),
                    "rotations": self._fairness_rotations,
                    "operation_rotations": self._operation_rotations,
                    "aged_background_admissions": self._aged_background_admissions,
                    "preemption_deferrals": self._preemption_deferrals,
                    "tenant_limit_rejections": self._tenant_limit_rejections,
                    "operation_limit_rejections": self._operation_limit_rejections,
                    "memory_shed_rejections": self._memory_shed_rejections,
                    "load_shed_rejections": self._load_shed_rejections,
                    "oldest_interactive_wait_ms": (
                        (now - next(iter(self._interactive_tickets.values())).enqueued_at) * 1000.0
                        if self._interactive_tickets
                        else 0.0
                    ),
                    "oldest_background_wait_ms": (
                        (now - next(iter(self._background_tickets.values())).enqueued_at) * 1000.0
                        if self._background_tickets
                        else 0.0
                    ),
                    "max_observed_queue_wait_ms": self._max_queue_wait_ms,
                    "memory_shedding": self._memory_shedding_locked(),
                    "memory_headroom_waits": self._memory_headroom_waits,
                    "memory_estimate_source": memory_source,
                    "background_starvation_seconds": self._background_starvation_seconds_locked(),
                    "foreground_grants_between_background": 3,
                },
                "draining": self._draining,
                "closed": self._closed,
                "preflight": {
                    "active": self._preflight_active,
                    "completed": self._preflight_completed,
                    "elapsed_ms": self._preflight_elapsed_ms,
                    "admission_owner": "local_inference_engine",
                },
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
                "singleflight_tenants": len(self._singleflight_tenants),
                "largest_tenant_singleflight_waiters": max(self._singleflight_tenants.values(), default=0),
            }
        snapshot["serving"] = serving
        describe_backend = getattr(self.model, "execution_snapshot", None)
        if callable(describe_backend):
            backend = describe_backend()
            if not isinstance(backend, Mapping):
                raise ValueError("local backend execution snapshot must be an object")
            admitted: dict[str, Any] = {}
            kind = backend.get("kind")
            if isinstance(kind, str) and kind in {"llama_cpp_cli", "native_runtime", "native_transformer"}:
                admitted["kind"] = kind
            for name in (
                "active_processes", "draining_processes", "spawning_processes", "processes_started",
                "processes_exited", "termination_requests", "trained_context_tokens",
            ):
                value = backend.get(name)
                if value is None or (type(value) is int and 0 <= value < 2**63):
                    admitted[name] = value
            for name in ("trained_context_known", "kv_estimate_available"):
                if type(backend.get(name)) is bool:
                    admitted[name] = backend[name]
            source = backend.get("memory_estimate_source")
            if isinstance(source, str) and source in {"gguf_process_weights_scratch_and_kv", "gguf_process_weights_scratch_kv_unknown"}:
                admitted["memory_estimate_source"] = source
            snapshot["backend"] = admitted
        try:
            serving["execution_contract"] = self.execution_contract()
        except (OSError, ValueError, RuntimeError):
            # Runtime controls must remain readable after identity drift. This
            # sanitized observation never fabricates a usable model contract.
            serving["execution_contract"] = None
            serving["execution_contract_error"] = "activated_contract_unavailable"
        return snapshot

    def configure_serving(self, policy: Mapping[str, Any]) -> dict[str, Any]:
        """Change derived serving policy without changing activated identity."""
        with self._capacity_lock:
            self._serving.configure(policy, time.monotonic())
            self._schedule_version += 1
            self._enforce_queue_limits_locked()
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
                if self._closed and action == "resume":
                    raise LocalInferenceOverloaded("closed local inference cannot resume")
                self._draining = action == "drain"
                if self._draining:
                    for ticket in tuple(self._tickets.values()):
                        self._retire_queued_locked(ticket, "draining")
                    # Active workers keep their reservations and physical
                    # ownership until their own finally block completes.
                self._schedule_version += 1
        return self.snapshot()

    async def close(self, *, cancel_running: bool = True) -> None:
        """Permanently stop admissions and retain custody until workers drain.

        A noncooperative backend keeps its reservation until it actually
        exits. Cancelling this close requests cancellation of active work and
        defers propagation until physical drain; it cannot unload a live model.
        """
        if type(cancel_running) is not bool:
            raise TypeError("cancel_running must be boolean")
        with self._capacity_lock:
            self._closed = self._draining = True
            for ticket in tuple(self._tickets.values()):
                self._retire_queued_locked(ticket, "closed")
            if cancel_running:
                for ticket in self._running.values():
                    ticket.cancel.set()
            self._schedule_version += 1
        # Do not hold both locks across an await or invalidate model weights.
        # Epoch fencing prevents an already returned worker from repopulating
        # the disposable cache while its coroutine finishes publication.
        with self._cache_lock:
            self._cache_evictions += len(self._cache)
            self._cache.clear()
            self._cache_bytes = 0
            self._cache_epoch += 1
        cancelled = False
        while True:
            with self._capacity_lock:
                active = self._active
                if cancelled:
                    for ticket in self._running.values():
                        ticket.cancel.set()
            if not active:
                break
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                cancelled = True
        if cancelled:
            raise asyncio.CancelledError

    def _reserve(
        self,
        work_class: str,
        scope_id: str,
        preemption_scope_id: str,
        tenant_scope_id: str,
        deadline: float | None,
        cancel: threading.Event,
        *,
        coalesced: bool = False,
        estimated_memory_bytes: int = 0,
    ) -> _ServingTicket:
        now = time.monotonic()
        with self._capacity_lock:
            self._sample_pressure_locked(now)
            if self._draining:
                self._overloaded += 1
                raise LocalInferenceOverloaded("local inference is draining")
            if self._memory_shedding_locked():
                self._memory_shed_rejections += 1
                self._overloaded += 1
                raise LocalInferenceOverloaded("local inference admission shed for memory pressure")
            available = self._serving.resources.available_memory_bytes
            if (
                estimated_memory_bytes and available is not None and not self._active
                and estimated_memory_bytes + 32 * 1024 * 1024 > available
            ):
                self._memory_shed_rejections += 1
                self._overloaded += 1
                raise LocalInferenceOverloaded("local native KV estimate exceeds available memory headroom")
            queue_deadline = now + self._serving.policy.max_queue_wait_seconds
            if deadline is not None:
                queue_deadline = min(queue_deadline, deadline)
            if queue_deadline <= now:
                self._queue_expired += 1
                raise LocalInferenceCancelled("local inference queue deadline exceeded")
            if work_class == "background" and self._serving.policy.background_max_concurrency == 0:
                self._overloaded += 1
                raise LocalInferenceOverloaded("local background inference is paused")
            queue_limit = self._effective_queue_limit_locked()
            tenant_queue_limit = self._serving.policy.max_queued_per_tenant
            full = self._queued >= queue_limit or self._tenant_queued.get(tenant_scope_id, 0) >= tenant_queue_limit
            if full and work_class == "interactive" and not coalesced:
                # Replace queued work only inside the same authority scope.
                victim = next((item for item in reversed(self._background_tickets.values()) if (
                    item.preemption_scope_id == preemption_scope_id
                    and item.tenant_scope_id == tenant_scope_id
                    and now - item.enqueued_at < self._background_starvation_seconds_locked()
                    and item.deadline - now > 0.25
                )), None)
                if victim is not None:
                    self._retire_queued_locked(victim, "preempted")
                    self._preemptions += 1
            self._next_ticket += 1
            ticket = _ServingTicket(
                self._next_ticket, work_class, scope_id, preemption_scope_id,
                tenant_scope_id, now, queue_deadline, cancel,
            )
            ticket.coalesced = coalesced
            ticket.estimated_memory_bytes = estimated_memory_bytes
            self._tickets[ticket.sequence] = ticket
            priority_queue = self._interactive_tickets if work_class == "interactive" else self._background_tickets
            priority_queue[ticket.sequence] = ticket
            tenants = self._tenant_queues[work_class]
            operations = tenants.setdefault(tenant_scope_id, OrderedDict())
            operations.setdefault(preemption_scope_id, OrderedDict())[ticket.sequence] = ticket
            self._queued += 1
            self._tenant_queued[tenant_scope_id] += 1
            operation = (tenant_scope_id, preemption_scope_id)
            self._operation_queued[operation] += 1
            self._schedule_version += 1
            # Reserve an immediately usable slot atomically. A zero queue
            # budget permits immediate execution, never a hidden waiting job.
            if not coalesced and self._try_admit_locked(ticket, now):
                return ticket
            if ticket.retired is not None:
                return ticket
            tenant_full = self._tenant_queued[tenant_scope_id] > tenant_queue_limit
            operation_full = self._operation_queued[operation] > self._operation_queue_limit_locked()
            queue_full = self._queued > queue_limit
            background_queue_limit = self._background_queue_limit_locked()
            background_full = work_class == "background" and len(self._background_tickets) > background_queue_limit
            if tenant_full or operation_full or queue_full or background_full:
                self._retire_queued_locked(ticket, "capacity exceeded")
                self._overloaded += 1
                if tenant_full:
                    self._tenant_limit_rejections += 1
                    raise LocalInferenceOverloaded("local per-tenant waiting capacity is full")
                if operation_full:
                    self._operation_limit_rejections += 1
                    raise LocalInferenceOverloaded("local per-operation waiting capacity is full")
                if queue_full and queue_limit < self.max_queue_size:
                    self._load_shed_rejections += 1
                    raise LocalInferenceOverloaded("local inference waiting admission shed for load pressure")
                raise LocalInferenceOverloaded("local inference waiting capacity is full")
            if not coalesced and work_class == "interactive" and (
                self._active >= self._serving.effective_concurrency
                or self._tenant_active.get(tenant_scope_id, 0) >= self._serving.policy.max_active_per_tenant
            ):
                victim = next((item for item in self._running.values() if (
                    item.work_class == "background"
                    and item.preemption_scope_id == preemption_scope_id
                    and item.tenant_scope_id == tenant_scope_id
                    and not item.cancel.is_set()
                    and not item.starvation_protected
                )), None)
                if victim is not None:
                    victim.cancel.set()
                    self._preemptions += 1
                elif any(
                    item.work_class == "background" and item.preemption_scope_id == preemption_scope_id
                    and item.tenant_scope_id == tenant_scope_id and item.starvation_protected
                    for item in self._running.values()
                ):
                    self._preemption_deferrals += 1
            return ticket

    def _validate_backend_result(
        self,
        request: LocalInferenceRequest,
        result: LocalInferenceResult,
        prepared_input: LocalPreparedInput | None,
        admitted_input_tokens: int,
    ) -> LocalInferenceResult:
        # Reconstruct the canonical type: a faulty callback can return a
        # dataclass whose mutable nested data or scalar fields changed after
        # construction. No unvalidated payload reaches the cache or followers.
        result = LocalInferenceResult(
            **{name: getattr(result, name) for name in LocalInferenceResult.__dataclass_fields__}
        )
        limits = _local_generation_limits(self.model)
        budget = LocalInputBudget.from_limits(limits)
        budget.validate_tokens(result.input_tokens, request.max_output_tokens)
        if result.input_tokens > admitted_input_tokens:
            raise ProviderProtocolViolationError("local terminal input usage exceeds admitted accounting")
        maximum_bytes = limits.get("max_output_utf8_bytes", 4 * 1024 * 1024)
        payload_bytes = len((result.text or "").encode("utf-8"))
        if result.structured_output is not None:
            payload_bytes += len(_stable_json(dict(result.structured_output)).encode("utf-8"))
        for call in result.tool_calls:
            payload_bytes += len(call.call_id.encode("utf-8")) + len(call.tool_id.encode("utf-8"))
            payload_bytes += len(_stable_json(dict(call.arguments)).encode("utf-8"))
            if payload_bytes > maximum_bytes:
                break
        if payload_bytes > maximum_bytes:
            raise ProviderProtocolViolationError("local result exceeds activated output-byte limit")
        if result.model_id != self.model.model_id or result.model_digest != self.model.model_digest:
            raise ValueError("local inference result model identity drift")
        if prepared_input is not None and result.input_tokens != prepared_input.input_tokens:
            raise ProviderProtocolViolationError("local result differs from admitted native input accounting")
        if result.output_tokens > request.max_output_tokens:
            raise ProviderProtocolViolationError("local backend exceeded admitted output-token limit")

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

        return result

    def _infer_admitted(
        self,
        request: LocalInferenceRequest,
        cancel: threading.Event,
        started: threading.Event,
        ticket: _ServingTicket,
        prepared_input: LocalPreparedInput | None = None,
        admitted_input_tokens: int = 0,
    ) -> LocalInferenceResult:
        started.set()
        failed = False
        try:
            if cancel.is_set():
                raise LocalInferenceCancelled("local inference cancelled before execution")
            if prepared_input is None:
                result = self.model.infer(request, cancel)
            else:
                # Keep native tokenization and accounting attached to the
                # physical worker; this value never enters the output cache.
                if (
                    prepared_input.scope_digest != ticket.scope_id
                    or prepared_input.request_digest != request.digest
                ):
                    raise ProviderPolicyError("prepared local input authority changed before dispatch")
                # The native owner validates its issuer, immutable sequence
                # and current execution identity at this dispatch boundary.
                result = self.model.infer_prepared(request, cancel, prepared_input)
            if not isinstance(result, LocalInferenceResult):
                raise TypeError("local backend must return LocalInferenceResult")
            result = self._validate_backend_result(request, result, prepared_input, admitted_input_tokens)
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
                self._release_running_locked(ticket)
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
                        if ticket.retired in {
                            "memory_pressure", "load_pressure", "tenant_capacity", "operation_capacity",
                        }:
                            raise LocalInferenceOverloaded("local inference queued admission shed: " + ticket.retired)
                        raise LocalInferenceCancelled("local inference queue " + ticket.retired)
                    if ticket.started_at is not None:
                        return
                    if now >= ticket.deadline:
                        self._retire_queued_locked(ticket, "deadline exceeded")
                        self._queue_expired += 1
                        raise LocalInferenceCancelled("local inference queue deadline exceeded")
                    if self._try_admit_locked(ticket, now):
                        return
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            with self._capacity_lock:
                self._remove_queued_locked(ticket)
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

    def _preflight_admitted(
        self,
        check: Callable[[], Any],
        ticket: _ServingTicket,
        started: threading.Event,
    ) -> Any:
        started.set()
        admitted_at = time.monotonic()
        with self._capacity_lock:
            self._preflight_active += 1
        try:
            if ticket.cancel.is_set():
                raise LocalInferenceCancelled("local input preflight cancelled")
            result = check()
            if ticket.cancel.is_set():
                raise LocalInferenceCancelled("local input preflight cancelled")
            with self._capacity_lock:
                self._preflight_completed += 1
            return result
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
                self._preflight_active -= 1
                self._preflight_elapsed_ms += (time.monotonic() - admitted_at) * 1000.0
                self._release_running_locked(ticket)
            self._execution_slots.release()

    async def _run_admitted_preflight(
        self,
        check: Callable[[], Any],
        *,
        work_class: str,
        scope_id: str,
        preemption_scope_id: str,
        tenant_scope_id: str,
        deadline: float | None,
    ) -> Any:
        """Own identity/token preparation in the same fair physical worker pool.

        Tokenizers and weight snapshots are synchronous and may be expensive.
        Moving them off the event loop must not create an unbounded executor
        queue or release a cancelled worker's reservation before it stops.
        """
        cancel = threading.Event()
        ticket = self._reserve(work_class, scope_id, preemption_scope_id, tenant_scope_id, deadline, cancel)
        await self._acquire_execution_slot(ticket)
        started = threading.Event()
        timeout = None
        try:
            worker = asyncio.create_task(asyncio.to_thread(self._preflight_admitted, check, ticket, started))
            if deadline is not None:
                timeout = asyncio.get_running_loop().call_later(
                    max(0.0, deadline - time.monotonic()), cancel.set,
                )
            result = await self._await_worker(worker, cancel)
        except BaseException:
            if not started.is_set():
                with self._capacity_lock:
                    self._release_running_locked(ticket)
                    self._failed += 1
                self._execution_slots.release()
            raise
        finally:
            if timeout is not None:
                timeout.cancel()
        if deadline is not None and time.monotonic() >= deadline:
            raise LocalInferenceCancelled("local input preflight deadline exceeded")
        return result

    def _prepare_admitted_request(
        self,
        request: LocalInferenceRequest,
        *,
        key: str,
        scope: str,
        scope_id: str | None,
        tenant_scope_id: str | None,
        prepared_input: LocalPreparedInput | None,
        resource_max_input_tokens: int | None = None,
        resource_max_output_tokens: int | None = None,
    ) -> tuple[LocalPreparedInput | None, int, int]:
        check = getattr(self.model, "check_readiness", None)
        if callable(check):
            check()
        if prepared_input is None:
            prepared_input = self.prepare_input(
                request,
                scope_id=scope_id,
                tenant_scope_id=tenant_scope_id,
            )
        else:
            self._validate_prepared_input(request, prepared_input, scope)
        input_tokens = self._validate_input_budget(
            request,
            prepared_input,
            resource_max_input_tokens=resource_max_input_tokens,
            resource_max_output_tokens=resource_max_output_tokens,
        )
        estimated_memory = self._request_memory_estimate(
            request,
            prepared_input,
            admitted_input_tokens=input_tokens,
        )
        if self._key(request, scope) != key:
            raise ProviderPolicyError("local execution identity changed during preparation")
        return prepared_input, input_tokens, estimated_memory

    def _model_identity(self, *, verify_identity: bool = True) -> str:
        # Native keys include admitted tokenizer, architecture and policy.
        # Full mutable-weight validation belongs to physical admission, never
        # to key derivation on the event loop or inside the cache lock.
        declared = getattr(self.model, "_declared_generation_limits", None)
        runtime_digest = (
            getattr(self.model, "_runtime_digest", None)
            if not verify_identity and callable(declared)
            else getattr(self.model, "runtime_digest", None)
        )
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
        # This derives a key only. Admitted preflight/cache-hit workers perform
        # full identity checks before a result may use it; deriving a key must
        # not serialize a native model on the event loop or under a cache lock.
        return _digest(
            {
                "identity": self._model_identity(verify_identity=False),
                "request": request.digest,
                "scope": scope_id,
            }
        )

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

    def prepare_input(
        self,
        request: LocalInferenceRequest,
        *,
        scope_id: str | None = None,
        tenant_scope_id: str | None = None,
    ) -> LocalPreparedInput | None:
        """Prepare native tokens once, sealed to trusted cache/tenant authority.

        Backends without native preparation retain their existing contract.
        The caller owns this value only for the lifetime of one request.
        """
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        for name, value in (("scope_id", scope_id), ("tenant_scope_id", tenant_scope_id)):
            if value is not None and (not isinstance(value, str) or not value or len(value) > 512):
                raise ValueError(f"{name} must be a non-empty bounded string")
        prepare = getattr(self.model, "prepare_input", None)
        if not callable(prepare):
            return None
        scope = _digest(
            {
                "cache_scope": scope_id or "local",
                "tenant_scope": tenant_scope_id or _ANONYMOUS_TENANT_SCOPE,
            }
        )
        prepared = prepare(request, scope_digest=scope)
        self._validate_prepared_input(request, prepared, scope)
        return prepared

    def _validate_prepared_input(
        self,
        request: LocalInferenceRequest,
        prepared: LocalPreparedInput,
        scope_digest: str,
    ) -> None:
        validate = getattr(self.model, "validate_prepared_input", None)
        infer = getattr(self.model, "infer_prepared", None)
        if not callable(validate) or not callable(infer):
            raise ProviderPolicyError("activated local backend does not admit prepared input")
        if (
            not isinstance(prepared, LocalPreparedInput)
            or prepared.request_digest != request.digest
            or prepared.scope_digest != scope_digest
        ):
            raise ProviderPolicyError("prepared local input authority or request mismatch")
        validate(request, prepared)

    def _validate_input_budget(
        self,
        request: LocalInferenceRequest,
        prepared_input: LocalPreparedInput | None = None,
        *,
        limits: Mapping[str, Any] | None = None,
        resource_max_input_tokens: int | None = None,
        resource_max_output_tokens: int | None = None,
    ) -> int:
        """Validate actual/declared accounting before any model worker starts."""
        budget = LocalInputBudget.from_limits(
            _local_generation_limits(self.model) if limits is None else limits
        )
        render = getattr(self.model, "_render_prompt", None)
        rendered = render(request) if callable(render) else request.rendered_input
        # Character and encoded-size checks precede even an activated counter.
        budget.validate_request(request, 0, rendered=rendered)
        counter = getattr(self.model, "count_input_tokens", None)
        if prepared_input is not None:
            tokens = prepared_input.input_tokens
        elif callable(counter):
            tokens = counter(request)
        else:
            tokens = len(rendered.encode("utf-8")) + 1
        budget.validate_tokens(
            tokens,
            request.max_output_tokens,
            resource_max_input_tokens=resource_max_input_tokens,
            resource_max_output_tokens=resource_max_output_tokens,
        )
        return tokens

    def _request_memory_estimate(
        self,
        request: LocalInferenceRequest,
        prepared_input: LocalPreparedInput | None = None,
        *,
        admitted_input_tokens: int | None = None,
    ) -> int:
        declared = getattr(self.model, "estimate_memory_bytes", None)
        if callable(declared):
            size = declared(request)
            if type(size) is not int or not 0 <= size < 2**63:
                raise ProviderPolicyError("local backend memory estimate is invalid")
            return size
        runtime = getattr(self.model, "runtime", None)
        estimate = getattr(runtime, "estimate_kv_bytes", None)
        limits = getattr(runtime, "limits", None)
        context = getattr(limits, "max_context", None)
        count = getattr(self.model, "count_input_tokens", None)
        if (
            not callable(estimate)
            or (prepared_input is None and admitted_input_tokens is None and not callable(count))
            or type(context) is not int
            or context < 1
        ):
            return 0
        input_tokens = (
            prepared_input.input_tokens
            if prepared_input is not None
            else admitted_input_tokens if admitted_input_tokens is not None else count(request)
        )
        if type(input_tokens) is not int or input_tokens < 0:
            raise ProviderPolicyError("local native memory admission received invalid token count")
        tokens = min(context, input_tokens + request.max_output_tokens)
        size = estimate(tokens)
        if type(size) is not int or not 0 <= size < 2**63:
            raise ProviderPolicyError("local native KV memory estimate is invalid")
        maximum = getattr(limits, "max_kv_bytes", None)
        if type(maximum) is int and size > maximum:
            raise ProviderPolicyError("local request exceeds activated native KV memory limit")
        return size

    async def _wait_coalesced(
        self,
        future: asyncio.Future[LocalInferenceResult],
        *,
        work_class: str,
        scope_id: str,
        preemption_scope_id: str,
        tenant_scope_id: str,
        deadline: float | None,
    ) -> LocalInferenceResult:
        # A duplicate is still a waiting request: use the same tenant,
        # operation and global pending budgets without acquiring an OS slot.
        ticket = self._reserve(
            work_class, scope_id, preemption_scope_id, tenant_scope_id,
            deadline, threading.Event(), coalesced=True,
        )
        waiter = asyncio.shield(future)
        try:
            while True:
                with self._capacity_lock:
                    now = time.monotonic()
                    self._sample_pressure_locked(now)
                    if ticket.retired is not None:
                        if ticket.retired in {
                            "memory_pressure", "load_pressure", "tenant_capacity", "operation_capacity",
                        }:
                            raise LocalInferenceOverloaded("local inference coalesced admission shed: " + ticket.retired)
                        raise LocalInferenceCancelled("local inference coalesced queue " + ticket.retired)
                    if now >= ticket.deadline:
                        self._retire_queued_locked(ticket, "deadline exceeded")
                        self._queue_expired += 1
                        raise LocalInferenceCancelled("local inference coalesced queue deadline exceeded")
                if waiter.done():
                    return replace(waiter.result())
                await asyncio.wait((waiter,), timeout=min(0.05, max(0.001, ticket.deadline - now)))
        except (asyncio.CancelledError, LocalInferenceCancelled):
            with self._capacity_lock:
                self._cancelled += 1
            raise
        finally:
            if not waiter.done():
                waiter.cancel()
            elif not waiter.cancelled():
                waiter.exception()
            with self._capacity_lock:
                self._max_queue_wait_ms = max(
                    self._max_queue_wait_ms, (time.monotonic() - ticket.enqueued_at) * 1000.0,
                )
                self._remove_queued_locked(ticket)

    async def generate(
        self,
        request: LocalInferenceRequest,
        *,
        work_class: str = "interactive",
        scope_id: str | None = None,
        preemption_scope_id: str | None = None,
        tenant_scope_id: str | None = None,
        deadline: float | None = None,
        prepared_input: LocalPreparedInput | None = None,
        resource_max_input_tokens: int | None = None,
        resource_max_output_tokens: int | None = None,
    ) -> LocalInferenceResult:
        """Generate within trusted tenant, cache and monotonic deadline scopes.

        Tenantless direct calls share the anonymous fairness bucket. A host
        adapter must derive explicit tenant scopes from validated authority,
        rather than allowing an operation to select a new fairness identity.
        """
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        if work_class not in {"interactive", "background"}:
            raise ValueError("local work_class must be interactive or background")
        for name, value in (
            ("scope_id", scope_id), ("preemption_scope_id", preemption_scope_id),
            ("tenant_scope_id", tenant_scope_id),
        ):
            if value is not None and (not isinstance(value, str) or not value or len(value) > 512):
                raise ValueError(f"{name} must be a non-empty bounded string")
        if deadline is not None and (
            isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or not math.isfinite(deadline)
        ):
            raise ValueError("local inference deadline must be finite monotonic seconds")
        if deadline is not None and deadline <= time.monotonic():
            raise LocalInferenceCancelled("local inference deadline exceeded")
        # Size and output checks are cheap and precede cache hashing or any
        # tokenizer callback. Cache hits retain their native preparation win.
        declared_budget = LocalInputBudget.from_limits(
            _local_generation_limits(self.model, verify_identity=False)
        )
        declared_budget.validate_request(
            request,
            0,
            resource_max_input_tokens=resource_max_input_tokens,
            resource_max_output_tokens=resource_max_output_tokens,
        )
        with self._capacity_lock:
            if self._draining:
                self._overloaded += 1
                raise LocalInferenceOverloaded("local inference is draining")
            if work_class == "background" and deadline is None:
                deadline = time.monotonic() + min(
                    3600.0, max(30.0, self._serving.policy.target_latency_ms / 1000.0 * 4),
                )
        tenant_scope = tenant_scope_id or _ANONYMOUS_TENANT_SCOPE
        preemption_scope = preemption_scope_id or scope_id or "local"
        scope = _digest({"cache_scope": scope_id or "local", "tenant_scope": tenant_scope})
        if prepared_input is not None and (
            not isinstance(prepared_input, LocalPreparedInput)
            or prepared_input.request_digest != request.digest
            or prepared_input.scope_digest != scope
        ):
            raise ProviderPolicyError("prepared local input authority or request mismatch")
        identity = self._model_identity(verify_identity=False)
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
                    await self._run_admitted_preflight(
                        admit_cached,
                        work_class=work_class,
                        scope_id=scope,
                        preemption_scope_id=preemption_scope,
                        tenant_scope_id=tenant_scope,
                        deadline=deadline,
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
                    declared_budget.validate_tokens(
                        cached.result.input_tokens,
                        request.max_output_tokens,
                        resource_max_input_tokens=resource_max_input_tokens,
                        resource_max_output_tokens=resource_max_output_tokens,
                    )
                    if deadline is not None and time.monotonic() >= deadline:
                        raise LocalInferenceCancelled("local cache result exceeded its request deadline")
                    with self._capacity_lock:
                        self._cache_hits += 1
                    return replace(cached.result, cached=True)

        loop = asyncio.get_running_loop()
        # An underfunded leader must not make an otherwise admissible request
        # fail merely because they share content. Cache entries remain content
        # scoped; in-flight failure sharing also pins the caller's ceilings.
        flight_key = (key, loop, resource_max_input_tokens, resource_max_output_tokens)
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
                    self._singleflight_tenants[tenant_scope] += 1
                    self._singleflight_hits += 1
        if overloaded:
            with self._capacity_lock:
                self._overloaded += 1
            raise LocalInferenceOverloaded("local inference in-flight waiter capacity is full")
        assert future is not None
        try:
            if not leader:
                result = await self._wait_coalesced(
                    future,
                    work_class=work_class,
                    scope_id=scope,
                    preemption_scope_id=preemption_scope,
                    tenant_scope_id=tenant_scope,
                    deadline=deadline,
                )
                declared_budget.validate_tokens(
                    result.input_tokens,
                    request.max_output_tokens,
                    resource_max_input_tokens=resource_max_input_tokens,
                    resource_max_output_tokens=resource_max_output_tokens,
                )
                return result
            try:
                # Only the leader prepares; cache hits and followers retain
                # their own grants without creating private token snapshots.
                prepared_input, admitted_input_tokens, estimated_memory = await self._run_admitted_preflight(
                    lambda: self._prepare_admitted_request(
                        request,
                        key=key,
                        scope=scope,
                        scope_id=scope_id,
                        tenant_scope_id=tenant_scope_id,
                        prepared_input=prepared_input,
                        resource_max_input_tokens=resource_max_input_tokens,
                        resource_max_output_tokens=resource_max_output_tokens,
                    ),
                    work_class=work_class,
                    scope_id=scope,
                    preemption_scope_id=preemption_scope,
                    tenant_scope_id=tenant_scope,
                    deadline=deadline,
                )
                if deadline is not None and time.monotonic() >= deadline:
                    raise LocalInferenceCancelled("local inference deadline exceeded during preparation")
                result = await self._generate_uncached(
                    request,
                    key=key,
                    scope_id=scope,
                    preemption_scope_id=preemption_scope,
                    work_class=work_class,
                    tenant_scope_id=tenant_scope,
                    deadline=deadline,
                    cache_epoch=epoch,
                    prepared_input=prepared_input,
                    admitted_input_tokens=admitted_input_tokens,
                    estimated_memory_bytes=estimated_memory,
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
                    self._singleflight_tenants[tenant_scope] -= 1
                    if self._singleflight_tenants[tenant_scope] == 0:
                        del self._singleflight_tenants[tenant_scope]

    async def _generate_uncached(
        self,
        request: LocalInferenceRequest,
        *,
        key: str,
        scope_id: str,
        preemption_scope_id: str,
        work_class: str,
        tenant_scope_id: str,
        deadline: float | None,
        cache_epoch: int,
        prepared_input: LocalPreparedInput | None,
        admitted_input_tokens: int,
        estimated_memory_bytes: int,
    ) -> LocalInferenceResult:
        cancel = threading.Event()
        ticket = self._reserve(
            work_class,
            scope_id,
            preemption_scope_id,
            tenant_scope_id,
            deadline,
            cancel,
            estimated_memory_bytes=estimated_memory_bytes,
        )
        await self._acquire_execution_slot(ticket)
        started = threading.Event()
        try:
            worker = asyncio.create_task(
                asyncio.to_thread(
                    self._infer_admitted,
                    request,
                    cancel,
                    started,
                    ticket,
                    prepared_input,
                    admitted_input_tokens,
                )
            )
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
                    self._release_running_locked(ticket)
                    self._failed += 1
                self._execution_slots.release()
            raise

        if self._key(request, scope_id) != key:
            raise ValueError("local runtime identity changed during inference")

        with self._capacity_lock:
            self._sample_pressure_locked(time.monotonic())
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
        tenant_scope_id: str | None = None,
        deadline: float | None = None,
    ) -> tuple[LocalInferenceResult, ...]:
        if not requests:
            return ()
        if work_class not in {"interactive", "background"}:
            raise ValueError("local work_class must be interactive or background")
        for name, value in (
            ("scope_id", scope_id),
            ("preemption_scope_id", preemption_scope_id),
            ("tenant_scope_id", tenant_scope_id),
        ):
            if value is not None and (not isinstance(value, str) or not value or len(value) > 512):
                raise ValueError(f"{name} must be a non-empty bounded string")
        if deadline is not None and (
            isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
            or not math.isfinite(deadline)
        ):
            raise ValueError("local inference deadline must be finite monotonic seconds")
        batch_limits = self.batch_limits()
        if len(requests) > batch_limits["max_batch_size"]:
            raise ValueError("local inference batch exceeds configured max_batch_size")
        if any(not isinstance(item, LocalInferenceRequest) for item in requests):
            raise TypeError("batch requires LocalInferenceRequest values")
        maximum_tokens = batch_limits["max_batch_tokens"]
        prepared_inputs: list[LocalPreparedInput | None] = [None] * len(requests)
        if maximum_tokens is not None:
            count = getattr(self.model, "count_input_tokens", None)
            if not callable(count):
                raise ProviderPolicyError("native batch admission requires its activated tokenizer")
            with self._capacity_lock:
                if work_class == "background" and deadline is None:
                    deadline = time.monotonic() + min(
                        3600.0,
                        max(30.0, self._serving.policy.target_latency_ms / 1000.0 * 4),
                    )
            tenant_scope = tenant_scope_id or _ANONYMOUS_TENANT_SCOPE
            preemption_scope = preemption_scope_id or scope_id or "local"
            scope = _digest({"cache_scope": scope_id or "local", "tenant_scope": tenant_scope})
            declared_budget = LocalInputBudget.from_limits(
                _local_generation_limits(self.model, verify_identity=False)
            )
            reserved_tokens = 0
            for index, request in enumerate(requests):
                if deadline is not None and time.monotonic() >= deadline:
                    raise LocalInferenceCancelled("local batch deadline exceeded before execution")
                declared_budget.validate_request(request, 0)
                key = self._key(request, scope)
                prepared, tokens, _estimated_memory = await self._run_admitted_preflight(
                    lambda: self._prepare_admitted_request(
                        request,
                        key=key,
                        scope=scope,
                        scope_id=scope_id,
                        tenant_scope_id=tenant_scope_id,
                        prepared_input=None,
                    ),
                    work_class=work_class,
                    scope_id=scope,
                    preemption_scope_id=preemption_scope,
                    tenant_scope_id=tenant_scope,
                    deadline=deadline,
                )
                prepared_inputs[index] = prepared
                reserved_tokens += tokens + request.max_output_tokens
                if reserved_tokens > maximum_tokens:
                    raise ProviderPolicyError("native batch exceeds its admitted aggregate token limit")
        with self._capacity_lock:
            self._sample_pressure_locked(time.monotonic())
            workers = min(
                len(requests), self._serving.effective_concurrency,
                self._serving.policy.max_active_per_tenant,
            )
        results: list[LocalInferenceResult | BaseException | None] = [None] * len(requests)
        next_index = 0

        async def consume() -> None:
            nonlocal next_index
            while next_index < len(requests):
                # No await separates assignment and increment on this loop.
                index = next_index
                next_index += 1
                try:
                    results[index] = await self.generate(
                        requests[index],
                        work_class=work_class,
                        scope_id=scope_id,
                        preemption_scope_id=preemption_scope_id,
                        tenant_scope_id=tenant_scope_id,
                        deadline=deadline,
                        prepared_input=prepared_inputs[index],
                    )
                except Exception as exc:  # noqa: BLE001 -- batch reports admitted outcomes in input order
                    results[index] = exc
                finally:
                    prepared_inputs[index] = None

        # A large native batch must not manufacture thousands of pending
        # requests or defeat the same tenant queue budgets as normal traffic.
        tasks = [asyncio.create_task(consume()) for _ in range(workers)]
        try:
            # A failed member must not detach still-running native workers.
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await _drain_inference_tasks(tasks)
            raise
        settled: list[LocalInferenceResult] = []
        for result in results:
            if isinstance(result, BaseException):
                raise result
            if not isinstance(result, LocalInferenceResult):
                raise RuntimeError("local inference batch did not settle all admitted members")
            settled.append(result)
        return tuple(settled)


async def _drain_inference_tasks(tasks: Sequence[asyncio.Task]) -> None:
    """Keep ownership through repeated cancellation until native cleanup ends."""
    drained = asyncio.gather(*tasks, return_exceptions=True)
    while not drained.done():
        try:
            await asyncio.shield(drained)
        except asyncio.CancelledError:
            continue
    drained.result()


class LocalInferenceScheduler:
    """Loop-bound submission facade using the engine's single fair queue.

    Native work is never staged in a second FIFO ahead of tenant admission.
    ``batch_window_ms`` remains an accepted legacy configuration value; new
    work is admitted immediately and explicit batches use bounded engine
    workers. Closing owns each accepted submission through physical drain.
    """

    def __init__(
        self,
        engine: LocalInferenceEngine,
        *,
        max_batch_size: int = 8,
        batch_window_ms: float = 2.0,
    ) -> None:
        if not isinstance(engine, LocalInferenceEngine):
            raise TypeError("engine must be LocalInferenceEngine")
        if type(max_batch_size) is not int or not 1 <= max_batch_size <= min(256, engine.max_batch_size):
            raise ValueError("scheduler max_batch_size exceeds engine batch bounds")
        if (
            isinstance(batch_window_ms, bool)
            or not isinstance(batch_window_ms, (int, float))
            or not math.isfinite(float(batch_window_ms))
            or not 0 <= batch_window_ms <= 1000
        ):
            raise ValueError("batch_window_ms must be in [0, 1000]")
        self.engine = engine
        self.max_batch_size = max_batch_size
        self.batch_window = float(batch_window_ms) / 1000.0
        self._inflight: set[asyncio.Future[None]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._close_task: asyncio.Task[None] | None = None
        self._closed = False

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise RuntimeError("local inference scheduler cannot cross event loops")
        return loop

    def _begin(self) -> asyncio.Future[None]:
        loop = self._ensure_loop()
        if self._closed:
            raise RuntimeError("local inference scheduler is closed")
        completed = loop.create_future()
        self._inflight.add(completed)
        return completed

    def _finish(self, completed: asyncio.Future[None]) -> None:
        self._inflight.discard(completed)
        if not completed.done():
            completed.set_result(None)

    async def submit(
        self,
        request: LocalInferenceRequest,
        *,
        work_class: str = "interactive",
        scope_id: str | None = None,
        preemption_scope_id: str | None = None,
        tenant_scope_id: str | None = None,
        deadline: float | None = None,
    ) -> LocalInferenceResult:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        completed = self._begin()
        try:
            # Await directly: cancellation remains attached to the engine's
            # real worker and no scheduler task can hide extra pending work.
            return await self.engine.generate(
                request, work_class=work_class, scope_id=scope_id,
                preemption_scope_id=preemption_scope_id,
                tenant_scope_id=tenant_scope_id, deadline=deadline,
            )
        finally:
            self._finish(completed)

    async def submit_many(
        self,
        requests: Sequence[LocalInferenceRequest],
        *,
        work_class: str = "interactive",
        scope_id: str | None = None,
        preemption_scope_id: str | None = None,
        tenant_scope_id: str | None = None,
        deadline: float | None = None,
    ) -> tuple[LocalInferenceResult, ...]:
        if len(requests) > self.max_batch_size:
            raise ValueError("scheduler batch exceeds configured max_batch_size")
        completed = self._begin()
        try:
            return await self.engine.generate_many(
                requests, work_class=work_class, scope_id=scope_id,
                preemption_scope_id=preemption_scope_id,
                tenant_scope_id=tenant_scope_id, deadline=deadline,
            )
        finally:
            self._finish(completed)

    def snapshot(self) -> dict[str, Any]:
        return {
            "closed": self._closed,
            "inflight_submissions": len(self._inflight),
            "max_batch_size": self.max_batch_size,
            "admission_owner": "local_inference_engine",
            "batch_mode": "bounded_engine_workers",
        }

    async def close(self) -> None:
        self._ensure_loop()
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(self._finish_close())
        try:
            await asyncio.shield(self._close_task)
        except asyncio.CancelledError:
            await _drain_inference_tasks([self._close_task])
            raise

    async def _finish_close(self) -> None:
        pending = tuple(self._inflight)
        if pending:
            drained = asyncio.gather(*pending, return_exceptions=True)
            while not drained.done():
                try:
                    await asyncio.shield(drained)
                except asyncio.CancelledError:
                    continue
            drained.result()


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
            with self.engine._capacity_lock:
                if self.engine._draining:
                    return False
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

    async def close(self, *, cancel_running: bool = True) -> None:
        """Unload this activated owner only after its physical workers stop."""
        await self.engine.close(cancel_running=cancel_running)

    @property
    def protocol_capabilities(self) -> tuple[str, ...]:
        return _local_protocol_capabilities(self.engine.model)

    def generation_limits(self) -> dict[str, Any]:
        """Describe activated limits; physical admission verifies native identity."""
        return _local_generation_limits(self.engine.model, verify_identity=False)

    def execution_contract(self) -> dict[str, Any]:
        """Return the exact configured route's bounded input/execution contract."""
        return self.engine.execution_contract(model_id=self.model)

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
        status["execution_contract"] = self.execution_contract()
        status["capacity"]["max_queue_size"] = self.engine.max_queue_size
        status["runtime"] = self.engine.snapshot()
        return status

    @property
    def runtime_digest(self) -> str | None:
        declared = getattr(self.engine.model, "_declared_generation_limits", None)
        value = (
            getattr(self.engine.model, "_runtime_digest", None)
            if callable(declared)
            else getattr(self.engine.model, "runtime_digest", None)
        )
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
        serving_deadline = time.monotonic() + remaining
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
        # Tenant fairness is deliberately independent of operation, context,
        # cache and preemption identities. A tenant cannot gain more capacity
        # by opening many operations, and all unowned traffic shares a bucket.
        effective_tenant = governance.tenant_id if governance is not None else request.tenant_id
        tenant_scope = _ANONYMOUS_TENANT_SCOPE if effective_tenant is None else _digest({"tenant": effective_tenant})
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
        remaining = serving_deadline - time.monotonic()
        if remaining <= 0:
            raise LocalInferenceCancelled("local inference deadline exceeded during preparation")
        try:
            result = await asyncio.wait_for(
                self.engine.generate(
                    local_request,
                    work_class=work_class,
                    scope_id=cache_scope,
                    preemption_scope_id=preemption_scope,
                    tenant_scope_id=tenant_scope,
                    deadline=serving_deadline,
                    resource_max_input_tokens=budget.max_input_tokens,
                    resource_max_output_tokens=budget.max_output_tokens,
                ),
                timeout=remaining,
            )
        except TimeoutError as exc:
            raise LocalInferenceCancelled("local inference deadline exceeded") from exc
        except LocalInputBudgetError as exc:
            raise ProviderPolicyError(str(exc)) from exc
        if time.monotonic() - started > budget.max_wall_seconds or (
            request.deadline is not None and datetime.now(UTC) >= request.deadline.astimezone(UTC)
        ):
            raise LocalInferenceCancelled("local inference completed after its admitted deadline")
        if result.input_tokens > budget.max_input_tokens:
            raise ProviderPolicyError("local result exceeded admitted input-token budget")
        if result.output_tokens > max_tokens:
            raise ProviderProtocolViolationError("local result exceeded admitted output-token budget")
        if len(result.tool_calls) > budget.max_tool_calls:
            raise ProviderPolicyError("local result exceeded admitted tool-call budget")
        maximum_bytes = limits.get("max_output_utf8_bytes")
        if maximum_bytes is not None:
            output_bytes = len((result.text or "").encode("utf-8"))
            if result.structured_output is not None:
                output_bytes += len(_stable_json(dict(result.structured_output)).encode("utf-8"))
            for call in result.tool_calls:
                output_bytes += len(call.call_id.encode("utf-8")) + len(call.tool_id.encode("utf-8"))
                output_bytes += len(_stable_json(dict(call.arguments)).encode("utf-8"))
                if output_bytes > maximum_bytes:
                    break
            if output_bytes > maximum_bytes:
                raise ProviderProtocolViolationError("local result exceeded activated output-byte limit")
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
