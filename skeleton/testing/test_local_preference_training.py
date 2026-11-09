from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from skeleton.compat.datetime_utc import UTC
from datetime import datetime

import numpy as np
import pytest

from skeleton.ai.runtime.inference.neural import BOS, NumpyRecurrentLM
from skeleton.ai.runtime.training.control import (
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    _digest,
)
from skeleton.ai.runtime.training.data import (
    DatasetRegistry,
    IngestEnvelope,
    MaterializedTrainingSource,
)
from skeleton.ai.runtime.training.neural_trainer import NeuralLocalTrainer
from skeleton.ai.runtime.training.post_training import PostTrainingExperiment
from skeleton.ai.runtime.training.preference_trainer import (
    ALGORITHM,
    PreferenceLocalTrainer,
    PreferencePair,
    preference_objective_and_gradients,
)

NOW = datetime(2026, 10, 4, 16, tzinfo=UTC)
PAIRS = (
    PreferencePair("answer: ", "yes", "no!"),
    PreferencePair("answer: ", "yes", "nah"),
    PreferencePair("reply: ", "yes", "not"),
)
CONFIG = {"epochs": 6, "beta": 0.5, "learning_rate": 0.1, "gradient_clip": 1.0}
PARAMETERS = ("embedding", "recurrent", "hidden_bias", "output", "output_bias")


class AbruptStop(BaseException):
    pass


def _materialize(datasets, dataset_id, documents):
    sources = tuple(
        MaterializedTrainingSource(
            envelope=IngestEnvelope.from_bytes(
                source_id=f"fixture://{dataset_id}/{index}",
                payload=doc.encode(),
                parser_version="text@1",
                classification="internal",
                rights=("training", "evaluation"),
                trusted=True,
                acquired_at=NOW,
            ),
            payload=doc.encode(),
            format="utf8_text",
            rights_refs=("license:preferences",),
        )
        for index, doc in enumerate(documents)
    )
    return datasets.ingest_materialized(
        ingestion_id=dataset_id,
        dataset_id=dataset_id,
        expected_version=0,
        sources={"train": sources},
        classification="internal",
        permitted_uses=("training", "evaluation"),
        retention_class="model-development",
    )


def _fixture(tmp_path, *, budget=None, parent_hidden=4):
    datasets = DatasetRegistry(tmp_path / "datasets.sqlite3")
    runs = TrainingRepository(tmp_path / "training.sqlite3")
    parent_data = _materialize(datasets, "parent-data", ("answer yes reply yes", "general neural words"))
    initial = NeuralLocalTrainer.initialize_model("parent-run", hidden_size=parent_hidden, seed=13)
    parent_manifest = TrainingRunManifest(
        run_id="parent-run",
        dataset_digest=parent_data.dataset_digest,
        base_model_digest=initial.model_digest,
        code_digest=hashlib.sha256(b"parent-code").hexdigest(),
        environment_digest=hashlib.sha256(b"float64").hexdigest(),
        seed=13,
        hyperparameters={},
    )
    parent, parent_artifact = NeuralLocalTrainer(datasets, runs).train(
        parent_manifest,
        datasets.training_corpus(parent_data.dataset_digest),
        hidden_size=parent_hidden,
        epochs=2,
        now=NOW,
    )
    data = _materialize(datasets, "preferences", tuple(pair.document for pair in PAIRS))
    manifest = TrainingRunManifest(
        run_id="preference-run",
        dataset_digest=data.dataset_digest,
        base_model_digest=parent.model_digest,
        code_digest=hashlib.sha256(b"preference-code").hexdigest(),
        environment_digest=hashlib.sha256(b"float64").hexdigest(),
        seed=13,
        hyperparameters={},
        resource_budget=budget or {},
    )
    experiment = PostTrainingExperiment(
        "preference-experiment",
        parent.model_digest,
        data.dataset_digest,
        "dpo",
        ALGORITHM,
        CONFIG,
        hashlib.sha256(b"planned-heldout-eval").hexdigest(),
    )
    trainer = PreferenceLocalTrainer(datasets, runs, parent_run_id="parent-run")
    return datasets, runs, trainer, manifest, experiment, parent, parent_artifact


