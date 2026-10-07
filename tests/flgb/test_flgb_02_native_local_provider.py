from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from skeleton.ai.model_runtime import NativeLLMRuntime, RuntimeContractError
from skeleton.ai.runtime.inference import (
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalModelAdapter,
    LocalModelArtifactError,
    NativeRuntimeBackendError,
    NativeRuntimeLocalModel,
    load_local_model_artifact,
    write_local_model_artifact,
)
from skeleton.api.engine_authority import (
    DelegatedAuthority,
    EngineAuthorityRegistry,
    EngineServiceGrant,
    engine_request_binding,
)
from skeleton.api.engine_runtime import EngineExecutionCoordinator
from skeleton.api.engine_service import (
    EngineContextHandoff,
    EngineExecutionCommand,
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
from skeleton.contracts.ai_execution import AIExecutionRequest
from skeleton.contracts.operation import OperationEnvelope
from skeleton.cortex.transformer import TinyTransformer
from skeleton.intelligence.execution_runtime import ExecutionVerificationDecision
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_runtime import ProviderRegistry, ProviderRequest
from skeleton.skills.tool_runtime import AsyncToolRuntime


def _backend() -> NativeRuntimeLocalModel:
    model = TinyTransformer(
        vocab=(
            "system:",
            "user:",
            "assistant:",
            "alpha",
            "beta",
            "gamma",
            "delta",
            "answer",
        ),
        dim=8,
        ctx=32,
        seed=43,
        n_heads=2,
        n_layers=2,
        d_ff=16,
    )
    return NativeRuntimeLocalModel(NativeLLMRuntime(model))


def _write_native(root: Path):
    backend = _backend()
    path = root / "native-runtime.json"
    receipt = write_local_model_artifact(backend, path)
    return path, backend, receipt


@contextmanager
def _local_environment(path: Path):
    values = {
        "AI_PROVIDER": "local",
        "AI_LOCAL_MODEL_PATH": str(path),
        "AI_LOCAL_MODEL_CACHE_SIZE": "8",
        "AI_LOCAL_MODEL_SEED": "23",
        "OPENAI_API_KEY": "",
        "OPENAI_BASE_URL": "",
        "AI_SECONDARY_API_KEY": "",
        "AI_SECONDARY_BASE_URL": "",
        "AI_SECONDARY_MODEL": "",
        "AI_VERIFICATION_MODEL": "",
    }
    with patch.dict(os.environ, values, clear=False):
        yield


@contextmanager
def _internet_blocked():
    original_socket = socket.socket

    def guarded_socket(*args, **kwargs):
        family = args[0] if args else kwargs.get("family", socket.AF_INET)
        if family in {socket.AF_INET, socket.AF_INET6}:
            raise AssertionError("native local provider attempted Internet I/O")
        return original_socket(*args, **kwargs)

    with patch("socket.socket", guarded_socket):
        yield


class TestNativeRuntimeLocalArtifact(unittest.TestCase):
    def test_checkpoint_round_trip_preserves_all_runtime_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            path, expected, receipt = _write_native(Path(directory))
            loaded = load_local_model_artifact(path)

            self.assertIsInstance(loaded.model, NativeRuntimeLocalModel)
            self.assertEqual(loaded.model.model_id, expected.model_id)
            self.assertEqual(loaded.model.model_digest, expected.model_digest)
            self.assertEqual(loaded.model.runtime_digest, expected.runtime_digest)
            self.assertEqual(
                loaded.model.tokenizer_digest,
                expected.tokenizer_digest,
            )
            self.assertEqual(
                loaded.receipt.schema,
                "skeleton.ai.native-llm-runtime.v2",
            )
            self.assertEqual(
                loaded.receipt.artifact_sha256,
                receipt.artifact_sha256,
            )
            self.assertEqual(
                loaded.receipt.model_digest,
                expected.model_digest,
            )
            self.assertTrue(
                json.loads(path.read_text(encoding="utf-8"))["digest"]
            )

    def test_artifact_weight_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _expected, _receipt = _write_native(Path(directory))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["model"]["bout"][0] += 0.25
            path.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                LocalModelArtifactError,
                "native runtime artifact failed identity validation",
            ):
                load_local_model_artifact(path)

    def test_backend_detects_post_admission_weight_drift(self):
        backend = _backend()
        backend.runtime.model.bout[0] += 0.5
        with self.assertRaises(RuntimeContractError):
            backend.infer(
                LocalInferenceRequest(prompt="alpha", max_output_tokens=1),
                threading.Event(),
            )

    def test_backend_honors_precancel_without_model_execution(self):
        backend = _backend()
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(LocalInferenceCancelled):
            backend.infer(
                LocalInferenceRequest(prompt="alpha", max_output_tokens=2),
                cancel,
            )

    def test_structured_output_protocol_validates_schema(self):
        backend = _backend()
        request = LocalInferenceRequest(
            prompt="alpha",
            max_output_tokens=2,
            structured_output_schema={
                "type": "object",
                "required": ["answer"],
                "properties": {"answer": {"type": "string"}},
                "additionalProperties": False,
            },
        )
        text, calls, structured, finish = backend._parse_output(
            '{"answer":"beta"}',
            request,
        )
        self.assertIsNone(text)
        self.assertEqual(calls, ())
        self.assertEqual(structured, {"answer": "beta"})
        self.assertEqual(finish, "completed")

        with self.assertRaisesRegex(
            NativeRuntimeBackendError,
            "structured output validation failed",
        ):
            backend._parse_output('{"answer":7}', request)
        with self.assertRaisesRegex(
            NativeRuntimeBackendError,
            "structured output is not valid JSON",
        ):
            backend._parse_output("not-json", request)

    def test_tool_protocol_accepts_declared_and_rejects_undeclared_ids(self):
        backend = _backend()
        request = LocalInferenceRequest(
            prompt="alpha",
            max_output_tokens=2,
            tools=(
                {
                    "tool_id": "repo.read",
                    "description": "read a repository path",
                    "input_schema": {
                        "type": "object",
                        "required": ["path"],
                        "properties": {"path": {"type": "string"}},
                        "additionalProperties": False,
                    },
                },
            ),
        )
        raw = (
            '{"skeleton_local_response":1,"tool_calls":['
            '{"call_id":"call-1","tool_id":"repo.read",'
            '"arguments":{"path":"README.md"}}]}'
        )
        text, calls, structured, finish = backend._parse_output(raw, request)
        self.assertIsNone(text)
        self.assertIsNone(structured)
        self.assertEqual(finish, "tool_calls")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].tool_id, "repo.read")
        self.assertEqual(calls[0].arguments, {"path": "README.md"})

        undeclared = raw.replace("repo.read", "repo.write")
        with self.assertRaisesRegex(
            NativeRuntimeBackendError,
            "undeclared tool_id",
        ):
            backend._parse_output(undeclared, request)

        boolean_version = raw.replace(
            '"skeleton_local_response":1',
            '"skeleton_local_response":true',
        )
        with self.assertRaisesRegex(
            NativeRuntimeBackendError,
            "unsupported native local response protocol version",
        ):
            backend._parse_output(boolean_version, request)

        duplicate_key = (
            '{"skeleton_local_response":1,'
            '"skeleton_local_response":1,'
            '"text":"alpha"}'
        )
        with self.assertRaisesRegex(
            NativeRuntimeBackendError,
            "duplicate JSON key",
        ):
            backend._parse_output(duplicate_key, request)

        unknown_field = (
            '{"skeleton_local_response":1,"text":"alpha","extra":true}'
        )
        with self.assertRaisesRegex(
            NativeRuntimeBackendError,
            "unsupported fields",
        ):
            backend._parse_output(unknown_field, request)

        empty_text = (
            '{"skeleton_local_response":1,"text":"   "}'
        )
        with self.assertRaisesRegex(
            NativeRuntimeBackendError,
            "text must be non-empty",
        ):
            backend._parse_output(empty_text, request)

    def test_tool_prompt_projects_only_declared_contract(self):
        backend = _backend()
        request = LocalInferenceRequest(
            prompt="alpha",
            tools=(
                {
                    "tool_id": "repo.read",
                    "description": "read",
                    "input_schema": {"type": "object"},
                },
            ),
        )
        rendered = backend._render_prompt(request)
        self.assertIn("Skeleton native local tool protocol", rendered)
        self.assertIn('"tool_id":"repo.read"', rendered)
        self.assertNotIn("repo.write", rendered)


