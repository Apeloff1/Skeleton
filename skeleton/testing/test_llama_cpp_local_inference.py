from __future__ import annotations

from skeleton.testing.local_inference_fixtures import local_serving_resources as local_serving_resources

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import struct
import threading

import pytest

from skeleton.ai.runtime.functional_ai import FunctionalAIRequest, FunctionalAIRuntime
from skeleton.ai.runtime.inference import LocalInferenceEngine, LocalInferenceRequest
from skeleton.ai.runtime.inference.llama_cpp import (
    CODING_COMPLETION_CHAT_TEMPLATE,
    COMPLETION_CHAT_FLAGS,
    QWEN3_COMPLETION_CHAT_TEMPLATE,
    LlamaCppConfig,
    LlamaCppModel,
    LlamaCppRuntimeError,
    build_llama_cpp_adapter,
)
from skeleton.intelligence.execution_runtime import ExecutionVerificationDecision
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_runtime import ProviderRequest
from skeleton.skills.tool_contract import ToolEffect, ToolManifest
from skeleton.skills.tool_runtime import AsyncToolRuntime


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
parser.add_argument("-f", "--binary-file", dest="f")
parser.add_argument("-n")
parser.add_argument("--seed")
parser.add_argument("--temp")
parser.add_argument("--json-schema-file")
args, unknown = parser.parse_known_args()
prompt = Path(args.f).read_text(encoding="utf-8")
if "[Skeleton local tool protocol]" in prompt:
    if not args.json_schema_file:
        print("missing governed JSON schema", file=sys.stderr)
        raise SystemExit(93)
    schema = json.loads(Path(args.json_schema_file).read_text(encoding="utf-8"))
    enum = schema["properties"]["tool_calls"]["items"]["properties"]["tool_id"]["enum"]
    if enum != ["repo.read"]:
        print("wrong governed tool enum", file=sys.stderr)
        raise SystemExit(94)
if any("sensitive-prompt" in item for item in sys.argv):
    print("prompt leaked into argv", file=sys.stderr)
    raise SystemExit(92)
if "SLOW_REQUEST" in prompt:
    time.sleep(2.0)
if "OVERFLOW_REQUEST" in prompt:
    print("x" * 8192)
    raise SystemExit(0)
if "INVALID_STRUCTURED_REQUEST" in prompt:
    print(json.dumps({"answer": 7}, sort_keys=True))
    raise SystemExit(0)
if "STRUCTURED_REQUEST" in prompt:
    if not args.json_schema_file:
        print("missing structured output schema", file=sys.stderr)
        raise SystemExit(95)
    schema = json.loads(Path(args.json_schema_file).read_text(encoding="utf-8"))
    if schema.get("required") != ["answer", "score"]:
        print("wrong structured output schema", file=sys.stderr)
        raise SystemExit(96)
    print(json.dumps({"answer": "offline", "score": 1}, sort_keys=True))
    raise SystemExit(0)
if "UNKNOWN_TOOL_REQUEST" in prompt:
    print(json.dumps({
        "skeleton_local_response": 1,
        "tool_calls": [{"call_id": "bad", "tool_id": "not.allowed", "arguments": {}}],
    }))
    raise SystemExit(0)
if "Tool results from the previous provider turn" in prompt:
    print(json.dumps({
        "skeleton_local_response": 1,
        "text": "The local subprocess model completed VS-001 from the governed receipt.",
    }, sort_keys=True))
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
    model.write_bytes(
        struct.pack("<4sIQQ", b"GGUF", 3, 1, 0)
        + b"fixture-open-weight-model-v1"
    )
    return runtime, model


