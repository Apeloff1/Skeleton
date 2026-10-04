import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace

import pytest

from skeleton.ai.runtime.learning_foundation.data import DatasetRegistry
from skeleton.ai.runtime.learning_foundation.training import (
    LocalTrainingControlPlane,
    MetricGate,
    TrainingControlError,
    TrainingEvaluationDecision,
    TrainingObservation,
)
from skeleton.learning.model_program import ReferenceNGramTrainer, TrainingSpec


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _fixture(*, minimum_workers=1):
    samples = (b"models preserve local evidence", b"recovery preserves training identity")
    record, _ = DatasetRegistry().ingest(
        ingestion_id="fixture",
        dataset_id="fixture",
        samples=samples,
        source_refs=("source:fixture",),
        rights_refs=("rights:training",),
        expected_version=0,
    )
    spec = TrainingSpec(
        run_id="fixture-run",
        model_id="fixture-model",
        dataset_ids=(record.identity,),
        trainer_id=ReferenceNGramTrainer.trainer_id,
        code_revision="fixture-revision",
        hyperparameters={"order": 2},
    )
    inputs = {
        "datasets": (record,),
        "corpora": {record.identity: tuple(sample.decode() for sample in samples)},
        "worker_ids": ("worker-a", "worker-b"),
        "min_workers": minimum_workers,
    }
    plane = LocalTrainingControlPlane()
    return plane, spec, inputs, plane.run(spec, **inputs)


@pytest.mark.parametrize("change", ["spec", "corpus", "dataset", "workers", "minimum"])
def test_run_retry_rejects_conflicting_inputs(change):
    plane, spec, inputs, _ = _fixture()
    if change == "spec":
        spec = replace(spec, seed=999)
    elif change == "corpus":
        inputs["corpora"] = {spec.dataset_ids[0]: ("forged corpus",)}
    elif change == "dataset":
        inputs["datasets"] = (replace(inputs["datasets"][0], rights_refs=("rights:changed",)),)
    elif change == "workers":
        inputs["worker_ids"] = ("other-worker",)
    else:
        inputs["min_workers"] = 2
    with pytest.raises(TrainingControlError, match="bound to different"):
        plane.run(spec, **inputs)


def test_run_retry_snapshot_cannot_be_mutated_by_returned_or_original_mapping():
    plane, spec, inputs, run = _fixture()
    original_digest = run.receipt.digest
    run.receipt.metrics["documents"] = 999.0
    run.artifact.payload["model_id"] = "poisoned"
    replay = plane.run(spec, **inputs)
    assert replay.receipt.digest == original_digest
    assert replay.artifact.load_reference_model().model_id == spec.model_id
    spec.hyperparameters["order"] = 3
    with pytest.raises(TrainingControlError, match="bound to different"):
        plane.run(spec, **inputs)


def test_prepopulated_dependency_registry_cannot_rebind_prior_run_to_changed_spec():
    plane, spec, inputs, _ = _fixture()
    other = LocalTrainingControlPlane(registry=plane.registry)
    with pytest.raises(TrainingControlError, match="receipt identity differs"):
        other.run(replace(spec, seed=999), **inputs)


def test_prepopulated_dependency_registry_cannot_hide_changed_corpus():
    plane, spec, inputs, _ = _fixture()
    other = LocalTrainingControlPlane(registry=plane.registry)
    inputs["corpora"] = {spec.dataset_ids[0]: ("wrong first document", "wrong second document")}
    with pytest.raises(TrainingControlError, match="registered dataset content"):
        other.run(spec, **inputs)


def test_concurrent_conflicting_run_admission_has_one_immutable_winner():
    _, spec, inputs, _ = _fixture()
    plane = LocalTrainingControlPlane()

    def attempt(seed):
        try:
            return plane.run(replace(spec, seed=seed), **inputs)
        except TrainingControlError:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(attempt, (1, 2)))
    assert sum(outcome is not None for outcome in outcomes) == 1
    winner = next(outcome for outcome in outcomes if outcome is not None)
    assert plane.run(winner.spec, **inputs) == winner


def test_replay_rejects_duplicate_dataset_and_extra_corpus():
    plane, spec, inputs, _ = _fixture()
    with pytest.raises(TrainingControlError, match="dataset identity coverage"):
        plane.run(spec, **{**inputs, "datasets": inputs["datasets"] * 2})
    with pytest.raises(TrainingControlError, match="corpus identity coverage"):
        plane.run(spec, **{**inputs, "corpora": {**inputs["corpora"], "other": ("text",)}})


