from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import threading

import pytest

from skeleton.ai.runtime.functional_ai import FunctionalAIRequest, FunctionalAIRuntime
from skeleton.ai.runtime.inference import LocalInferenceEngine, LocalInferenceRequest
from skeleton.ai.runtime.inference.llama_cpp import (
    LlamaCppConfig,
    LlamaCppModel,
    LlamaCppRuntimeError,
    build_llama_cpp_adapter,
)
from skeleton.intelligence.execution_runtime import ExecutionVerificationDecision
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.skills.tool_contract import ToolEffect, ToolManifest
from skeleton.skills.tool_runtime import AsyncToolRuntime


NOW = datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc)


_FAKE_RUNTIME = r'''#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import sys
import time

for key in (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "GOOGLE_API_KEY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
):
    if os.environ.get(key):
        print("forbidden environment leaked: " + key, file=sys.stderr)
        raise SystemExit(91)

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("-m")
parser.add_argument("-f")
parser.add_argument("-n")
parser.add_argument("--seed")
parser.add_argument("--temp")
args, unknown = parser.parse_known_args()
prompt = Path(args.f).read_text(encoding="utf-8")
if any("sensitive-prompt" in item for item in sys.argv):
    print("prompt leaked into argv", file=sys.stderr)
    raise SystemExit(92)
if "SLOW_REQUEST" in prompt:
    time.sleep(2.0)
if "OVERFLOW_REQUEST" in prompt:
    print("x" * 8192)
    raise SystemExit(0)
if "UNKNOWN_TOOL_REQUEST" in prompt:
    print(json.dumps({
        "skeleton_local_response": 1,
        "tool_calls": [{"call_id": "bad", "tool_id": "not.allowed", "arguments": {}}],
    }))
    raise SystemExit(0)
if "Tool results from the previous provider turn" in prompt:
    print("The local subprocess model completed VS-001 from the governed receipt.")
    raise SystemExit(0)
if "[Skeleton local tool protocol]" in prompt:
    print(json.dumps({
        "skeleton_local_response": 1,
        "tool_calls": [{
            "call_id": "local-read-1",
            "tool_id": "repo.read",
            "arguments": {"path": "README.md"},
        }],
    }, sort_keys=True))
    raise SystemExit(0)
print("offline subprocess answer")
'''


def _artifacts(tmp_path: Path) -> tuple[Path, Path]:
    runtime = tmp_path / "llama-cli"
    runtime.write_text(_FAKE_RUNTIME, encoding="utf-8")
    runtime.chmod(0o755)
    model = tmp_path / "fixture.gguf"
    model.write_bytes(b"GGUF-fixture-open-weight-model-v1")
    return runtime, model


def _config(tmp_path: Path, **overrides) -> LlamaCppConfig:
    runtime, model = _artifacts(tmp_path)
    values = {
        "executable": str(runtime),
        "model_path": str(model),
        "timeout_seconds": 5.0,
        "max_output_bytes": 16 * 1024,
        "max_stderr_bytes": 8 * 1024,
    }
    values.update(overrides)
    return LlamaCppConfig(**values)


@pytest.mark.asyncio
async def test_llama_cpp_executes_without_prompt_argv_or_provider_credentials(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-child")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid")
    backend = LlamaCppModel(_config(tmp_path))
    expected_model_digest = hashlib.sha256(
        (tmp_path / "fixture.gguf").read_bytes()
    ).hexdigest()
    result = await LocalInferenceEngine(backend).generate(
        LocalInferenceRequest(prompt="sensitive-prompt: answer offline", max_output_tokens=8)
    )
    assert result.text == "offline subprocess answer"
    assert result.model_digest == expected_model_digest
    assert backend.runtime_digest != backend.model_digest
    assert result.response_id is not None and result.response_id.startswith("local:llama:")