def _config(tmp_path: Path, **overrides) -> LlamaCppConfig:
    runtime, model = _artifacts(tmp_path)
    values = {
        "executable": str(runtime),
        "model_path": str(model),
        "timeout_seconds": 5.0,
        "context_size": 2048,
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
    assert backend.gguf_header.version == 3
    assert backend.gguf_header.tensor_count == 1
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
async def test_llama_cpp_enforces_and_returns_structured_output(tmp_path: Path) -> None:
    adapter = build_llama_cpp_adapter(_config(tmp_path))
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer", "score"],
        "properties": {
            "answer": {"type": "string"},
            "score": {"type": "integer", "minimum": 0, "maximum": 1},
        },
    }
    response = await adapter.generate(
        ProviderRequest(
            instructions="Return governed structured output.",
            prompt="STRUCTURED_REQUEST",
            structured_output_schema=schema,
            max_output_tokens=32,
        )
    )
    assert response.provider == "local"
    assert response.text is None
    assert response.structured_output == {"answer": "offline", "score": 1}


@pytest.mark.asyncio
async def test_llama_cpp_rejects_structured_output_schema_violation(
    tmp_path: Path,
) -> None:
    backend = LlamaCppModel(_config(tmp_path))
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer"],
        "properties": {"answer": {"type": "string"}},
    }
    with pytest.raises(LlamaCppRuntimeError, match="structured output validation failed"):
        await LocalInferenceEngine(backend).generate(
            LocalInferenceRequest(
                prompt="INVALID_STRUCTURED_REQUEST",
                structured_output_schema=schema,
            )
        )


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
    with pytest.raises(LlamaCppRuntimeError, match="symlinked path component rejected"):
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
    # The second turn includes the governed tool protocol and its recorded
    # result alongside an output reserve; admit that complete rendered input.
    config = _config(tmp_path, context_size=8192)
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
        created_at=datetime.now(timezone.utc),
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
    expected_runtime_digest = hashlib.sha256(
        Path(config.executable).read_bytes()
    ).hexdigest()
    assert run.evidence.local_runtime_digest == expected_runtime_digest
    assert all(
        expected_runtime_digest in ref
        and run.evidence.local_model_digest in ref
        for ref in run.evidence.provider_receipts
    )
    assert run.evidence.tool_receipt_count == 1
    assert len(run.evidence.provider_receipts) == 2
    assert len(observed) == 1

    recovered = SQLiteExecutionRepository(database)
    stored = recovered.result(request.execution_id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.final_output == run.execution.result.final_output
    assert stored.stream_terminal_event == run.evidence.stream_terminal_event


def test_llama_cpp_rejects_non_gguf_model(tmp_path: Path) -> None:
    runtime, model = _artifacts(tmp_path)
    model.write_bytes(b"not-a-gguf-model-artifact")
    with pytest.raises(LlamaCppRuntimeError, match="GGUF"):
        LlamaCppModel(
            LlamaCppConfig(executable=str(runtime), model_path=str(model))
        )


@pytest.mark.parametrize("version", [0, 1, 4, 99])
def test_llama_cpp_rejects_unsupported_gguf_versions(
    tmp_path: Path,
    version: int,
) -> None:
    runtime, model = _artifacts(tmp_path)
    model.write_bytes(struct.pack("<4sIQQ", b"GGUF", version, 1, 0) + b"x")
    with pytest.raises(LlamaCppRuntimeError, match="unsupported GGUF version"):
        LlamaCppModel(
            LlamaCppConfig(executable=str(runtime), model_path=str(model))
        )


def test_llama_cpp_rejects_zero_tensor_gguf(tmp_path: Path) -> None:
    runtime, model = _artifacts(tmp_path)
    model.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 0, 0) + b"x")
    with pytest.raises(LlamaCppRuntimeError, match="zero tensors"):
        LlamaCppModel(
            LlamaCppConfig(executable=str(runtime), model_path=str(model))
        )


