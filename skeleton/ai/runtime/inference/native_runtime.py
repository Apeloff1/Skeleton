"""Canonical FLGB native transformer as a LocalModelBackend.

This module is the convergence seam between the FLGB-02 native runtime and the
engine's existing provider-neutral local inference stack.  It deliberately
keeps ProviderRegistry, CognitiveExecutionRuntime, caching, governance, and
engine orchestration unchanged while replacing the legacy local artifact
backend with the same tokenizer/checkpoint/transformer runtime used by FLGB-02.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from collections.abc import Mapping
from typing import Any

from skeleton.ai.model_runtime import (
    GenerationConfig,
    GenerationResult,
    NativeLLMRuntime,
    ReplayReceipt,
    RuntimeContractError,
    RuntimeEvent,
    RuntimeUsage,
)
from skeleton.ai.model_runtime.runtime_contracts import RUNTIME_SCHEMA, digest_json
from skeleton.ai.model_runtime.tokenization import TokenSequence, TokenizerContractError
from skeleton.skills.tool_contract import (
    ToolContractError,
    validate_json_schema,
    validate_json_value,
)

from .local import (
    LocalInferenceCancelled,
    LocalInputBudget,
    LocalInputBudgetError,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalPreparedInput,
    LocalToolCall,
)

_MAX_OUTPUT_BYTES = 4 * 1024 * 1024


class NativeRuntimeBackendError(RuntimeError):
    """Native runtime could not satisfy the local inference contract."""


class _NativeStreamAudit:
    """Check bounded stream/terminal consistency before publishing native work.

    These checks establish that one owner's observable records agree. They
    confer no independent quality, correctness or promotion authority.
    """

    def __init__(self, runtime: NativeLLMRuntime, prompt: TokenSequence, config: GenerationConfig) -> None:
        self.runtime, self.prompt, self.config = runtime, prompt, config
        self.events: list[RuntimeEvent] = []
        self.generated_ids: list[int] = []
        self.generated_tokens: list[str] = []
        self.stopped = False
        self.completed = False
        self.output_bytes = 0
        self.config_digest = digest_json(config.to_dict())
        self.request_digest = digest_json(
            {
                "model_digest": runtime.model_digest,
                "tokenizer_digest": runtime.tokenizer.digest,
                "prompt_sequence_digest": prompt.digest,
                "config_digest": self.config_digest,
            }
        )

    @staticmethod
    def _text_size(text: str) -> int:
        if not isinstance(text, str) or len(text) > _MAX_OUTPUT_BYTES:
            raise RuntimeContractError("native stream text exceeds its output bound")
        size = 0
        try:
            for offset in range(0, len(text), 8192):
                size += len(text[offset : offset + 8192].encode("utf-8", errors="strict"))
                if size > _MAX_OUTPUT_BYTES:
                    raise RuntimeContractError("native stream text exceeds its output bound")
        except UnicodeError as exc:
            raise RuntimeContractError("native stream text is not valid UTF-8") from exc
        return size

    def observe(self, event: RuntimeEvent) -> None:
        if not isinstance(event, RuntimeEvent):
            raise RuntimeContractError("native decoder emitted an invalid event type")
        event = RuntimeEvent(**{name: getattr(event, name) for name in RuntimeEvent.__dataclass_fields__})
        if (
            self.completed
            or event.sequence != len(self.events)
            or len(self.events) >= self.config.max_new_tokens + 4
        ):
            raise RuntimeContractError("native decoder event sequence is invalid")
        if event.cache_tokens > self.runtime.limits.max_context:
            raise RuntimeContractError("native decoder cache accounting exceeds its context")
        self._text_size(event.text_delta)
        if not self.events:
            if (
                event.kind != "admitted"
                or event.token_id is not None
                or event.detail_digest != self.request_digest
            ):
                raise RuntimeContractError("native decoder admission event does not bind its request")
        elif len(self.events) == 1:
            if (
                event.kind != "prompt"
                or event.token_id is not None
                or event.detail_digest != self.prompt.digest
            ):
                raise RuntimeContractError("native decoder prompt event differs from admitted input")
        elif event.kind == "token":
            if (
                self.stopped
                or type(event.token_id) is not int
                or not 0 <= event.token_id < self.runtime.tokenizer.vocab_size
            ):
                raise RuntimeContractError("native decoder token event violates its stream state")
            if len(self.generated_ids) >= self.config.max_new_tokens:
                raise RuntimeContractError("native decoder exceeded its output-token budget")
            expected = digest_json(
                {
                    "request_digest": self.request_digest,
                    "ordinal": len(self.generated_ids) + 1,
                    "token_id": event.token_id,
                }
            )
            if event.detail_digest != expected:
                raise RuntimeContractError("native decoder token event digest differs")
            piece = self.runtime.tokenizer.token_text(event.token_id)
            self.output_bytes += self._text_size(piece) + int(bool(self.generated_ids))
            if self.output_bytes > _MAX_OUTPUT_BYTES:
                raise RuntimeContractError("native generation exceeds its output-byte budget")
            hidden = bool(self.config.stop_strings) or (
                event.token_id in self.config.stop_token_ids and not self.config.include_stop_tokens
            )
            if event.text_delta != ("" if hidden else piece):
                raise RuntimeContractError("native token text differs from its admitted tokenizer")
            self.generated_ids.append(event.token_id)
            self.generated_tokens.append(piece)
        elif event.kind == "stopped":
            if (
                self.stopped
                or not self.generated_ids
                or self.events[-1].kind != "token"
                or event.token_id != self.generated_ids[-1]
                or event.detail_digest != self.events[-1].detail_digest
                or event.text_delta
            ):
                raise RuntimeContractError("native decoder stop event has no matching generated token")
            self.stopped = True
        elif event.kind == "completed":
            if event.token_id is not None or event.detail_digest is None:
                raise RuntimeContractError("native decoder completion has no terminal receipt")
            self.completed = True
        else:
            raise RuntimeContractError("native decoder emitted an event outside its lifecycle")
        self.events.append(event)

    def validate(self, result: GenerationResult) -> None:
        if not isinstance(result, GenerationResult) or not self.completed:
            raise RuntimeContractError("native decoder terminated without a complete event stream")
        self._text_size(result.text)
        if not isinstance(result.finish_reason, str):
            raise RuntimeContractError("native terminal reason must be text")
        if (
            type(result.generated_ids) is not tuple
            or result.generated_ids != tuple(self.generated_ids)
            or type(result.generated_tokens) is not tuple
            or result.generated_tokens != tuple(self.generated_tokens)
            or result.prompt_sequence != self.prompt
            or type(result.events) is not tuple
            or result.events != tuple(self.events)
        ):
            raise RuntimeContractError("native terminal output differs from its actual streamed tokens")
        if not isinstance(result.usage, RuntimeUsage) or not isinstance(result.replay_receipt, ReplayReceipt):
            raise RuntimeContractError("native terminal usage or replay receipt has an invalid type")
        usage = RuntimeUsage(
            **{name: getattr(result.usage, name) for name in RuntimeUsage.__dataclass_fields__}
        )
        receipt = ReplayReceipt(
            **{name: getattr(result.replay_receipt, name) for name in ReplayReceipt.__dataclass_fields__}
        )
        if (
            usage.prompt_tokens != len(self.prompt.token_ids)
            or usage.generated_tokens != len(self.generated_ids)
            or usage.model_bytes != self.runtime.model_bytes
            or usage.kv_peak_bytes > self.runtime.limits.max_kv_bytes
        ):
            raise RuntimeContractError("native terminal usage differs from admitted runtime accounting")
        expected_output = digest_json(
            {"generated_ids": self.generated_ids, "text": result.text, "finish_reason": result.finish_reason}
        )
        if (
            receipt.model_digest != self.runtime.model_digest
            or receipt.tokenizer_digest != self.runtime.tokenizer.digest
            or receipt.architecture_digest != self.runtime.architecture.digest
            or receipt.device_digest != self.runtime.device.digest
            or receipt.request_digest != self.request_digest
            or receipt.config_digest != self.config_digest
            or receipt.seed != self.config.seed
            or receipt.output_digest != expected_output
            or self.events[-1].detail_digest != receipt.digest
        ):
            raise RuntimeContractError("native terminal replay receipt differs from observed execution")
        if (
            result.finish_reason not in {"completed", "length", "stop_token", "stop_string"}
            or self.stopped != (result.finish_reason in {"stop_token", "stop_string"})
            or result.finish_reason == "length"
            and len(self.generated_ids) != self.config.max_new_tokens
        ):
            raise RuntimeContractError("native terminal reason contradicts observed generation")
        visible = self.generated_ids
        if result.finish_reason == "stop_token":
            if not visible or visible[-1] not in self.config.stop_token_ids:
                raise RuntimeContractError("native stop token differs from the generation policy")
            if not self.config.include_stop_tokens:
                visible = visible[:-1]
        expected_text = self.runtime.tokenizer.decode_ids(visible)
        if result.finish_reason == "stop_string":
            matches = [expected_text.find(marker) for marker in self.config.stop_strings]
            matches = [position for position in matches if position >= 0]
            if not matches:
                raise RuntimeContractError("native string stop has no matching admitted delimiter")
            expected_text = expected_text[: min(matches)]
        if (
            result.text != expected_text
            or self.events[-1].text_delta != (result.text if self.config.stop_strings else "")
            or not isinstance(result.checkpoint_digest, str)
            or len(result.checkpoint_digest) != 64
            or any(character not in "0123456789abcdef" for character in result.checkpoint_digest)
        ):
            raise RuntimeContractError("native terminal text or checkpoint binding is invalid")


class NativeRuntimeLocalModel:
    """Expose NativeLLMRuntime through the LocalModelBackend protocol."""

    artifact_schema = RUNTIME_SCHEMA
    model_family = "native_transformer"
    protocol_capabilities = ("text-generation", "tool-calls", "structured-output")
    tokenizer_kind = "native_tokenizer"

    def __init__(self, runtime: NativeLLMRuntime) -> None:
        if not isinstance(runtime, NativeLLMRuntime):
            raise TypeError("runtime must be NativeLLMRuntime")
        self.runtime = runtime
        identity = runtime.model_identity
        self.model_id = identity.model_id
        self._admitted_model_id = self.model_id
        self._model_digest = runtime.model_digest
        self._runtime_digest = identity.identity_digest
        self._tokenizer_digest = runtime.tokenizer.digest
        self._preparation_issuer = object()

    @property
    def model_digest(self) -> str:
        return self._model_digest

    @property
    def runtime_digest(self) -> str:
        # LocalInferenceEngine consults runtime_digest before cache lookup,
        # making this the single fail-closed identity-validation boundary.
        self.assert_identity()
        return self._runtime_digest

    @property
    def tokenizer_digest(self) -> str:
        return self._tokenizer_digest

    @property
    def execution_profile_digest(self) -> str:
        return hashlib.sha256(
            self._stable_json(
                {
                    "schema": "skeleton.native.execution-profile.v1",
                    "runtime": self._runtime_digest,
                    "device": self.runtime.device.to_dict(),
                    "device_policy": self.runtime.device_policy.to_dict(),
                    "limits": self.runtime.limits.to_dict(),
                    "tokenizer_limits": {
                        name: getattr(self.runtime.tokenizer.limits, name)
                        for name in ("max_chars", "max_tokens", "max_chunks", "max_chunk_chars")
                    },
                }
            ).encode("utf-8")
        ).hexdigest()

    def assert_identity(self) -> None:
        """Reject mutable weight/tokenizer/runtime drift before cache or inference."""
        self.runtime.assert_model_unchanged()
        try:
            self.runtime.tokenizer.assert_unchanged()
        except TokenizerContractError as exc:
            raise NativeRuntimeBackendError("native tokenizer identity drift") from exc
        if self.model_id != self._admitted_model_id:
            raise NativeRuntimeBackendError("native model identifier drift")
        if self.runtime.model_digest != self._model_digest:
            raise NativeRuntimeBackendError("native model digest drift")
        if self.runtime.tokenizer.digest != self._tokenizer_digest:
            raise NativeRuntimeBackendError("native tokenizer digest drift")
        if self.runtime.model_identity.identity_digest != self._runtime_digest:
            raise NativeRuntimeBackendError("native runtime identity drift")

    def check_readiness(self) -> None:
        """Read admitted metadata/device availability without scanning weights.

        Full weight/tokenizer integrity remains mandatory in the admitted
        preparation and inference worker. This probe cannot attest those bytes.
        """
        device = self.runtime.device
        if (
            self.model_id != self._admitted_model_id
            or self.runtime.model_digest != self._model_digest
            or self.runtime.tokenizer.digest != self._tokenizer_digest
            or self.runtime.model_identity.identity_digest != self._runtime_digest
            or str(getattr(self.runtime.model, "device", "cpu") or "cpu") != device.actual
            or bool(getattr(self.runtime.model, "resident", False)) != device.resident
        ):
            raise NativeRuntimeBackendError("native runtime is no longer admitted on its execution device")

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical integrity-checked native runtime checkpoint."""
        self.assert_identity()
        checkpoint = self.runtime.checkpoint()
        if checkpoint.get("schema") != RUNTIME_SCHEMA:
            raise NativeRuntimeBackendError("native checkpoint schema drift")
        return dict(checkpoint)

    def count_input_tokens(self, request: LocalInferenceRequest) -> int:
        return self.prepare_input(request).input_tokens

    def prepare_input(
        self,
        request: LocalInferenceRequest,
        *,
        scope_digest: str | None = None,
    ) -> LocalPreparedInput:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        limits = self.generation_limits()
        rendered = self._render_prompt(request)
        try:
            budget = LocalInputBudget.from_limits(limits)
            budget.validate_request(request, 0, rendered=rendered)
        except LocalInputBudgetError as exc:
            raise NativeRuntimeBackendError(str(exc)) from exc
        sequence = self.runtime.encode(rendered)
        count = len(sequence.token_ids)
        try:
            budget.validate_tokens(count, request.max_output_tokens)
        except LocalInputBudgetError as exc:
            raise NativeRuntimeBackendError(str(exc)) from exc
        return LocalPreparedInput(
            request_digest=request.digest,
            model_digest=self._model_digest,
            runtime_digest=self._runtime_digest,
            execution_profile_digest=self.execution_profile_digest,
            tokenizer_digest=self._tokenizer_digest,
            source_digest=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            sequence_digest=sequence.digest,
            input_tokens=count,
            scope_digest=scope_digest,
            token_sequence=sequence,
            issuer=self._preparation_issuer,
        )

    def validate_prepared_input(self, request: LocalInferenceRequest, prepared: LocalPreparedInput) -> None:
        self.assert_identity()
        if not isinstance(prepared, LocalPreparedInput):
            raise NativeRuntimeBackendError("native prepared input contract is invalid")
        rendered_digest = hashlib.sha256(self._render_prompt(request).encode("utf-8")).hexdigest()
        prepared.assert_binding(
            request,
            issuer=self._preparation_issuer,
            model_digest=self._model_digest,
            runtime_digest=self._runtime_digest,
            execution_profile_digest=self.execution_profile_digest,
            tokenizer_digest=self._tokenizer_digest,
            source_digest=rendered_digest,
        )
        sequence = prepared.token_sequence
        if (
            not isinstance(sequence, TokenSequence)
            or type(sequence.token_ids) is not tuple
            or sequence.tokenizer_digest != self._tokenizer_digest
            or sequence.source_text_digest != rendered_digest
            or len(sequence.token_ids) != prepared.input_tokens
            or sequence.digest != prepared.sequence_digest
            or any(
                type(token) is not int or not 0 <= token < self.runtime.tokenizer.vocab_size
                for token in sequence.token_ids
            )
        ):
            raise NativeRuntimeBackendError("native prepared token sequence changed after admission")
        try:
            LocalInputBudget.from_limits(self._declared_generation_limits()).validate_tokens(
                prepared.input_tokens,
                request.max_output_tokens,
            )
        except LocalInputBudgetError as exc:
            raise NativeRuntimeBackendError(str(exc)) from exc

    def generation_limits(self) -> dict[str, Any]:
        """Expose activated sliding-context and tokenizer admission ceilings."""

        self.assert_identity()
        return self._declared_generation_limits()

    def _declared_generation_limits(self) -> dict[str, Any]:
        tokenizer_limits = self.runtime.tokenizer.limits
        return {
            "context_window": min(self.runtime.limits.max_context, tokenizer_limits.max_tokens),
            "max_output_tokens": min(8192, self.runtime.limits.max_new_tokens, tokenizer_limits.max_tokens),
            "max_total_tokens": self.runtime.limits.max_total_tokens,
            "shared_context": False,
            "tokenizer": self.tokenizer_kind,
            "tokenizer_max_chars": tokenizer_limits.max_chars,
            "tokenizer_max_tokens": tokenizer_limits.max_tokens,
            "max_output_utf8_bytes": _MAX_OUTPUT_BYTES,
            "limits_source": "activated_native_runtime",
        }

    @staticmethod
    def _output_size(text: str, maximum: int = _MAX_OUTPUT_BYTES) -> int:
        size = 0
        try:
            for offset in range(0, len(text), 8192):
                size += len(text[offset : offset + 8192].encode("utf-8", errors="strict"))
                if size > maximum:
                    raise NativeRuntimeBackendError("native generation exceeds the local output byte budget")
        except UnicodeEncodeError as exc:
            raise NativeRuntimeBackendError("native generation contains invalid Unicode") from exc
        return size

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint: Mapping[str, Any],
    ) -> NativeRuntimeLocalModel:
        if not isinstance(checkpoint, Mapping):
            raise TypeError("checkpoint must be a mapping")
        runtime = NativeLLMRuntime.restore(checkpoint)
        return cls(runtime)

    @staticmethod
    def _stable_json(value: object) -> str:
        try:
            return json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise NativeRuntimeBackendError("native local protocol value is not canonical JSON") from exc

    @staticmethod
    def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise NativeRuntimeBackendError(f"native local protocol duplicate JSON key: {key}")
            result[key] = value
        return result

    @staticmethod
    def _reject_constant(value: str) -> None:
        raise NativeRuntimeBackendError("native local protocol contains non-finite JSON constant: " + value)

    @staticmethod
    def _finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise NativeRuntimeBackendError("native local protocol contains a non-finite JSON number")
        return number

    def _load_protocol_json(self, text: str) -> Any:
        try:
            return json.loads(
                text,
                object_pairs_hook=self._strict_object,
                parse_constant=self._reject_constant,
                parse_float=self._finite_float,
            )
        except NativeRuntimeBackendError:
            raise
        except (ValueError, RecursionError) as exc:
            raise NativeRuntimeBackendError("native local protocol output is not valid JSON") from exc

    def _normalized_structured_output_schema(
        self,
        request: LocalInferenceRequest,
    ) -> dict[str, Any] | None:
        if request.structured_output_schema is None:
            return None
        try:
            schema = validate_json_schema(request.structured_output_schema)
        except ToolContractError as exc:
            raise NativeRuntimeBackendError(f"invalid native structured output schema: {exc}") from exc
        if schema.get("type") not in {None, "object"}:
            raise NativeRuntimeBackendError("native structured output schema must describe an object")
        return schema

    def _render_prompt(self, request: LocalInferenceRequest) -> str:
        prompt = request.rendered_input
        structured_schema = self._normalized_structured_output_schema(request)
        if request.tools:
            allowed: list[dict[str, Any]] = []
            seen_tool_ids: set[str] = set()
            for item in request.tools:
                tool_id = str(item.get("tool_id", "")).strip()
                if not tool_id:
                    raise NativeRuntimeBackendError("native local tool schema missing tool_id")
                if tool_id in seen_tool_ids:
                    raise NativeRuntimeBackendError(f"duplicate native local tool_id {tool_id!r}")
                seen_tool_ids.add(tool_id)
                allowed.append(
                    {
                        "tool_id": tool_id,
                        "description": str(item.get("description", "")),
                        "input_schema": item.get("input_schema", {}),
                    }
                )
            prompt += (
                "\n\n[Skeleton native local tool protocol]\n"
                "When a tool is required, output exactly one JSON object and no prose: "
                '{"skeleton_local_response":1,"tool_calls":'
                '[{"call_id":"stable-id","tool_id":"allowed-id","arguments":{}}]}.\n'
                "Never invent a tool_id. Otherwise answer normally.\n"
                + (
                    "If final structured output is requested, place it under "
                    "structured_output and match the supplied schema.\n"
                    if request.structured_output_schema is not None
                    else ""
                )
                + "Allowed tools: "
                + self._stable_json(allowed)
            )
            if structured_schema is not None:
                prompt += "\nFinal structured output schema: " + self._stable_json(structured_schema)
            if request.tool_choice in {"required", "specific"}:
                prompt += "\nA tool call is required for this turn; do not return a prose-only answer."
            if request.tool_choice == "specific":
                prompt += "\nRequired tool_id: " + str(request.specific_tool_id)
        elif request.structured_output_schema is not None:
            prompt += (
                "\n\n[Skeleton native structured-output protocol]\n"
                "Output exactly one JSON object matching this schema and no prose: "
                + self._stable_json(structured_schema)
            )
        return prompt

    def _parse_output(
        self,
        raw: str,
        request: LocalInferenceRequest,
    ) -> tuple[
        str | None,
        tuple[LocalToolCall, ...],
        Mapping[str, Any] | None,
        str,
    ]:
        text = raw.strip()
        if not text:
            raise NativeRuntimeBackendError("native runtime produced empty output")
        allowed_tool_ids = {
            str(item.get("tool_id", "")).strip()
            for item in request.tools
            if str(item.get("tool_id", "")).strip()
        }
        payload: Any = None
        if text.startswith("{"):
            try:
                payload = self._load_protocol_json(text)
            except NativeRuntimeBackendError:
                if request.tools or request.structured_output_schema is not None:
                    raise
                payload = None
            version = payload.get("skeleton_local_response") if isinstance(payload, dict) else None
            if (
                isinstance(payload, dict)
                and "skeleton_local_response" in payload
                and not (type(version) is int and version == 1)
            ):
                raise NativeRuntimeBackendError("unsupported native local response protocol version")
            if isinstance(payload, dict) and type(version) is int and version == 1:
                unknown_envelope = set(payload) - {
                    "skeleton_local_response",
                    "text",
                    "structured_output",
                    "tool_calls",
                }
                if unknown_envelope:
                    raise NativeRuntimeBackendError(
                        "native local response envelope contains unsupported fields"
                    )
                raw_calls = payload.get("tool_calls", [])
                if not isinstance(raw_calls, list) or len(raw_calls) > 256:
                    raise NativeRuntimeBackendError("native tool_calls envelope must be a list of at most 256 calls")
                calls: list[LocalToolCall] = []
                call_ids: set[str] = set()
                for raw_call in raw_calls:
                    if not isinstance(raw_call, dict):
                        raise NativeRuntimeBackendError("native local tool call must be an object")
                    if set(raw_call) != {"call_id", "tool_id", "arguments"}:
                        raise NativeRuntimeBackendError("native local tool call has invalid fields")
                    if not isinstance(raw_call["call_id"], str) or not isinstance(raw_call["tool_id"], str):
                        raise NativeRuntimeBackendError("native tool identifiers must be strings")
                    call_id = str(raw_call.get("call_id", "")).strip()
                    tool_id = str(raw_call.get("tool_id", "")).strip()
                    arguments = raw_call.get("arguments", {})
                    if not call_id:
                        raise NativeRuntimeBackendError("native local tool call missing call_id")
                    if call_id in call_ids:
                        raise NativeRuntimeBackendError("native local tool call identifiers must be unique")
                    call_ids.add(call_id)
                    if tool_id not in allowed_tool_ids:
                        raise NativeRuntimeBackendError(
                            f"native model requested undeclared tool_id {tool_id!r}"
                        )
                    if not isinstance(arguments, dict):
                        raise NativeRuntimeBackendError("native local tool arguments must be an object")
                    calls.append(
                        LocalToolCall(
                            call_id=call_id,
                            tool_id=tool_id,
                            arguments=arguments,
                        )
                    )
                payload_text = payload.get("text")
                if payload_text is not None and not isinstance(
                    payload_text,
                    str,
                ):
                    raise NativeRuntimeBackendError("native response text must be text or null")
                if isinstance(payload_text, str) and not payload_text.strip():
                    raise NativeRuntimeBackendError("native response text must be non-empty when present")
                structured = payload.get("structured_output")
                if structured is not None and not isinstance(structured, dict):
                    raise NativeRuntimeBackendError("native structured_output must be an object")
                if structured is not None and request.structured_output_schema is not None:
                    try:
                        validate_json_value(
                            self._normalized_structured_output_schema(request),
                            structured,
                            path="structured_output",
                        )
                    except ToolContractError as exc:
                        raise NativeRuntimeBackendError(
                            f"native structured output validation failed: {exc}"
                        ) from exc
                if not calls and payload_text is None and structured is None:
                    raise NativeRuntimeBackendError("native local response envelope contains no output")
                return (
                    payload_text,
                    tuple(calls),
                    structured,
                    "tool_calls" if calls else "completed",
                )

        if request.structured_output_schema is not None:
            try:
                structured_payload = self._load_protocol_json(text)
            except NativeRuntimeBackendError as exc:
                raise NativeRuntimeBackendError("native structured output is not valid JSON") from exc
            if not isinstance(structured_payload, dict):
                raise NativeRuntimeBackendError("native structured output must be a JSON object")
            try:
                validate_json_value(
                    self._normalized_structured_output_schema(request),
                    structured_payload,
                    path="structured_output",
                )
            except ToolContractError as exc:
                raise NativeRuntimeBackendError(f"native structured output validation failed: {exc}") from exc
            return None, (), structured_payload, "completed"

        return text, (), None, "completed"

    @staticmethod
    def _truncate_stop(text: str, stops: tuple[str, ...]) -> tuple[str, bool]:
        earliest: int | None = None
        for marker in stops:
            index = text.find(marker)
            if index >= 0 and (earliest is None or index < earliest):
                earliest = index
        if earliest is None:
            return text, False
        return text[:earliest].rstrip(), True

    def infer(
        self,
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        if not isinstance(cancel, threading.Event):
            raise TypeError("cancel must be threading.Event")
        if cancel.is_set():
            raise LocalInferenceCancelled("native local inference cancelled")
        return self.infer_prepared(request, cancel, self.prepare_input(request))

    def infer_prepared(
        self,
        request: LocalInferenceRequest,
        cancel: threading.Event,
        prepared: LocalPreparedInput,
    ) -> LocalInferenceResult:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        if not isinstance(cancel, threading.Event):
            raise TypeError("cancel must be threading.Event")
        if cancel.is_set():
            raise LocalInferenceCancelled("native local inference cancelled")

        self.validate_prepared_input(request, prepared)
        limits = self._declared_generation_limits()
        if request.max_output_tokens > limits["max_output_tokens"]:
            raise NativeRuntimeBackendError("native request exceeds the admitted output-token budget")
        execution_profile = self.execution_profile_digest
        started = time.perf_counter()
        eos_id = self.runtime.tokenizer.special_token_id("eos")
        config = GenerationConfig(
            max_new_tokens=request.max_output_tokens,
            seed=request.seed,
            temperature=0.0,
            top_k=0,
            top_p=1.0,
            use_cache=True,
            stop_token_ids=() if eos_id is None else (eos_id,),
            stop_strings=request.stop,
            include_stop_tokens=False,
        )

        def interrupt() -> None:
            if cancel.is_set():
                raise LocalInferenceCancelled("native local inference cancelled")

        try:
            prompt_sequence = prepared.token_sequence
            input_tokens = len(prompt_sequence.token_ids)
            if input_tokens > limits["context_window"]:
                raise NativeRuntimeBackendError("native request exceeds the admitted context budget")
            if input_tokens + request.max_output_tokens > limits["max_total_tokens"]:
                raise NativeRuntimeBackendError("native request exceeds the admitted total-token budget")
            audit = _NativeStreamAudit(self.runtime, prompt_sequence, config)
            # stream_sequence admits the exact sequence used for accounting;
            # native string stops finish normally with real usage and receipt.
            with self.runtime.stream_sequence(prompt_sequence, config, interrupt=interrupt) as stream:
                for event in stream:
                    interrupt()
                    audit.observe(event)
            result = stream.result
            if result is None:
                raise NativeRuntimeBackendError("native runtime terminated without a generation result")
            audit.validate(result)
        except LocalInferenceCancelled:
            raise
        except RuntimeContractError as exc:
            raise NativeRuntimeBackendError("native runtime rejected local inference") from exc

        self.assert_identity()
        interrupt()
        if self.execution_profile_digest != execution_profile:
            raise NativeRuntimeBackendError("native execution profile changed during inference")
        if (
            result.prompt_sequence != prompt_sequence
            or result.usage.prompt_tokens != input_tokens
            or result.usage.generated_tokens != len(result.generated_ids)
            or len(result.generated_ids) > request.max_output_tokens
        ):
            raise NativeRuntimeBackendError("native terminal result does not match admitted token accounting")
        if result.finish_reason not in {"completed", "length", "stop_token", "stop_string"}:
            raise NativeRuntimeBackendError("native decoder returned an unsupported terminal reason")
        self._output_size(result.text)
        raw_text, stop_hit = self._truncate_stop(result.text, request.stop)
        stop_hit = stop_hit or result.finish_reason in {"stop_token", "stop_string"}
        if not raw_text and not stop_hit:
            # Preserve generated model material instead of inventing an answer.
            raw_text = " ".join(result.generated_tokens).strip()
        if not raw_text:
            raise NativeRuntimeBackendError(
                "native runtime stopped before visible output"
                if stop_hit
                else "native runtime generated no output"
            )
        self._output_size(raw_text)

        text, tool_calls, structured, parsed_finish = self._parse_output(
            raw_text,
            request,
        )
        if tool_calls:
            finish_reason = "tool_calls"
        elif stop_hit or result.finish_reason in {"completed", "stop_token", "stop_string"}:
            finish_reason = "completed"
        elif parsed_finish == "completed":
            finish_reason = "length"
        else:
            finish_reason = parsed_finish

        published_digest = hashlib.sha256(
            (request.digest + ":" + result.output_digest + ":" + self._runtime_digest + ":" + execution_profile).encode("ascii")
        ).hexdigest()
        visible_digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
        execution_receipt_digest = hashlib.sha256(
            (
                result.replay_receipt.digest
                + ":"
                + request.digest
                + ":"
                + self._runtime_digest
                + ":"
                + published_digest
                + ":"
                + visible_digest
                + ":"
                + finish_reason
            ).encode("ascii")
        ).hexdigest()
        interrupt()
        return LocalInferenceResult(
            text=text,
            model_id=self.model_id,
            model_digest=self.model_digest,
            input_tokens=len(result.prompt_sequence.token_ids),
            output_tokens=len(result.generated_ids),
            finish_reason=finish_reason,
            response_id="native:" + published_digest[:32],
            execution_receipt_digest=execution_receipt_digest,
            tool_calls=tool_calls,
            structured_output=structured,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )


__all__ = [
    "NativeRuntimeBackendError",
    "NativeRuntimeLocalModel",
]