@pytest.mark.parametrize(
    "field",
    [
        "run_id",
        "spec_digest",
        "plan_digest",
        "model_digest",
        "training_receipt_digest",
        "step",
        "payload_digest",
    ],
)
def test_checkpoint_descriptor_must_match_immutable_payload(field):
    plane, _, _, run = _fixture()
    value = 2 if field == "step" else "wrong-run" if field == "run_id" else _sha("wrong")
    forged = replace(run.checkpoint, **{field: value})
    with pytest.raises(TrainingControlError, match="binding mismatch|payload digest"):
        plane.recover(forged, available_workers=("worker-a",), required_workers=1)


def test_checkpoint_recovery_cannot_lower_admitted_capacity():
    plane, _, _, run = _fixture(minimum_workers=2)
    with pytest.raises(TrainingControlError, match="cannot lower"):
        plane.recover(run.checkpoint, available_workers=("worker-a",), required_workers=1)
    receipt = plane.recover(run.checkpoint, available_workers=("worker-a",), required_workers=2)
    assert receipt.status == "insufficient_capacity"


def test_checkpoint_duplicate_json_keys_fail_even_when_bytes_digest_matches():
    plane, _, _, run = _fixture()
    payload = plane.checkpoint_store.get(run.checkpoint.content_digest)
    duplicate = payload[:-1] + b',"step":1}'
    obj = plane.checkpoint_store.put(duplicate, media_type="application/json")
    checkpoint = replace(run.checkpoint, content_digest=obj.digest)
    with pytest.raises(TrainingControlError, match="duplicate JSON keys"):
        plane.recover(checkpoint, available_workers=("worker-a",), required_workers=1)


def test_checkpoint_unknown_schema_fails_before_capacity_verdict():
    plane, _, _, run = _fixture()
    obj = json.loads(plane.checkpoint_store.get(run.checkpoint.content_digest))
    obj["schema_version"] = 999
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    stored = plane.checkpoint_store.put(payload, media_type="application/json")
    checkpoint = replace(run.checkpoint, content_digest=stored.digest, payload_digest=stored.digest)
    with pytest.raises(TrainingControlError, match="unsupported checkpoint"):
        plane.recover(checkpoint, available_workers=("worker-a",), required_workers=1)


def test_duplicate_metric_gate_cannot_hide_an_earlier_failure():
    plane, spec, _, _ = _fixture()
    with pytest.raises(TrainingControlError, match="duplicate metric"):
        plane.evaluate(
            spec.run_id,
            gates=(MetricGate("documents", minimum=999), MetricGate("documents", minimum=1)),
            verifier_id="independent",
        )


def test_gate_digest_binds_thresholds_even_when_both_pass():
    plane, spec, _, _ = _fixture()
    a = plane.evaluate(spec.run_id, gates=(MetricGate("documents", minimum=1),), verifier_id="independent")
    b = plane.evaluate(spec.run_id, gates=(MetricGate("documents", minimum=2),), verifier_id="independent")
    assert a.passed and b.passed and a.decision_digest != b.decision_digest


def test_unissued_or_mutated_evaluation_cannot_qualify_post_training():
    plane, spec, _, _ = _fixture()
    fake = TrainingEvaluationDecision(spec.run_id, True, "independent", {"forged": True}, _sha("fake"))
    with pytest.raises(TrainingControlError, match="not issued"):
        plane.post_train(spec.run_id, fake)
    gate = plane.evaluate(
        spec.run_id, gates=(MetricGate("documents", minimum=999),), verifier_id="independent"
    )
    forged = replace(gate, passed=True, checks={"documents": True})
    with pytest.raises(TrainingControlError, match="not issued"):
        plane.post_train(spec.run_id, forged)
    assert plane.post_train(spec.run_id, deepcopy(gate)).promotion_eligible is False
    gate.checks["documents"] = True
    with pytest.raises(TrainingControlError, match="not issued"):
        plane.post_train(spec.run_id, gate)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True, "1"])
def test_nonfinite_or_boolean_metric_gate_bounds_are_rejected(value):
    with pytest.raises(TrainingControlError, match="finite numeric"):
        MetricGate("documents", minimum=value)


def test_evaluation_boolean_coercion_and_contradictory_verdict_fail_closed():
    with pytest.raises(TrainingControlError, match="must be boolean"):
        TrainingEvaluationDecision("run", True, "independent", {"check": "false"}, _sha("decision"))
    with pytest.raises(TrainingControlError, match="contradicts checks"):
        TrainingEvaluationDecision("run", True, "independent", {"check": False}, _sha("decision"))
    with pytest.raises(TrainingControlError, match="finite"):
        TrainingObservation("run", 1, {"loss": math.nan}, _sha("observation"))