@pytest.mark.parametrize(
    "extra_arg",
    [
        "--model=/tmp/other.gguf",
        "--prompt=override",
        "--file=/tmp/prompt.txt",
        "--binary-file=/tmp/prompt.txt",
        "-bf/tmp/prompt.txt",
        "--n-predict=999",
        "--seed=42",
        "--temp=1.0",
        "--ctx-size=4096",
        "--threads=64",
        "--batch-size=512",
        "--gpu-layers=99",
        "--grammar=root ::= \"x\"",
        "--grammar-file=/tmp/grammar.gbnf",
        "--json-schema={}",
        "--json-schema-file=/tmp/schema.json",
        "-j{}",
        "-jf/tmp/schema.json",
        "-m/tmp/other.gguf",
        "-n999",
        "-c4096",
        "-t64",
        "-b512",
        "-ngl99",
    ],
)
def test_llama_cpp_rejects_managed_argument_override(
    tmp_path: Path,
    extra_arg: str,
) -> None:
    runtime, model = _artifacts(tmp_path)
    with pytest.raises(ValueError, match="may not override managed flag"):
        LlamaCppConfig(
            executable=str(runtime),
            model_path=str(model),
            extra_args=(extra_arg,),
        )


@pytest.mark.parametrize(
    "extra_arg",
    [
        "--hf-repo=owner/model",
        "--hf-file=model.gguf",
        "--model-url=https://example.invalid/model.gguf",
        "--url=https://example.invalid/model.gguf",
        "--download",
        "-hf=owner/model",
    ],
)
def test_llama_cpp_rejects_remote_model_acquisition_flags(
    tmp_path: Path,
    extra_arg: str,
) -> None:
    runtime, model = _artifacts(tmp_path)
    with pytest.raises(ValueError, match="remote model acquisition"):
        LlamaCppConfig(
            executable=str(runtime),
            model_path=str(model),
            extra_args=(extra_arg,),
        )


def test_llama_cpp_allows_unmanaged_local_tuning_flag(tmp_path: Path) -> None:
    runtime, model = _artifacts(tmp_path)
    config = LlamaCppConfig(
        executable=str(runtime),
        model_path=str(model),
        extra_args=("--mlock",),
    )
    assert config.extra_args == ("--mlock",)


@pytest.mark.parametrize("extra_arg", ["--mlock\n--model=x", "--mlock\x7f"])
def test_llama_cpp_rejects_control_characters_in_extra_args(
    tmp_path: Path,
    extra_arg: str,
) -> None:
    runtime, model = _artifacts(tmp_path)
    with pytest.raises(ValueError, match="control characters"):
        LlamaCppConfig(
            executable=str(runtime),
            model_path=str(model),
            extra_args=(extra_arg,),
        )


def _chat_config(tmp_path: Path, template: str = CODING_COMPLETION_CHAT_TEMPLATE, **overrides):
    values = {
        "context_size": 12288,
        "output_framing": "llama_completion_eog",
        "extra_args": (*COMPLETION_CHAT_FLAGS, "--chat-template", template),
    }
    values.update(overrides)
    return _config(tmp_path, **values)


@pytest.mark.parametrize(
    ("template", "trailer"),
    [
        (CODING_COMPLETION_CHAT_TEMPLATE, "<|im_start|>assistant\n"),
        (QWEN3_COMPLETION_CHAT_TEMPLATE, "<|im_start|>assistant\n<think>\n\n</think>\n\n"),
    ],
    ids=["coding", "qwen3-closed-think"],
)
def test_pinned_native_chat_preserves_actual_roles_content_and_one_generation_prefix(
    tmp_path: Path, template: str, trailer: str,
) -> None:
    backend = LlamaCppModel(_chat_config(tmp_path, template))
    request = LocalInferenceRequest(
        instructions="  SYSTEM_POLICY\nretain policy whitespace  ",
        history=(("user", "previous user\n"), ("assistant", "previous answer 漁")),
        prompt="  current source\nconst text = '\\n';\n  ",
        max_output_tokens=1024,
    )
    expected = (
        "<|im_start|>system\n  SYSTEM_POLICY\nretain policy whitespace  <|im_end|>\n"
        "<|im_start|>user\nprevious user\n<|im_end|>\n"
        "<|im_start|>assistant\nprevious answer 漁<|im_end|>\n"
        "<|im_start|>user\n  current source\nconst text = '\\n';\n  <|im_end|>\n"
        + trailer
    )
    assert backend._render_prompt(request) == expected
    assert backend.count_input_tokens(request) == len(expected.encode("utf-8")) + 1
    assert request.rendered_input.startswith("system: SYSTEM_POLICY")  # Generic contract unchanged.