def _train(fixture):
    datasets, _runs, trainer, manifest, experiment, _parent, _artifact = fixture
    return trainer.train(
        manifest, datasets.training_corpus(manifest.dataset_digest), experiment=experiment, **CONFIG, now=NOW
    )


def _interrupt_after_two_updates(monkeypatch, runs):
    original = runs.checkpoint
    count = 0

    def interrupted(checkpoint, lease, **kwargs):
        nonlocal count
        result = original(checkpoint, lease, **kwargs)
        if checkpoint.run_id == "preference-run":
            count += 1
            if count == 3:
                raise AbruptStop("after two committed preference updates")
        return result

    monkeypatch.setattr(runs, "checkpoint", interrupted)


def test_actual_dpo_changes_chosen_margin_and_keeps_full_parent_reference_frozen(tmp_path):
    fixture = _fixture(tmp_path)
    _datasets, runs, _trainer, manifest, experiment, parent, parent_artifact = fixture
    parent_digest = parent.model_digest
    policy, artifact = _train(fixture)
    assert artifact.initial_loss == pytest.approx(np.log(2))
    assert artifact.final_loss < artifact.initial_loss
    assert artifact.final_margin > artifact.initial_margin
    assert policy.model_digest != parent_digest
    assert artifact.reference_model_digest == parent_digest
    assert artifact.parent_checkpoint_digest == parent_artifact.checkpoint_digest
    assert artifact.experiment_digest == experiment.digest
    assert artifact.production_promotion_authorized is False
    frozen = runs.checkpoint_payload(runs.latest_checkpoint(manifest.run_id))["reference"]
    assert NumpyRecurrentLM.from_dict(frozen).model_digest == parent_digest
    assert NeuralLocalTrainer(fixture[0], runs).load_artifact("parent-run")[0].model_digest == parent_digest
    assert artifact.update_count == CONFIG["epochs"] * len(PAIRS)
    assert all(not np.array_equal(getattr(policy, name), getattr(parent, name)) for name in PARAMETERS)


@pytest.mark.parametrize(
    "name,index",
    [
        ("embedding", (BOS, 0)),
        ("embedding", (ord("a"), 1)),
        ("recurrent", (0, 1)),
        ("hidden_bias", (1,)),
        ("output", (1, ord("y"))),
        ("output_bias", (ord("n"),)),
    ],
)
def test_dpo_true_derivative_matches_finite_difference_with_prompt_conditioning(name, index):
    reference = NumpyRecurrentLM(model_id="reference", parameters=None)
    policy = NumpyRecurrentLM.from_dict(reference.to_dict())
    pair = PreferencePair("abc", "yes", "no!")
    loss, _margin, gradient = preference_objective_and_gradients(policy, reference, pair, beta=0.7)
    assert loss == pytest.approx(np.log(2))
    values = getattr(policy, name)
    original = values[index]
    epsilon = 1e-6
    values[index] = original + epsilon
    upper = preference_objective_and_gradients(policy, reference, pair, beta=0.7)[0]
    values[index] = original - epsilon
    lower = preference_objective_and_gradients(policy, reference, pair, beta=0.7)[0]
    values[index] = original
    assert gradient[name][index] == pytest.approx((upper - lower) / (2 * epsilon), rel=2e-5, abs=2e-8)


