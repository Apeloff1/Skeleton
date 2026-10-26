"""Unfinished engine work retains its exact local artifact across restart."""

import asyncio
import hashlib
import json

import pytest

from skeleton.ai.runtime.inference import ReferenceNGramModel
from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
from skeleton.api.engine_routes import _engine_coordinator
from skeleton.api.engine_runtime import (
    EngineExecutionCoordinator,
)
from skeleton.persistence.execution_repository import ExecutionRepositoryConflict
from skeleton.intelligence.execution_runtime import CognitiveExecutionRuntime
from skeleton.provider_runtime import ProviderPolicyError, ProviderRegistry, provider_execution_identity
from skeleton.testing.test_engine_execution_coordinator import (
    FakeProvider,
    FakeRegistry,
)
from skeleton.testing.test_governed_model_engine_acceptance import (
    _command,
    _engine_stack,
    _offline,
)


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


@pytest.fixture
def local_artifact(tmp_path, monkeypatch):
    path = tmp_path / "pinned-model.json"
    model = ReferenceNGramModel.train(("local engine answer complete",), model_id="pinned-local-model")
    write_local_model_artifact(model, path)
    _offline(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", str(path))
    monkeypatch.setenv("AI_LOCAL_MODEL_SEED", "0")
    for name in (
        "AI_SECONDARY_API_KEY",
        "AI_SECONDARY_BASE_URL",
        "AI_SECONDARY_MODEL",
        "AI_VERIFICATION_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    return path, model


async def _result(service, execution_id):
    for _ in range(1000):
        result = service.repository.result(execution_id)
        if result is not None:
            return result
        await asyncio.sleep(0.001)
    raise AssertionError("pinned execution did not terminalize")


async def _pause_after_actual_inference(tmp_path, monkeypatch):
    command = _command("reference")
    async with _engine_stack(tmp_path, "reference") as (_client, service, registry, app):
        coordinator = app.dependency_overrides[_engine_coordinator]()
        waiting = asyncio.Event()
        gate = asyncio.Event()

        async def pause(_request, candidate, _context_digest):
            assert candidate == "answer complete"
            waiting.set()
            await gate.wait()

        coordinator.verification_hook = pause
        adapter = registry.require_active()
        infer = adapter.engine.model.infer

        def observed_infer(request, cancelled):
            checkpoint = service.repository.latest_checkpoint(command.execution_request.execution_id)
            assert checkpoint.payload["provider_execution_binding"]["generator"] == provider_execution_identity(adapter)
            return infer(request, cancelled)

        monkeypatch.setattr(adapter.engine.model, "infer", observed_infer)
        service.submit(command, verified_service_principal="codedock-backend")
        await coordinator.ensure_started(command)
        await asyncio.wait_for(waiting.wait(), timeout=2)
        checkpoint = service.repository.latest_checkpoint(command.execution_request.execution_id)
        assert checkpoint.payload["model_turns"] == 1
        assert service.repository.result(command.execution_request.execution_id) is None
        return command, checkpoint


@pytest.mark.asyncio
async def test_changed_weights_same_model_name_fail_before_resumed_dispatch(
    tmp_path, monkeypatch, local_artifact
):
    path, original = local_artifact
    command, checkpoint = await _pause_after_actual_inference(tmp_path, monkeypatch)
    replacement = ReferenceNGramModel.train(("local engine changed behavior",), model_id=original.model_id)
    assert replacement.model_digest != original.model_digest
    write_local_model_artifact(replacement, path)
    calls = []
    async with _engine_stack(tmp_path, "reference") as (_client, service, registry, app):

        async def forbidden_dispatch(_request):
            calls.append(True)
            raise AssertionError("changed local artifact was dispatched")

        monkeypatch.setattr(registry.require_active(), "generate", forbidden_dispatch)
        coordinator = app.dependency_overrides[_engine_coordinator]()
        await coordinator.ensure_started(command)
        result = await _result(service, command.execution_request.execution_id)
        assert result.status == "failed"
        assert result.usage["error_code"] == "provider_activation_binding_mismatch"
        assert result.usage["model_turns"] == 1
        assert result.usage["provider_usage"] == checkpoint.payload["usage_events"]
        assert list(result.provider_receipts) == checkpoint.payload["provider_receipts"]
        assert service.repository.latest_checkpoint(result.execution_id) == checkpoint
        assert calls == []


@pytest.mark.asyncio
async def test_exact_artifact_restart_finishes_without_replaying_committed_inference(
    tmp_path, monkeypatch, local_artifact
):
    command, checkpoint = await _pause_after_actual_inference(tmp_path, monkeypatch)
    async with _engine_stack(tmp_path, "reference") as (_client, service, registry, app):

        async def forbidden_dispatch(_request):
            raise AssertionError("committed inference was repeated")

        monkeypatch.setattr(registry.require_active(), "generate", forbidden_dispatch)
        await app.dependency_overrides[_engine_coordinator]().ensure_started(command)
        result = await _result(service, command.execution_request.execution_id)
        assert result.status == "completed"
        assert result.final_output == "answer complete"
        assert result.usage["provider_usage"] == checkpoint.payload["usage_events"]


@pytest.mark.asyncio
async def test_changed_local_seed_fails_before_resumed_dispatch(tmp_path, monkeypatch, local_artifact):
    command, checkpoint = await _pause_after_actual_inference(tmp_path, monkeypatch)
    old_seed = checkpoint.payload["provider_execution_binding"]["generator"]["routes"][0]["local_activation"]["default_seed"]
    monkeypatch.setenv("AI_LOCAL_MODEL_SEED", str(old_seed + 1))
    calls = []
    async with _engine_stack(tmp_path, "reference") as (_client, service, registry, app):

        async def forbidden_dispatch(_request):
            calls.append(True)
            raise AssertionError("changed local inference seed was dispatched")

        monkeypatch.setattr(registry.require_active(), "generate", forbidden_dispatch)
        await app.dependency_overrides[_engine_coordinator]().ensure_started(command)
        result = await _result(service, command.execution_request.execution_id)
        assert result.status == "failed"
        assert result.usage["error_code"] == "provider_activation_binding_mismatch"
        assert result.usage["provider_usage"] == checkpoint.payload["usage_events"]
        assert service.repository.latest_checkpoint(result.execution_id) == checkpoint
        assert calls == []


@pytest.mark.asyncio
async def test_pin_commits_before_dispatch_and_recovers_exact_initial_artifact(
    tmp_path, monkeypatch, local_artifact
):
    command = _command("reference")
    with monkeypatch.context() as crash:

        async def interrupted_provider_turn(_runtime, *_args, **_kwargs):
            raise asyncio.CancelledError("process interruption before dispatch")

        crash.setattr(CognitiveExecutionRuntime, "_run_provider_turn", interrupted_provider_turn)
        async with _engine_stack(tmp_path, "reference") as (_client, service, registry, app):
            service.submit(command, verified_service_principal="codedock-backend")
            coordinator = app.dependency_overrides[_engine_coordinator]()
            await coordinator.ensure_started(command)
            task = coordinator._tasks[command.execution_request.execution_id]
            await asyncio.gather(task, return_exceptions=True)
            checkpoint = service.repository.latest_checkpoint(command.execution_request.execution_id)
            assert (
                checkpoint.payload["provider_execution_binding"]["generator"]
                == provider_execution_identity(registry.require_active())
            )
            assert checkpoint.payload["model_turns"] == 0
            assert service.repository.result(command.execution_request.execution_id) is None
    async with _engine_stack(tmp_path, "reference") as (_client, service, _registry, app):
        await app.dependency_overrides[_engine_coordinator]().ensure_started(command)
        result = await _result(service, command.execution_request.execution_id)
        assert result.status == "completed" and result.final_output == "answer complete"
        assert result.usage["model_turns"] == 1


@pytest.mark.parametrize("damage", ["digest", "deleted_pin", "self_consistent_substitution"])
@pytest.mark.asyncio
async def test_corrupt_or_missing_local_pin_blocks_resumed_dispatch(
    tmp_path, monkeypatch, local_artifact, damage
):
    command, checkpoint = await _pause_after_actual_inference(tmp_path, monkeypatch)
    async with _engine_stack(tmp_path, "reference") as (_client, service, registry, app):
        payload = json.loads(json.dumps(checkpoint.payload))
        if damage == "deleted_pin":
            del payload["provider_execution_binding"]
        elif damage == "digest":
            payload["provider_execution_binding"]["binding_digest"] = "0" * 64
        else:
            binding = payload["provider_execution_binding"]
            generator = binding["generator"]
            generator["routes"][0]["local_activation"]["artifact"]["model_digest"] = "0" * 64
            unsigned_generator = {k: v for k, v in generator.items() if k != "identity_digest"}
            generator["identity_digest"] = _digest(unsigned_generator)
            binding["binding_digest"] = _digest({k: v for k, v in binding.items() if k != "binding_digest"})
        current = service.repository.get(command.execution_request.execution_id)
        service.repository.checkpoint(
            current.execution_id,
            payload,
            expected_execution_version=current.version,
            expected_checkpoint_version=current.checkpoint_version,
        )
        calls = []

        async def forbidden_dispatch(_request):
            calls.append(True)
            raise AssertionError("unbound local inference dispatched")

        monkeypatch.setattr(registry.require_active(), "generate", forbidden_dispatch)
        await app.dependency_overrides[_engine_coordinator]().ensure_started(command)
        result = await _result(service, command.execution_request.execution_id)
        assert result.status == "failed"
        assert result.usage["error_code"] == (
            "provider_activation_binding_missing" if damage == "deleted_pin" else "provider_activation_binding_mismatch"
        )
        assert calls == []


def test_execution_descriptor_is_detached_content_only(local_artifact):
    adapter = ProviderRegistry.from_env().require_active()
    identity = provider_execution_identity(adapter)
    assert identity["schema_version"] == "skeleton.provider.route_binding.v1"
    assert identity["identity_digest"] == _digest({k: v for k, v in identity.items() if k != "identity_digest"})
    assert identity["mode"] == "single"
    assert len(identity["routes"]) == 1
    route = identity["routes"][0]
    assert route["provider_id"] == "local"
    assert route["model_id"] == local_artifact[1].model_id
    assert route["local_activation"]["default_seed"] == 0
    artifact = route["local_activation"]["artifact"]
    assert artifact["model_digest"] == local_artifact[1].model_digest
    assert len(artifact["artifact_sha256"]) == 64
    assert str(local_artifact[0]) not in json.dumps(identity)
    artifact["model_digest"] = "0" * 64
    assert provider_execution_identity(adapter)["routes"][0]["local_activation"]["artifact"]["model_digest"] == local_artifact[1].model_digest


@pytest.mark.asyncio
async def test_local_recovery_cannot_substitute_an_external_provider(tmp_path, monkeypatch, local_artifact):
    command, _checkpoint = await _pause_after_actual_inference(tmp_path, monkeypatch)
    async with _engine_stack(tmp_path, "reference") as (_client, service, _registry, app):
        provider = FakeProvider()
        coordinator = app.dependency_overrides[_engine_coordinator]()
        coordinator.provider_registry = FakeRegistry(provider)
        await coordinator.ensure_started(command)
        result = await _result(service, command.execution_request.execution_id)
        assert result.usage["error_code"] == "provider_activation_binding_mismatch"
        assert provider.requests == []


@pytest.mark.asyncio
async def test_completed_result_replay_accepts_a_different_current_artifact(tmp_path, local_artifact):
    path, original = local_artifact
    command = _command("reference")
    async with _engine_stack(tmp_path, "reference") as (client, _service, _registry, _app):
        first = await client.execute(command)
        assert first.status == "completed"
    write_local_model_artifact(
        ReferenceNGramModel.train(("replacement artifact",), model_id=original.model_id), path
    )
    async with _engine_stack(tmp_path, "reference") as (client, _service, _registry, _app):
        assert await client.execute(command) == first


@pytest.mark.asyncio
async def test_pristine_created_legacy_checkpoint_can_acquire_the_exact_pin(tmp_path, local_artifact):
    command = _command("reference")
    async with _engine_stack(tmp_path, "reference") as (_client, service, registry, app):
        service.submit(command, verified_service_principal="codedock-backend")
        runtime = CognitiveExecutionRuntime(
            service.repository,
            registry.require_active(),
            app.dependency_overrides[_engine_coordinator]().tool_runtime,
        )
        handoff = command.compiled_context
        payload = runtime._initial_payload(
            command.execution_request,
            instructions=handoff.instructions,
            prompt=handoff.prompt,
            context_digest=handoff.context_digest,
            history=(),
        )
        current = service.repository.get(command.execution_request.execution_id)
        service.repository.checkpoint(
            current.execution_id,
            payload,
            expected_execution_version=current.version,
            expected_checkpoint_version=0,
        )
        await app.dependency_overrides[_engine_coordinator]().ensure_started(command)
        result = await _result(service, current.execution_id)
        assert result.status == "completed"
        assert (
            service.repository.latest_checkpoint(current.execution_id).payload["provider_execution_binding"][
                "generator"
            ]
            == provider_execution_identity(registry.require_active())
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("artifact_sha256", "bad"),
        ("reference", "path:/private"),
        ("artifact_bytes", True),
        ("model_id", "other"),
    ],
)
def test_descriptor_rejects_invalid_loaded_artifact_receipt(local_artifact, field, value):
    adapter = ProviderRegistry.from_env().require_active()
    adapter._artifact_status[field] = value
    with pytest.raises(ProviderPolicyError, match="execution identity artifact receipt drift"):
        provider_execution_identity(adapter)


@pytest.mark.asyncio
async def test_stale_absent_checkpoint_observation_cannot_replace_a_competing_pin(tmp_path, local_artifact):
    path, original = local_artifact
    command = _command("reference")
    async with _engine_stack(tmp_path, "reference") as (_client, service, first_registry, app):
        service.submit(command, verified_service_principal="codedock-backend")
        first = app.dependency_overrides[_engine_coordinator]()
        old_runtime = CognitiveExecutionRuntime(
            service.repository, first_registry.require_active(), first.tool_runtime
        )
        handoff = command.compiled_context
        old_payload = old_runtime._initial_payload(
            command.execution_request, instructions=handoff.instructions,
            prompt=handoff.prompt, context_digest=handoff.context_digest,
        )
        assert service.repository.latest_checkpoint(command.execution_request.execution_id) is None
        # Two activations observe the same checkpoint-less execution. The newer
        # activation wins the compare-and-swap; the stale one cannot overwrite it.
        write_local_model_artifact(
            ReferenceNGramModel.train(("new competing content",), model_id=original.model_id), path
        )
        second_registry = ProviderRegistry.from_env()
        new_runtime = CognitiveExecutionRuntime(
            service.repository, second_registry.require_active(), first.tool_runtime
        )
        new_payload = new_runtime._initial_payload(
            command.execution_request, instructions=handoff.instructions,
            prompt=handoff.prompt, context_digest=handoff.context_digest,
        )
        current = service.repository.get(command.execution_request.execution_id)
        committed = service.repository.checkpoint(
            current.execution_id, new_payload,
            expected_execution_version=current.version, expected_checkpoint_version=0,
        )
        assert old_payload["provider_execution_binding"] != new_payload["provider_execution_binding"]
        with pytest.raises(ExecutionRepositoryConflict):
            service.repository.checkpoint(
                current.execution_id, old_payload,
                expected_execution_version=current.version, expected_checkpoint_version=0,
            )
        assert service.repository.latest_checkpoint(current.execution_id) == committed
        assert committed.payload["provider_execution_binding"]["generator"] == provider_execution_identity(
            second_registry.require_active()
        )