@pytest.mark.parametrize("with_tools", [False, True], ids=["json", "tools-and-json"])
def test_pinned_chat_places_validated_schema_and_tool_protocol_only_in_system(
    tmp_path: Path, with_tools: bool,
) -> None:
    backend = LlamaCppModel(_chat_config(tmp_path))
    schema = {"type": "object", "properties": {"修正": {"type": "string"}}, "required": ["修正"]}
    tools = ({"tool_id": "repo.read", "description": "Read a scoped source", "input_schema": {"type": "object"}},) if with_tools else ()
    request = LocalInferenceRequest(
        instructions="Repair the reported error only.", prompt="Owned source and actual error.",
        tools=tools, structured_output_schema=schema,
        tool_choice="specific" if with_tools else "auto",
        specific_tool_id="repo.read" if with_tools else None,
    )
    rendered = backend._render_prompt(request)
    system, remaining = rendered.split("<|im_end|>\n", 1)
    assert system.startswith("<|im_start|>system\nRepair the reported error only.")
    assert '"required":["修正"]' in system
    assert "Required final JSON schema:" in system if with_tools else "Required JSON schema:" in system
    assert ("Allowed tools:" in system) is with_tools
    assert ("Required tool_id: repo.read" in system) is with_tools
    assert remaining == "<|im_start|>user\nOwned source and actual error.<|im_end|>\n<|im_start|>assistant\n"
    assert "schema" not in remaining and "protocol" not in remaining


def test_pinned_native_binary_transport_preserves_exact_bytes_and_existing_limits(
    tmp_path: Path, monkeypatch,
) -> None:
    import skeleton.ai.runtime.inference.llama_cpp as native

    backend = LlamaCppModel(_chat_config(tmp_path, threads=2, batch_size=64, gpu_layers=0))
    request = LocalInferenceRequest(
        instructions="Repair only; no extra features.",
        history=(("user", "old source 漁\n"), ("assistant", "old answer")),
        prompt="STRUCTURED_REQUEST sensitive-prompt literal \\n stays literal\n",
        max_output_tokens=1024, seed=4294967302,
        structured_output_schema={"type": "object", "properties": {"answer": {"type": "string"}, "score": {"type": "integer"}}, "required": ["answer", "score"]},
    )
    expected = backend._render_prompt(request).encode("utf-8")
    original_popen = native.subprocess.Popen
    captured = []

    def capture(command, **kwargs):
        input_file = Path(command[command.index("--binary-file") + 1])
        captured.append((list(command), input_file.read_bytes(), input_file.stat().st_mode & 0o777))
        return original_popen(command, **kwargs)

    monkeypatch.setattr(native.subprocess, "Popen", capture)
    result = backend.infer(request, threading.Event())
    assert result.structured_output == {"answer": "offline", "score": 1}
    assert len(captured) == 1
    command, actual, mode = captured[0]
    assert actual == expected and actual.endswith(b"<|im_start|>assistant\n")
    assert mode == 0o600
    assert "--no-conversation" in command and "--no-escape" in command
    for forbidden in ("-f", "--conversation", "--chat-template", "--jinja", "--single-turn"):
        assert forbidden not in command
    for flag, value in (("-n", "1024"), ("-c", "12288"), ("-t", "2"), ("-b", "64"), ("-ngl", "0"), ("--seed", "7"), ("--temp", "0")):
        assert command[command.index(flag) + 1] == value
    assert "--json-schema-file" in command
    assert not any("sensitive-prompt" in item for item in command)
    assert result.input_tokens == len(expected) + 1
    assert backend.execution_snapshot()["active_processes"] == 0