def test_interrupted_reopened_resume_is_bit_identical_and_skips_committed_pairs(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    datasets, runs, _trainer, manifest, experiment, _parent, _artifact = fixture
    documents = datasets.training_corpus(manifest.dataset_digest)
    _interrupt_after_two_updates(monkeypatch, runs)
    with pytest.raises(AbruptStop):
        _train(fixture)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    payload = runs.checkpoint_payload(checkpoint)
    assert payload["cursor"]["pair_index"] == 2
    assert payload["usage"]["pairs"] == 2
    runs.close()
    datasets.close()
    reopened_data = DatasetRegistry(tmp_path / "datasets.sqlite3")
    reopened = TrainingRepository(tmp_path / "training.sqlite3")
    resumed = PreferenceLocalTrainer(reopened_data, reopened, parent_run_id="parent-run")
    import skeleton.ai.runtime.training.preference_trainer as module

    original_gradient = module.preference_objective_and_gradients
    calls = []

    def counting(policy, reference, pair, **kwargs):
        calls.append(pair)
        return original_gradient(policy, reference, pair, **kwargs)

    monkeypatch.setattr(module, "preference_objective_and_gradients", counting)
    model, artifact = resumed.train(manifest, documents, experiment=experiment, **CONFIG, now=NOW)
    assert len(calls) == len(PAIRS) * CONFIG["epochs"] - 2
    assert calls[0] == PAIRS[2]
    baseline_path = tmp_path / "baseline"
    baseline_path.mkdir()
    baseline = _fixture(baseline_path)
    expected, expected_artifact = _train(baseline)
    assert model.model_digest == expected.model_digest
    for name in PARAMETERS:
        np.testing.assert_array_equal(getattr(model, name), getattr(expected, name))
    assert artifact.final_loss == expected_artifact.final_loss
    assert artifact.final_margin == expected_artifact.final_margin
    assert artifact.token_count == expected_artifact.token_count
    assert reopened._epoch(manifest.run_id) == 1


def test_completed_preference_reuse_has_no_gradient_update_and_reloads_identical_artifact(
    tmp_path, monkeypatch
):
    fixture = _fixture(tmp_path)
    policy, artifact = _train(fixture)
    import skeleton.ai.runtime.training.preference_trainer as module

    def forbidden(*args, **kwargs):
        raise AssertionError("completed candidate must not repeat an update")

    monkeypatch.setattr(module, "preference_objective_and_gradients", forbidden)
    reused, reused_artifact = _train(fixture)
    assert reused.model_digest == policy.model_digest
    assert reused_artifact == artifact
    assert fixture[2].load_artifact(artifact.run_id)[1] == artifact


@pytest.mark.parametrize(
    "budget",
    [
        {"max_steps": 1},
        {"max_pairs": 1},
        {"max_updates": 1},
        {"max_documents": 1},
        {"max_training_bytes": 1},
        {"max_epochs": 1},
        {"max_corpus_bytes": 1},
    ],
)
def test_cumulative_budget_denies_before_any_preference_run_or_update(tmp_path, budget):
    fixture = _fixture(tmp_path, budget=budget)
    with pytest.raises(TrainingStateError, match="budget"):
        _train(fixture)
    with pytest.raises(KeyError):
        fixture[1].state("preference-run")


@pytest.mark.parametrize("kind", ["preference", "parent"])
def test_revocation_prevents_resume_and_completed_artifact_loading(tmp_path, kind):
    fixture = _fixture(tmp_path)
    _train(fixture)
    datasets, _runs, trainer, manifest, _experiment, _parent, _artifact = fixture
    dataset_digest = (
        manifest.dataset_digest if kind == "preference" else fixture[1].manifest("parent-run").dataset_digest
    )
    source = datasets.dataset(dataset_digest).source_ingest_digests[0]
    datasets.revoke_source_rights(source, reason="withdrawn", command_id="revoke-" + kind)
    with pytest.raises(PermissionError):
        trainer.load_artifact(manifest.run_id)
    with pytest.raises(PermissionError):
        _train(fixture)


@pytest.mark.parametrize("malformed", ['{"reward":1}', '{"schema_version":"other"}', "{}"])
def test_scalar_reward_or_unknown_document_does_not_enter_optimizer(malformed):
    with pytest.raises(TrainingStateError, match="document"):
        PreferencePair.from_document(malformed)


def test_reordered_or_unmaterialized_pairs_are_rejected_before_candidate_registration(tmp_path):
    fixture = _fixture(tmp_path)
    datasets, runs, trainer, manifest, experiment, _parent, _artifact = fixture
    corpus = datasets.training_corpus(manifest.dataset_digest)
    with pytest.raises((ValueError, TrainingStateError)):
        trainer.train(manifest, tuple(reversed(corpus)), experiment=experiment, **CONFIG, now=NOW)
    with pytest.raises(KeyError):
        runs.state(manifest.run_id)


def test_stale_worker_after_computed_gradient_cannot_publish_replacement_work(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    _datasets, runs, _trainer, manifest, _experiment, _parent, _artifact = fixture
    import skeleton.ai.runtime.training.preference_trainer as module

    original = module.preference_objective_and_gradients
    replaced = []

    def superseded(*args, **kwargs):
        result = original(*args, **kwargs)
        runs.recover(manifest.run_id)
        runs.start(manifest.run_id)
        replaced.append(runs.lease_worker(manifest.run_id, "replacement", issued_at=NOW))
        return result

    monkeypatch.setattr(module, "preference_objective_and_gradients", superseded)
    with pytest.raises(TrainingStateError, match="stale"):
        _train(fixture)
    assert runs.latest_checkpoint(manifest.run_id).digest == runs.checkpoints(manifest.run_id)[-1].digest
    assert runs.checkpoint_payload(runs.latest_checkpoint(manifest.run_id))["usage"]["pairs"] == 0
    assert runs.state(manifest.run_id) == "running"
    runs.assert_worker_current(replaced[0])


@pytest.mark.parametrize("field", ["model", "reference", "usage", "cursor", "observations", "optimizer"])
def test_resume_payload_tamper_rejected_even_with_recomputed_payload_digest(tmp_path, monkeypatch, field):
    fixture = _fixture(tmp_path)
    datasets, runs, trainer, manifest, _experiment, _parent, _artifact = fixture
    _interrupt_after_two_updates(monkeypatch, runs)
    with pytest.raises(AbruptStop):
        _train(fixture)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    binding = runs.execution_binding(manifest.run_id)
    payload = runs.checkpoint_payload(checkpoint)
    if field in {"model", "reference"}:
        payload[field]["parameters"]["output_bias"][0] += 0.1
    elif field == "usage":
        payload[field]["steps"] -= 1
    elif field == "cursor":
        payload[field]["pair_index"] += 1
    elif field == "observations":
        payload[field]["initial"]["loss"] += 1
    else:
        payload[field]["learning_rate"] += 1
    changed = replace(checkpoint, payload_digest=_digest(payload))
    with pytest.raises((TrainingStateError, ValueError)):
        trainer._restore(
            manifest, binding, changed, datasets.training_corpus(manifest.dataset_digest), payload=payload
        )


def test_parent_lineage_manifest_and_experiment_mismatches_fail_before_candidate(tmp_path):
    fixture = _fixture(tmp_path)
    datasets, runs, trainer, manifest, experiment, _parent, _artifact = fixture
    corpus = datasets.training_corpus(manifest.dataset_digest)
    for wrong_manifest, wrong_experiment in (
        (replace(manifest, base_model_digest="0" * 64), experiment),
        (manifest, replace(experiment, algorithm="scalar-reward")),
        (manifest, replace(experiment, objective="reward")),
    ):
        with pytest.raises(TrainingStateError):
            trainer.train(wrong_manifest, corpus, experiment=wrong_experiment, **CONFIG, now=NOW)
    with pytest.raises(KeyError):
        runs.state(manifest.run_id)


def test_pref_doc_bounds_and_canonical_schema_are_explicit():
    with pytest.raises(ValueError):
        PreferencePair("p", "same", "same")
    with pytest.raises(ValueError):
        PreferencePair("p" * 1025, "yes", "no")
    with pytest.raises(ValueError):
        PreferencePair("p", "yes" * 400, "no")
    with pytest.raises(TrainingStateError):
        PreferencePair.from_document(json.dumps(json.loads(PAIRS[0].document)))


@pytest.mark.parametrize("kind", ["preference", "parent"])
def test_revocation_during_true_gradient_prevents_checkpoint_and_candidate_escape(
    tmp_path, monkeypatch, kind
):
    fixture = _fixture(tmp_path)
    datasets, runs, _trainer, manifest, _experiment, _parent, _artifact = fixture
    import skeleton.ai.runtime.training.preference_trainer as module

    original = module.preference_objective_and_gradients
    dataset_digest = (
        manifest.dataset_digest if kind == "preference" else runs.manifest("parent-run").dataset_digest
    )
    source = datasets.dataset(dataset_digest).source_ingest_digests[0]

    def revoked(*args, **kwargs):
        gradient = original(*args, **kwargs)
        datasets.revoke_source_rights(source, reason="revoked during update", command_id="during-gradient")
        return gradient

    monkeypatch.setattr(module, "preference_objective_and_gradients", revoked)
    with pytest.raises(PermissionError):
        _train(fixture)
    assert runs.state(manifest.run_id) == "failed"
    assert len(runs.checkpoints(manifest.run_id)) == 1
    assert runs.checkpoint_payload(runs.latest_checkpoint(manifest.run_id))["usage"]["pairs"] == 0


def test_failed_pair_payload_commit_is_atomic_and_retry_continues_initial_state(tmp_path):
    fixture = _fixture(tmp_path)
    _datasets, runs, _trainer, manifest, _experiment, _parent, _artifact = fixture
    import sqlite3

    runs._db.execute(
        """CREATE TEMP TRIGGER reject_preference_payload BEFORE INSERT ON training_checkpoint_payload
        WHEN (SELECT COUNT(*) FROM training_checkpoint WHERE run_id='preference-run')>1
        BEGIN SELECT RAISE(ABORT,'pair payload crash'); END"""
    )
    with pytest.raises(sqlite3.IntegrityError, match="pair payload crash"):
        _train(fixture)
    checkpoints = runs.checkpoints(manifest.run_id)
    assert len(checkpoints) == 1
    assert runs.checkpoint_payload(checkpoints[0])["usage"]["pairs"] == 0
    assert runs.state(manifest.run_id) == "failed"
    runs._db.execute("DROP TRIGGER reject_preference_payload")
    policy, artifact = _train(fixture)
    assert runs._epoch(manifest.run_id) == 1
    assert artifact.update_count == CONFIG["epochs"] * len(PAIRS)
    assert policy.model_digest != artifact.reference_model_digest


def test_crash_after_finished_checkpoint_terminalizes_without_preference_update(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    _datasets, runs, _trainer, manifest, _experiment, _parent, _artifact = fixture
    complete = runs.complete

    def interrupted(*args, **kwargs):
        raise AbruptStop("before preference completion")

    monkeypatch.setattr(runs, "complete", interrupted)
    with pytest.raises(AbruptStop):
        _train(fixture)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    assert runs.checkpoint_payload(checkpoint)["finished"] is True
    monkeypatch.setattr(runs, "complete", complete)
    import skeleton.ai.runtime.training.preference_trainer as module

    def forbidden(*args, **kwargs):
        raise AssertionError("finished work replayed an update")

    monkeypatch.setattr(module, "preference_objective_and_gradients", forbidden)
    policy, artifact = _train(fixture)
    assert artifact.checkpoint_digest == checkpoint.digest
    assert policy.model_digest == checkpoint.model_digest
    assert runs.state(manifest.run_id) == "completed"


@pytest.mark.parametrize(
    "field", ["parent_run_id", "parent_checkpoint_digest", "parent_model_digest", "evaluation_suite_digest"]
)
def test_reserved_manifest_lineage_drift_rejected_before_candidate_registration(tmp_path, field):
    fixture = _fixture(tmp_path)
    datasets, runs, trainer, manifest, experiment, _parent, _artifact = fixture
    modified = replace(
        manifest, hyperparameters={field: "wrong-parent" if field == "parent_run_id" else "0" * 64}
    )
    with pytest.raises(TrainingStateError, match="manifest lineage"):
        trainer.train(
            modified,
            datasets.training_corpus(manifest.dataset_digest),
            experiment=experiment,
            **CONFIG,
            now=NOW,
        )
    with pytest.raises(KeyError):
        runs.state(manifest.run_id)


def test_actual_implementation_drift_rejects_completed_reload(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    _train(fixture)
    import skeleton.ai.runtime.training.preference_trainer as module

    monkeypatch.setattr(module, "_implementation_digest", lambda: "0" * 64)
    with pytest.raises(TrainingStateError, match="resume state"):
        fixture[2].load_artifact("preference-run")


@pytest.mark.parametrize(
    "world_size,parallelism,reuse_parent_run",
    [
        (2, "data_parallel", False),
        (2, "single", False),
        (1, "data_parallel", False),
        (1, "model_parallel", False),
        (1, "single", True),
    ],
)
def test_restore_rejects_rehashed_non_single_worker_or_parent_run_candidate(
    tmp_path, world_size, parallelism, reuse_parent_run
):
    fixture = _fixture(tmp_path)
    _train(fixture)
    datasets, runs, trainer, manifest, _experiment, _parent, _artifact = fixture
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    binding = runs.execution_binding(manifest.run_id)
    payload = runs.checkpoint_payload(checkpoint)
    changed_manifest = replace(
        manifest,
        run_id="parent-run" if reuse_parent_run else manifest.run_id,
        world_size=world_size,
        parallelism=parallelism,
    )
    binding["manifest_digest"] = changed_manifest.digest
    if reuse_parent_run:
        policy = NumpyRecurrentLM.from_dict(payload["model"])
        policy.model_id = "skeleton-local-preference:" + changed_manifest.run_id
        payload["model"] = policy.to_dict()
        binding["training_config"]["model_id"] = policy.model_id
    payload["binding_digest"] = _digest(binding)
    changed_checkpoint = replace(
        checkpoint,
        run_id=changed_manifest.run_id,
        manifest_digest=changed_manifest.digest,
        model_digest=payload["model"]["model_digest"],
        payload_digest=_digest(payload),
    )
    with pytest.raises(TrainingStateError, match="distinct single-worker"):
        trainer._restore(
            changed_manifest,
            binding,
            changed_checkpoint,
            datasets.training_corpus(manifest.dataset_digest),
            payload=payload,
        )


@pytest.mark.parametrize(
    "world_size,parallelism", [(2, "single"), (1, "data_parallel"), (2, "data_parallel")]
)
def test_parent_manifest_worker_scope_denied_before_weight_load(
    tmp_path, monkeypatch, world_size, parallelism
):
    fixture = _fixture(tmp_path)
    _datasets, runs, trainer, manifest, _experiment, _parent, _artifact = fixture
    original_manifest = runs.manifest
    wrong_parent = replace(original_manifest("parent-run"), world_size=world_size, parallelism=parallelism)

    def changed(run_id):
        return wrong_parent if run_id == "parent-run" else original_manifest(run_id)

    def forbidden(*args, **kwargs):
        raise AssertionError("inadmissible parent loaded numerical weights")

    monkeypatch.setattr(runs, "manifest", changed)
    monkeypatch.setattr(trainer.parent_trainer, "load_artifact", forbidden)
    with pytest.raises(TrainingStateError, match="parent requires a single-worker"):
        _train(fixture)
    with pytest.raises(KeyError):
        runs.state(manifest.run_id)
