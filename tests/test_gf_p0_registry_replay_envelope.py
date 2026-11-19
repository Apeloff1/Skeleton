"""GF-P0-15/16/18 discovery, replay isolation, and invocation envelopes.

No weight file is opened, no provider SDK is called, and no hardware VRAM
is measured. The VRAM figure is the declared tensor table.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.provider_model_readiness import (
    InvocationBudget,
    ResourceEnvelopeExhausted,
    invoke_bounded,
    run_bounded_loop,
)
from skeleton.provider_runtime import (
    ProviderRegistry,
    discover_model_weight_readiness,
    invoke_with_resource_envelope,
)
from skeleton.shells.ai.model_registry import (
    AIModelRegistry,
    MODEL_LICENSE_ALLOWLIST,
    ModelCapability,
    ModelNotReadyError,
)
from skeleton.simulation.game.golden_grid import (
    GameDataset,
    GridEnvironmentAdapter,
    HoldoutRejected,
    RecordedTrace,
    ReplayDivergence,
    evaluation_rows,
    record_actions,
    replay_recorded,
    training_rows,
)


def _manifest(directory: Path, *, license_id: str, artifact: str, tensors: list[dict[str, object]]) -> Path:
    path = directory / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema": "skeleton.model_weight_discovery.v1",
                "architecture_id": "tiny-linear-v1",
                "license_id": license_id,
                "artifact": artifact,
                "tensors": tensors,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_absent_artifact_is_not_ready(tmp_path: Path) -> None:
    manifest = _manifest(
        tmp_path,
        license_id="apache-2.0",
        artifact="weights.bin",
        tensors=[{"name": "weight", "dtype": "f32", "shape": [2, 2]}],
    )
    report = discover_model_weight_readiness(manifest)
    assert report.artifact_present is False
    assert report.architecture_id == "tiny-linear-v1"
    assert report.license_allowed is True
    assert report.license_id in MODEL_LICENSE_ALLOWLIST
    assert report.ready is False
    assert report.weights_loaded is False
    assert report.hardware_vram_measured is False
    assert report.estimate_source == "declared_tensor_table"
    with pytest.raises(ModelNotReadyError, match="absent"):
        report.require_admitted()


def test_disallowed_license_is_refused(tmp_path: Path) -> None:
    artifact = tmp_path / "weights.bin"
    artifact.write_bytes(b"not-weights")
    manifest = _manifest(
        tmp_path,
        license_id="closed-research-only",
        artifact="weights.bin",
        tensors=[{"name": "weight", "dtype": "f32", "shape": [2, 2]}],
    )
    report = AIModelRegistry().discover_weights(manifest)
    assert report.artifact_present is True
    assert report.license_allowed is False
    assert report.ready is False
    assert report.weights_loaded is False
    with pytest.raises(ModelNotReadyError, match="allow-list"):
        report.require_admitted()
    registry = AIModelRegistry()
    item = registry.register(type("Att", (), {
        "provider_id": "local",
        "model_id": "m1",
        "digest": "att-1",
    })())
    registry.set_capability(
        item.registry_id,
        ModelCapability(
            weights_ready=True,
            weights_digest="sha256:declared",
            license_id="closed-research-only",
            allowed_uses=frozenset({"model-inference"}),
            vram_required_mb=0,
        ),
        expected_revision=item.revision,
    )
    with pytest.raises(ModelNotReadyError, match="allow-list"):
        registry.require_ready("local:m1", use="model-inference")


def test_vram_estimate_comes_from_declared_tensor_table(tmp_path: Path) -> None:
    artifact = tmp_path / "weights.bin"
    artifact.write_bytes(b"not-a-tensor-table")
    manifest = _manifest(
        tmp_path,
        license_id="MIT",
        artifact="weights.bin",
        tensors=[
            {"name": "weight", "dtype": "f32", "shape": [2, 2]},
            {"name": "bias", "dtype": "i8", "shape": [4]},
        ],
    )
    report = discover_model_weight_readiness(manifest)
    assert report.estimated_vram_bytes == (2 * 2 * 4) + 4
    assert report.estimated_vram_bytes != artifact.stat().st_size
    assert report.estimate_source == "declared_tensor_table"
    assert report.weights_loaded is False
    assert report.hardware_vram_measured is False
    assert report.architecture_id == "tiny-linear-v1"
    assert report.ready is True
    assert report.require_admitted() is report
    adapter = type("Local", (), {"provider_id": "local", "model": "tiny"})()
    registry_report = ProviderRegistry([adapter], active="local").discover_weight_readiness(manifest)
    assert registry_report.estimated_vram_bytes == report.estimated_vram_bytes
    assert registry_report.weights_loaded is False
    assert registry_report.hardware_vram_measured is False


def test_replay_reproduces_hash_and_detects_divergence() -> None:
    actions = ["right", "right", "down", "wait"]
    adapter = GridEnvironmentAdapter()
    for action in actions:
        adapter.step(action)
    recorded = adapter.record()
    assert replay_recorded(recorded) == recorded.state_hash
    assert record_actions(actions).state_hash == recorded.state_hash
    again = GridEnvironmentAdapter()
    assert again.run(actions) == recorded.state_hash
    moved = RecordedTrace(("right",), recorded.state_hash)
    forged = RecordedTrace(recorded.actions, "ab" * 32)
    for tampered in (moved, forged):
        with pytest.raises(ReplayDivergence) as caught:
            replay_recorded(tampered)
        assert caught.value.expected == tampered.state_hash
        assert caught.value.actual != tampered.state_hash
        assert caught.value.actual == GridEnvironmentAdapter().run(tampered.actions)


def test_holdout_can_be_evaluated_and_is_rejected_as_training() -> None:
    traces = [record_actions(["wait"]), record_actions(["right", "up"])]
    dataset = GameDataset(traces, holdout_indexes={1})
    evaluated = evaluation_rows(dataset.holdout)
    assert evaluated == (traces[1],)
    assert training_rows(dataset.train) == (traces[0],)
    with pytest.raises(HoldoutRejected, match="holdout split rejected as training input"):
        training_rows(dataset.holdout)


def test_envelope_exhaustion_mid_loop_returns_no_partial() -> None:
    with pytest.raises(ResourceEnvelopeExhausted) as caught:
        run_bounded_loop(5, byte_budget=25, step_budget=10, nbytes=10, steps=1)
    assert caught.value.kind == "bytes"
    assert run_bounded_loop(2, byte_budget=25, step_budget=10, nbytes=10, steps=1) == (0, 1)


def test_nested_budget_consumes_parent_remainder() -> None:
    seen: dict[str, InvocationBudget] = {}

    def outer(budget: InvocationBudget) -> int:
        seen["parent"] = budget
        budget.charge(nbytes=4, steps=1)

        def inner(child: InvocationBudget) -> str:
            child.charge(nbytes=6, steps=1)
            assert child.remaining_bytes == 10
            assert child.remaining_steps == 1
            return "inner-ok"

        assert invoke_bounded(inner, byte_budget=1000, step_budget=1000, parent=budget) == "inner-ok"
        return budget.remaining_bytes

    assert invoke_bounded(outer, byte_budget=20, step_budget=3) == 10
    assert seen["parent"].remaining_steps == 1

    def over_remainder(budget: InvocationBudget) -> str:
        budget.charge(nbytes=0, steps=3)

        def inner(child: InvocationBudget) -> str:
            child.charge(nbytes=0, steps=2)
            return "should-not-return"

        return invoke_bounded(inner, byte_budget=10, step_budget=10, parent=budget)

    with pytest.raises(ResourceEnvelopeExhausted) as caught:
        invoke_with_resource_envelope(over_remainder, byte_budget=10, step_budget=4)
    assert caught.value.kind == "steps"