@pytest.mark.asyncio
async def test_llama_cpp_preserves_governed_tool_call_contract(tmp_path: Path) -> None:
    backend = LlamaCppModel(_config(tmp_path))
    result = await LocalInferenceEngine(backend).generate(
        LocalInferenceRequest(
            prompt="Read repository context.",
            instructions="Use allowed tools.",
            tools=(
                {
                    "tool_id": "repo.read",
                    "description": "Read a repository path",
                    "input_schema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            ),
        )
    )
    assert result.finish_reason == "tool_calls"
    assert result.text is None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_id == "repo.read"
    assert dict(result.tool_calls[0].arguments) == {"path": "README.md"}


@pytest.mark.asyncio
async def test_llama_cpp_rejects_model_requested_undeclared_tool(tmp_path: Path) -> None:
    backend = LlamaCppModel(_config(tmp_path))
    with pytest.raises(LlamaCppRuntimeError, match="undeclared tool_id"):
        await LocalInferenceEngine(backend).generate(
            LocalInferenceRequest(
                prompt="UNKNOWN_TOOL_REQUEST",
                tools=(
                    {"tool_id": "repo.read", "description": "read", "input_schema": {}},
                ),
            )
        )


def test_llama_cpp_rejects_model_artifact_mutation(tmp_path: Path) -> None:
    config = _config(tmp_path)
    backend = LlamaCppModel(config)
    Path(config.model_path).write_bytes(b"GGUF-mutated-model-contents-that-changed")
    with pytest.raises(LlamaCppRuntimeError, match="model artifact identity changed"):
        backend.infer(LocalInferenceRequest(prompt="answer"), threading.Event())


@pytest.mark.asyncio
async def test_llama_cpp_enforces_output_bound(tmp_path: Path) -> None:
    backend = LlamaCppModel(_config(tmp_path, max_output_bytes=1024))
    with pytest.raises(LlamaCppRuntimeError, match="stdout exceeded"):
        await LocalInferenceEngine(backend).generate(
            LocalInferenceRequest(prompt="OVERFLOW_REQUEST")
        )


@pytest.mark.asyncio
async def test_llama_cpp_enforces_deadline(tmp_path: Path) -> None:
    backend = LlamaCppModel(_config(tmp_path, timeout_seconds=0.05))
    with pytest.raises(TimeoutError, match="deadline"):
        await LocalInferenceEngine(backend).generate(
            LocalInferenceRequest(prompt="SLOW_REQUEST")
        )


@pytest.mark.asyncio
async def test_llama_cpp_observes_async_cancellation(tmp_path: Path) -> None:
    backend = LlamaCppModel(_config(tmp_path, timeout_seconds=5.0))
    task = asyncio.create_task(
        LocalInferenceEngine(backend).generate(LocalInferenceRequest(prompt="SLOW_REQUEST"))
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_llama_cpp_rejects_model_symlink_by_default(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("symlink semantics vary on Windows")
    runtime, model = _artifacts(tmp_path)
    linked = tmp_path / "linked.gguf"
    linked.symlink_to(model)
    with pytest.raises(LlamaCppRuntimeError, match="symlink rejected"):
        LlamaCppModel(LlamaCppConfig(executable=str(runtime), model_path=str(linked)))


def _verification(_request, candidate: str, context_digest: str) -> ExecutionVerificationDecision:
    assert candidate.startswith("The local subprocess model completed VS-001")
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "vs001:subprocess-independent",
            "candidate_digest": hashlib.sha256(candidate.encode()).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:vs001-subprocess-model-receipt",),
    )


@pytest.mark.asyncio
async def test_vs001_crosses_real_local_process_boundary_and_recovers(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    database = tmp_path / "vs001-subprocess.sqlite3"
    repo = SQLiteExecutionRepository(database)
    tools = AsyncToolRuntime()
    observed = []

    async def read_handler(request):
        observed.append(request)
        return "artifact:readme:local-subprocess"

    await tools.register(
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="Read one repository path",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            effect=ToolEffect.READ_ONLY,
            approval_required=False,
            data_policy="internal:repository",
            network_policy="none",
        ),
        read_handler,
    )
    request = FunctionalAIRequest(
        request_id="vs001-llama-subprocess",
        objective="Read governed context and finish through the local process boundary.",
        prompt="Read README.md and report completion.",
        instructions="Use only the local model and explicitly governed tools.",
        context_digest=hashlib.sha256(b"vs001-subprocess-context").hexdigest(),
        allowed_tool_ids=("repo.read",),
        created_at=NOW,
    )
    runtime = FunctionalAIRuntime(
        repo,
        build_llama_cpp_adapter(config),
        tools,
        verification_hook=_verification,
    )
    run = await runtime.execute(request)
    assert run.execution.completed is True
    assert run.evidence.local_model_id.startswith("llama.cpp:")
    assert run.evidence.local_model_digest == hashlib.sha256(
        Path(config.model_path).read_bytes()
    ).hexdigest()
    assert run.evidence.tool_receipt_count == 1
    assert len(run.evidence.provider_receipts) == 2
    assert len(observed) == 1

    recovered = SQLiteExecutionRepository(database)
    stored = recovered.result(request.execution_id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.final_output == run.execution.result.final_output
    assert stored.stream_terminal_event == run.evidence.stream_terminal_event