class TestNativeRuntimeLocalProvider(unittest.IsolatedAsyncioTestCase):
    async def test_local_engine_cache_is_native_model_identity_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            path, expected, _receipt = _write_native(Path(directory))
            loaded = load_local_model_artifact(path)
            engine = LocalInferenceEngine(loaded.model, cache_size=4)
            request = LocalInferenceRequest(
                prompt="alpha beta",
                instructions="answer",
                max_output_tokens=4,
                seed=7,
            )
            first = await engine.generate(request)
            second = await engine.generate(request)

            self.assertEqual(first.model_id, expected.model_id)
            self.assertEqual(first.model_digest, expected.model_digest)
            self.assertGreater(first.input_tokens, 0)
            self.assertGreater(first.output_tokens, 0)
            self.assertLessEqual(first.output_tokens, 4)
            self.assertTrue(first.text)
            self.assertFalse(first.cached)
            self.assertTrue(second.cached)
            self.assertEqual(second.text, first.text)
            self.assertEqual(second.model_digest, first.model_digest)

    async def test_cache_hit_revalidates_native_runtime_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _expected, _receipt = _write_native(Path(directory))
            loaded = load_local_model_artifact(path)
            engine = LocalInferenceEngine(loaded.model, cache_size=4)
            request = LocalInferenceRequest(
                prompt="alpha beta",
                max_output_tokens=2,
                seed=3,
            )
            first = await engine.generate(request)
            self.assertFalse(first.cached)

            loaded.model.runtime.model.bout[0] += 0.5
            with self.assertRaises(RuntimeContractError):
                await engine.generate(request)

    async def test_provider_registry_activates_native_checkpoint_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            path, expected, _receipt = _write_native(Path(directory))
            with _local_environment(path), _internet_blocked():
                registry = ProviderRegistry.from_env()
                adapter = registry.require_active()
                status = registry.statuses()

                self.assertIsInstance(adapter, LocalModelAdapter)
                self.assertIsInstance(
                    adapter.engine.model,
                    NativeRuntimeLocalModel,
                )
                self.assertEqual(adapter.provider_id, "local")
                self.assertEqual(adapter.model, expected.model_id)
                self.assertEqual(
                    adapter.runtime_digest,
                    expected.runtime_digest,
                )
                self.assertEqual(status[0]["network_policy"], "none")
                self.assertEqual(
                    status[0]["artifact"]["schema"],
                    "skeleton.ai.native-llm-runtime.v2",
                )
                self.assertEqual(
                    status[0]["artifact"]["model_digest"],
                    expected.model_digest,
                )

                response = await adapter.generate(
                    ProviderRequest(
                        instructions="answer",
                        prompt="alpha beta",
                        max_output_tokens=3,
                        operation_id="op-native-provider",
                        execution_id="exec-native-provider",
                        turn_id="turn-native-provider",
                    )
                )

                self.assertEqual(response.provider, "local")
                self.assertEqual(response.model, expected.model_id)
                self.assertTrue(response.text)
                self.assertGreater(response.usage.input_tokens, 0)
                self.assertGreater(response.usage.output_tokens, 0)
                self.assertLessEqual(response.usage.output_tokens, 3)
                self.assertEqual(response.usage.billed_cost, "0")
                self.assertEqual(
                    response.usage.usage_source,
                    "local_model",
                )