@pytest.mark.parametrize("location", ["instructions", "prompt", "history", "schema", "tool"])
@pytest.mark.parametrize("marker", ["<|im_start|>", "<|im_end|>", "<|endoftext|>"])
def test_chat_control_delimiters_cannot_create_native_roles_before_process_dispatch(
    tmp_path: Path, monkeypatch, location: str, marker: str,
) -> None:
    import skeleton.ai.runtime.inference.llama_cpp as native

    backend = LlamaCppModel(_chat_config(tmp_path))
    values = {"instructions": "Policy", "prompt": "Owned source", "history": (("assistant", "Prior model output"),)}
    if location in {"instructions", "prompt"}:
        values[location] = marker
    elif location == "history":
        values["history"] = (("user", marker),)
    elif location == "schema":
        values["structured_output_schema"] = {"type": "object", "description": marker}
    else:
        values["tools"] = ({"tool_id": "repo.read", "description": marker, "input_schema": {"type": "object"}},)
    monkeypatch.setattr(native.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Reserved token must fail before native launch"))
    with pytest.raises(LlamaCppRuntimeError, match="reserved ChatML"):
        backend.infer(LocalInferenceRequest(**values), threading.Event())


@pytest.mark.parametrize("customization", ["raw", "custom-template", "extra-tuning", "generic-conversation"])
def test_unknown_and_raw_deployments_retain_exact_legacy_rendering_and_file_transport(
    tmp_path: Path, customization: str,
) -> None:
    config = _chat_config(tmp_path)
    if customization == "raw":
        config = replace(config, output_framing="raw")
    elif customization == "custom-template":
        config = replace(config, extra_args=(*COMPLETION_CHAT_FLAGS, "--chat-template", "custom-template"))
    elif customization == "extra-tuning":
        config = replace(config, extra_args=(*config.extra_args, "--mlock"))
    else:
        config = replace(config, extra_args=COMPLETION_CHAT_FLAGS)
    backend = LlamaCppModel(config)
    request = LocalInferenceRequest(instructions="  Policy  ", history=(("user", "prior\n"),), prompt=" source <|im_start|> ")
    assert backend._native_chat_profile() is None
    assert backend._render_prompt(request) == request.rendered_input
    command = backend._command(tmp_path / "private-prompt", request)
    assert "-f" in command and "--binary-file" not in command and "--no-conversation" not in command
    assert command[-len(config.extra_args):] == list(config.extra_args)


def test_effective_role_format_enters_cache_identity_only_for_recognized_profiles(
    tmp_path: Path, monkeypatch,
) -> None:
    import skeleton.ai.runtime.inference.llama_cpp as native

    original_digest = native._digest
    captured = []

    def capture(value):
        if isinstance(value, dict) and value.get("schema") == "skeleton.llama-cpp.execution-profile.v1":
            captured.append(dict(value))
        return original_digest(value)

    monkeypatch.setattr(native, "_digest", capture)
    config = _chat_config(tmp_path)
    backend = LlamaCppModel(config)
    actual = backend.execution_profile_digest
    corrected_profile = captured[-1]
    assert corrected_profile.pop("prompt_format") == "skeleton.chatml.coding.v1"
    assert actual != original_digest(corrected_profile)  # Historical single-user-blob cache cannot match.
    raw = LlamaCppModel(replace(config, extra_args=()))
    raw_digest = raw.execution_profile_digest
    assert "prompt_format" not in captured[-1]
    assert raw_digest == original_digest(captured[-1])


def test_model_visible_schema_and_role_framing_count_towards_native_context_before_launch(
    tmp_path: Path, monkeypatch,
) -> None:
    import skeleton.ai.runtime.inference.llama_cpp as native

    backend = LlamaCppModel(_chat_config(tmp_path, context_size=512))
    request = LocalInferenceRequest(
        prompt="Owned source", max_output_tokens=128,
        structured_output_schema={"type": "object", "description": "漁" * 200},
    )
    assert len(request.rendered_input.encode("utf-8")) + 1 + request.max_output_tokens < 512
    assert backend.count_input_tokens(request) + request.max_output_tokens > 512
    monkeypatch.setattr(native.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Full framed/schema context must be admitted before launch"))
    with pytest.raises(LlamaCppRuntimeError, match="completion exceed admitted GGUF context"):
        backend.infer(request, threading.Event())
