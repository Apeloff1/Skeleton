"""Application entry to the existing governed offline llama.cpp/GGUF inference backend.

This module DOES NOT implement a second model runtime, downloader, subprocess
wrapper, inference engine or artifact loader. It only constrains user-visible
CLI input and maps the canonical LocalInferenceEngine result to a provenance-
bound, honestly labelled receipt. Both the executable and GGUF must already
exist on disk, be explicitly selected, and pass the canonical identity gates.
"""
from __future__ import annotations

from dataclasses import dataclass

import asyncio
import hashlib
from pathlib import Path

from skeleton.ai.runtime.inference.llama_cpp import (
    LlamaCppConfig,
    LlamaCppModel,
)
from skeleton.ai.runtime.inference.local import (
    LocalInferenceEngine,
    LocalInferenceRequest,
)

MAX_GGUF_PROMPT_CHARS = 8192
MAX_GGUF_OUTPUT_TOKENS = 2048


class OfflineGGUFError(ValueError):
    """Operator's local GGUF request is not admissible."""


async def generate_local_gguf(
    *,
    executable: str | Path,
    model: str | Path,
    prompt: str,
    max_output_tokens: int = 128,
) -> dict[str, object]:
    """Perform one credential-free inference turn through the canonical backend.

    The text is sent only via the backend's private temporary prompt file;
    never through a shell or process argument. The returned counts are the
    llama.cpp adapter's estimates, not verified tokenizer usage.
    """
    if (
        not isinstance(prompt, str) or not prompt.strip()
        or len(prompt) > MAX_GGUF_PROMPT_CHARS
    ):
        raise OfflineGGUFError("GGUF prompt must contain 1-8192 characters")
    if (
        type(max_output_tokens) is not int
        or not 1 <= max_output_tokens <= MAX_GGUF_OUTPUT_TOKENS
    ):
        raise OfflineGGUFError("GGUF output token budget must be 1-2048")
    if (
        not isinstance(executable, (str, Path))
        or not str(executable).strip()
        or not isinstance(model, (str, Path))
        or not str(model).strip()
    ):
        raise OfflineGGUFError("explicit llama.cpp executable and GGUF model required")
    backend = LlamaCppModel(LlamaCppConfig(
        executable=str(executable),
        model_path=str(model),
        timeout_seconds=120.0,
        max_output_bytes=1024 * 1024,
        max_stderr_bytes=128 * 1024,
        temperature=0.0,
        reject_model_symlink=True,
        rehash_artifacts_each_run=True,
    ))
    request = LocalInferenceRequest(
        prompt=prompt.strip(),
        max_output_tokens=max_output_tokens,
        seed=0,
    )
    result = await LocalInferenceEngine(backend, cache_size=0).generate(request)
    if (
        not isinstance(result.text, str) or not result.text.strip()
        or result.tool_calls or result.structured_output is not None
        or result.model_digest != backend.model_digest
        or len(result.text) > 32_768
    ):
        raise OfflineGGUFError("GGUF backend returned invalid, unbound, or oversized text")
    # Receipt identifies the *actual* local executable and model bytes.
    # Never make up an execution_receipt_digest if the canonical backend
    # has not emitted one; keep response identity separate from attestation.
    return {
        "schema_version": 1,
        "backend": "llama.cpp",
        "text": result.text,
        "model_id": result.model_id,
        "model_digest": result.model_digest,
        "runtime_digest": backend.runtime_digest,
        "model_bytes": backend.model_artifact.size_bytes,
        "runtime_bytes": backend.runtime_artifact.size_bytes,
        "response_id": result.response_id,
        "input_tokens_estimated": result.input_tokens,
        "output_tokens_estimated": result.output_tokens,
        "token_counts_are_estimates": True,
        "hosted_provider_used": False,
        "model_downloaded": False,
        "model_quality_certified": False,
        "execution_receipt_digest": result.execution_receipt_digest,
        "request_sha256": hashlib.sha256(
            request.rendered_input.encode("utf-8")
        ).hexdigest(),
    }


def generate_local_gguf_sync(
    executable: str | Path, model: str | Path, prompt: str,
    *, max_output_tokens: int = 128,
) -> dict[str, object]:
    """Synchronous terminal adapter; shared async model runtime is canonical."""
    return asyncio.run(generate_local_gguf(
        executable=executable,
        model=model,
        prompt=prompt,
        max_output_tokens=max_output_tokens,
    ))


@dataclass(frozen=True, slots=True)
class GGUFChatAnswer:
    text: str
    model_digest: str
    execution_receipt_digest: str | None
    input_tokens: int
    output_tokens: int


class OfflineGGUFSession:
    """Ephemeral multi-turn GGUF chat over the EXISTING llama.cpp process plane.

    No native tokenizer or exact context accounting is claimed, and model-
    bound transcript persistence is disabled until a GGUF-specific authority
    with a verified tokenizer exists. The app never executes arbitrary tools.
    """

    ui_output_budget = 32

    def __init__(self, executable: str | Path, model: str | Path) -> None:
        self.backend = LlamaCppModel(LlamaCppConfig(
            executable=str(executable),
            model_path=str(model),
            timeout_seconds=120.0,
            max_output_bytes=1024 * 1024,
            max_stderr_bytes=128 * 1024,
            temperature=0.0,
            reject_model_symlink=True,
            rehash_artifacts_each_run=True,
        ))
        self.engine = LocalInferenceEngine(self.backend, cache_size=0)
        self.history: tuple[tuple[str, str], ...] = ()

    @property
    def model_digest(self) -> str:
        return self.backend.model_digest

    def clear(self) -> None:
        self.history = ()

    async def ask(
        self, prompt: str, *, max_output_tokens: int = 32,
    ) -> GGUFChatAnswer:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4096:
            raise OfflineGGUFError("GGUF desktop message must be 1-4096 characters")
        if (
            type(max_output_tokens) is not int
            or not 1 <= max_output_tokens <= MAX_GGUF_OUTPUT_TOKENS
        ):
            raise OfflineGGUFError("GGUF output budget is out of bounds")
        history = self.history
        # Conservative character cap, NOT an assertion of exact model token
        # window. Drop oldest paired turns rather than truncating role text.
        while history and (
            sum(len(text) for _, text in history) + len(prompt) > 4096
        ):
            history = history[2:]
        request = LocalInferenceRequest(
            prompt=prompt.strip(),
            history=history,
            max_output_tokens=max_output_tokens,
            seed=0,
        )
        result = await self.engine.generate(request)
        if (
            not isinstance(result.text, str)
            or not result.text.strip()
            or result.tool_calls
            or result.structured_output is not None
            or result.model_digest != self.backend.model_digest
            or len(result.text) > 8192
        ):
            raise OfflineGGUFError("invalid, unbound or oversized GGUF chat response")
        self.history = (
            history + (("user", request.prompt), ("assistant", result.text))
        )[-16:]
        return GGUFChatAnswer(
            text=result.text,
            model_digest=result.model_digest,
            execution_receipt_digest=result.execution_receipt_digest,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