def _engine_command():
    now = datetime.now(timezone.utc)
    operation = OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id="tenant-native",
        actor_id="operator-native",
        capability="assistant.chat",
        created_at=now,
        deadline=now + timedelta(minutes=2),
        idempotency_key="native-runtime-local-provider",
        trace_id="trace-native-runtime-local-provider",
    )
    execution_id = str(uuid4())
    handoff = EngineContextHandoff(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        turn_id=str(uuid4()),
        tenant_id=operation.tenant_id,
        context_id=str(uuid4()),
        context_digest="a" * 64,
        compiler_version="native-runtime-local-provider-test",
        source_snapshot=((str(uuid4()), "b" * 64),),
        data_class="internal",
        instructions="answer",
        prompt="alpha beta",
        purpose="model-inference",
        history=(),
    )
    request = AIExecutionRequest(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        objective="Execute the canonical native runtime through local provider.",
        context_policy={
            "tenant_id": operation.tenant_id,
            "capability": operation.capability,
            "data_class": handoff.data_class,
            "context_id": handoff.context_id,
            "context_digest": handoff.context_digest,
            "compiler_version": handoff.compiler_version,
            "handoff_digest": handoff.handoff_digest,
            "source_snapshot": [list(item) for item in handoff.source_snapshot],
        },
        tool_policy={
            "tenant_id": operation.tenant_id,
            "data_class": "internal",
            "purpose": "tool-execution",
            "allowed_tool_ids": [],
        },
        resource_budget={
            "max_model_turns": 2,
            "max_tool_calls": 1,
            "max_output_tokens": 4,
        },
        stop_policy={
            "deadline": operation.deadline.isoformat(),
            "max_repeat_tool_batches": 1,
        },
        created_at=now,
    )
    authority = DelegatedAuthority(
        service_principal="codedock-backend",
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        scopes=(
            "engine:submit",
            "engine:read",
            "engine:cancel",
            "engine:events",
            "engine:approve",
        ),
        capability=operation.capability,
        issued_at=now,
        expires_at=operation.deadline,
        request_binding=engine_request_binding(operation, request),
    )
    return operation, EngineExecutionCommand(
        operation=operation,
        execution_request=request,
        delegated_authority=authority,
        compiled_context=handoff,
        context_seed_refs=("test:native-runtime-local-provider",),
        resource_budget=dict(request.resource_budget),
        stream_preferences={"mode": "events"},
    )


