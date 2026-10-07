"""Canonical FLGB native transformer as a LocalModelBackend.

This module is the convergence seam between the FLGB-02 native runtime and the
engine's existing provider-neutral local inference stack.  It deliberately
keeps ProviderRegistry, CognitiveExecutionRuntime, caching, governance, and
engine orchestration unchanged while replacing the legacy local artifact
backend with the same tokenizer/checkpoint/transformer runtime used by FLGB-02.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Mapping

from skeleton.ai.model_runtime import (
    GenerationConfig,
    NativeLLMRuntime,
    RuntimeContractError,
)
from skeleton.ai.model_runtime.runtime_contracts import RUNTIME_SCHEMA
from skeleton.ai.model_runtime.tokenization import TokenizerContractError

from skeleton.skills.tool_contract import (
    ToolContractError,
    validate_json_schema,
    validate_json_value,
)

from .local import (
    LocalInferenceCancelled,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalToolCall,
)


class NativeRuntimeBackendError(RuntimeError):
    """Native runtime could not satisfy the local inference contract."""


class NativeRuntimeLocalModel:
    """Expose NativeLLMRuntime through the LocalModelBackend protocol."""

    artifact_schema = RUNTIME_SCHEMA

    def __init__(self, runtime: NativeLLMRuntime) -> None:
        if not isinstance(runtime, NativeLLMRuntime):
            raise TypeError("runtime must be NativeLLMRuntime")
        self.runtime = runtime
        identity = runtime.model_identity
        self.model_id = identity.model_id
        self._model_digest = runtime.model_digest
        self._runtime_digest = identity.identity_digest

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
        return self.runtime.tokenizer.digest

    def assert_identity(self) -> None:
        """Reject mutable weight/tokenizer/runtime drift before cache or inference."""
        self.runtime.assert_model_unchanged()
        try:
            self.runtime.tokenizer.assert_unchanged()
        except TokenizerContractError as exc:
            raise NativeRuntimeBackendError(
                "native tokenizer identity drift"
            ) from exc
        if self.runtime.model_digest != self._model_digest:
            raise NativeRuntimeBackendError("native model digest drift")
        if self.runtime.model_identity.identity_digest != self._runtime_digest:
            raise NativeRuntimeBackendError("native runtime identity drift")

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical integrity-checked native runtime checkpoint."""
        self.assert_identity()
        checkpoint = self.runtime.checkpoint()
        if checkpoint.get("schema") != RUNTIME_SCHEMA:
            raise NativeRuntimeBackendError("native checkpoint schema drift")
        return dict(checkpoint)

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint: Mapping[str, Any],
    ) -> "NativeRuntimeLocalModel":
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
            raise NativeRuntimeBackendError(
                "native local protocol value is not canonical JSON"
            ) from exc

    @staticmethod
    def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise NativeRuntimeBackendError(
                    f"native local protocol duplicate JSON key: {key}"
                )
            result[key] = value
        return result

    @staticmethod
    def _reject_constant(value: str) -> None:
        raise NativeRuntimeBackendError(
            "native local protocol contains non-finite JSON constant: " + value
        )

    def _load_protocol_json(self, text: str) -> Any:
        try:
            return json.loads(
                text,
                object_pairs_hook=self._strict_object,
                parse_constant=self._reject_constant,
            )
        except NativeRuntimeBackendError:
            raise
        except json.JSONDecodeError as exc:
            raise NativeRuntimeBackendError(
                "native local protocol output is not valid JSON"
            ) from exc

    def _normalized_structured_output_schema(
        self,
        request: LocalInferenceRequest,
    ) -> dict[str, Any] | None:
        if request.structured_output_schema is None:
            return None
        try:
            schema = validate_json_schema(request.structured_output_schema)
        except ToolContractError as exc:
            raise NativeRuntimeBackendError(
                f"invalid native structured output schema: {exc}"
            ) from exc
        if schema.get("type") not in {None, "object"}:
            raise NativeRuntimeBackendError(
                "native structured output schema must describe an object"
            )
        return schema

    def _render_prompt(self, request: LocalInferenceRequest) -> str:
        prompt = request.rendered_input
        if request.tools:
            allowed: list[dict[str, Any]] = []
            seen_tool_ids: set[str] = set()
            for item in request.tools:
                tool_id = str(item.get("tool_id", "")).strip()
                if not tool_id:
                    raise NativeRuntimeBackendError(
                        "native local tool schema missing tool_id"
                    )
                if tool_id in seen_tool_ids:
                    raise NativeRuntimeBackendError(
                        f"duplicate native local tool_id {tool_id!r}"
                    )
                seen_tool_ids.add(tool_id)
                allowed.append(
                    {
                        "tool_id": tool_id,
                        "description": str(item.get("description", "")),
                        "input_schema": item.get("input_schema", {}),
                    }
                )
            if request.structured_output_schema is not None:
                self._normalized_structured_output_schema(request)
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
        elif request.structured_output_schema is not None:
            schema = self._normalized_structured_output_schema(request)
            prompt += (
                "\n\n[Skeleton native structured-output protocol]\n"
                "Output exactly one JSON object matching this schema and no prose: "
                + self._stable_json(schema)
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
            if request.tools or request.structured_output_schema is not None:
                payload = self._load_protocol_json(text)
            else:
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = None
            version = (
                payload.get("skeleton_local_response")
                if isinstance(payload, dict)
                else None
            )
            if (
                isinstance(payload, dict)
                and "skeleton_local_response" in payload
                and not (type(version) is int and version == 1)
            ):
                raise NativeRuntimeBackendError(
                    "unsupported native local response protocol version"
                )
            if (
                isinstance(payload, dict)
                and type(version) is int
                and version == 1
            ):
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
                if not isinstance(raw_calls, list):
                    raise NativeRuntimeBackendError(
                        "native tool_calls envelope must be a list"
                    )
                calls: list[LocalToolCall] = []
                for raw_call in raw_calls:
                    if not isinstance(raw_call, dict):
                        raise NativeRuntimeBackendError(
                            "native local tool call must be an object"
                        )
                    if set(raw_call) != {"call_id", "tool_id", "arguments"}:
                        raise NativeRuntimeBackendError(
                            "native local tool call has invalid fields"
                        )
                    call_id = str(raw_call.get("call_id", "")).strip()
                    tool_id = str(raw_call.get("tool_id", "")).strip()
                    arguments = raw_call.get("arguments", {})
                    if not call_id:
                        raise NativeRuntimeBackendError(
                            "native local tool call missing call_id"
                        )
                    if tool_id not in allowed_tool_ids:
                        raise NativeRuntimeBackendError(
                            f"native model requested undeclared tool_id {tool_id!r}"
                        )
                    if not isinstance(arguments, dict):
                        raise NativeRuntimeBackendError(
                            "native local tool arguments must be an object"
                        )
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
                    raise NativeRuntimeBackendError(
                        "native response text must be text or null"
                    )
                if isinstance(payload_text, str) and not payload_text.strip():
                    raise NativeRuntimeBackendError(
                        "native response text must be non-empty when present"
                    )
                structured = payload.get("structured_output")
                if structured is not None and not isinstance(structured, dict):
                    raise NativeRuntimeBackendError(
                        "native structured_output must be an object"
                    )
                if (
                    structured is not None
                    and request.structured_output_schema is not None
                ):
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
                    raise NativeRuntimeBackendError(
                        "native local response envelope contains no output"
                    )
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
                raise NativeRuntimeBackendError(
                    "native structured output is not valid JSON"
                ) from exc
            if not isinstance(structured_payload, dict):
                raise NativeRuntimeBackendError(
                    "native structured output must be a JSON object"
                )
            try:
                validate_json_value(
                    self._normalized_structured_output_schema(request),
                    structured_payload,
                    path="structured_output",
                )
            except ToolContractError as exc:
                raise NativeRuntimeBackendError(
                    f"native structured output validation failed: {exc}"
                ) from exc
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
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        if not isinstance(cancel, threading.Event):
            raise TypeError("cancel must be threading.Event")
        if cancel.is_set():
            raise LocalInferenceCancelled("native local inference cancelled")

        self.assert_identity()
        started = time.perf_counter()
        config = GenerationConfig(
            max_new_tokens=request.max_output_tokens,
            seed=request.seed,
            temperature=0.0,
            top_k=0,
            top_p=1.0,
            use_cache=True,
        )

        try:
            rendered_input = self._render_prompt(request)
            stream = self.runtime.stream(rendered_input, config)
            for _event in stream:
                if cancel.is_set():
                    raise LocalInferenceCancelled(
                        "native local inference cancelled"
                    )
            result = stream.result
            if result is None:
                raise NativeRuntimeBackendError(
                    "native runtime terminated without a generation result"
                )
        except LocalInferenceCancelled:
            raise
        except RuntimeContractError as exc:
            raise NativeRuntimeBackendError(
                "native runtime rejected local inference"
            ) from exc

        self.assert_identity()
        raw_text, stop_hit = self._truncate_stop(result.text, request.stop)
        if not raw_text:
            # Preserve generated model material instead of inventing an answer.
            raw_text = " ".join(result.generated_tokens).strip()
        if not raw_text:
            raise NativeRuntimeBackendError("native runtime generated no output")

        text, tool_calls, structured, parsed_finish = self._parse_output(
            raw_text,
            request,
        )
        if tool_calls:
            finish_reason = "tool_calls"
        elif stop_hit or result.finish_reason in {"completed", "stop_token"}:
            finish_reason = "completed"
        elif parsed_finish == "completed":
            finish_reason = "length"
        else:
            finish_reason = parsed_finish

        return LocalInferenceResult(
            text=text,
            model_id=self.model_id,
            model_digest=self.model_digest,
            input_tokens=len(result.prompt_sequence.token_ids),
            output_tokens=len(result.generated_ids),
            finish_reason=finish_reason,
            response_id="native:" + result.output_digest[:32],
            tool_calls=tool_calls,
            structured_output=structured,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )


__all__ = [
    "NativeRuntimeBackendError",
    "NativeRuntimeLocalModel",
]