def _verified(_request, candidate: str, context_digest: str):
    if not candidate.strip():
        raise AssertionError("verification candidate must be non-empty")
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "test:native-runtime-local-provider",
            "candidate_digest": hashlib.sha256(candidate.encode()).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:native-runtime-local-provider",),
    )


async def _wait_result(service, execution_id: str):
    for _ in range(300):
        result = service.repository.result(execution_id)
        if result is not None:
            return result
        await asyncio.sleep(0)
    raise AssertionError("native local engine execution did not complete")


class TestNativeRuntimeEnginePath(unittest.IsolatedAsyncioTestCase):
    async def test_engine_coordinator_reaches_native_runtime_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, expected, _receipt = _write_native(root)
            with _local_environment(path), _internet_blocked():
                operation, command = _engine_command()
                service = EngineExecutionService(
                    SQLiteExecutionRepository(root / "native-engine.sqlite3"),
                    SQLiteEngineSubmissionStore(
                        root / "native-submissions.sqlite3"
                    ),
                    EngineAuthorityRegistry(
                        [
                            EngineServiceGrant(
                                service_principal="codedock-backend",
                                scopes=frozenset(
                                    {
                                        "engine:submit",
                                        "engine:read",
                                        "engine:cancel",
                                        "engine:events",
                                        "engine:approve",
                                    }
                                ),
                                tenant_ids=frozenset(
                                    {operation.tenant_id}
                                ),
                                capabilities=frozenset(
                                    {operation.capability}
                                ),
                            )
                        ]
                    ),
                )
                service.submit(
                    command,
                    verified_service_principal="codedock-backend",
                    actor_id=operation.actor_id,
                    tenant_id=operation.tenant_id,
                    now=operation.created_at,
                )
                registry = ProviderRegistry.from_env()
                adapter = registry.require_active()
                self.assertIsInstance(
                    adapter.engine.model,
                    NativeRuntimeLocalModel,
                )
                self.assertEqual(
                    adapter.engine.model.model_digest,
                    expected.model_digest,
                )

                coordinator = EngineExecutionCoordinator(
                    service,
                    provider_registry=registry,
                    tool_runtime=AsyncToolRuntime(),
                    verification_hook=_verified,
                )
                try:
                    await coordinator.ensure_started(command)
                    result = await _wait_result(
                        service,
                        command.execution_request.execution_id,
                    )
                    self.assertEqual(result.status, "completed")
                    self.assertTrue(result.final_output)
                    self.assertTrue(result.provider_receipts)
                    self.assertTrue(
                        all(
                            item.startswith("provider:local:")
                            for item in result.provider_receipts
                        )
                    )
                    self.assertEqual(
                        result.verification_receipt["outcome"],
                        "passed",
                    )
                    self.assertEqual(
                        registry.require_active().model,
                        expected.model_id,
                    )
                finally:
                    await coordinator.shutdown()
                    service.repository.close()
                    service.submissions.close()


if __name__ == "__main__":
    unittest.main()
