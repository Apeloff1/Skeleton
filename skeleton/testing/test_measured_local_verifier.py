"""Actual independent local verifier outputs own measured, restart-safe gates."""

import asyncio
import hashlib
import json
from dataclasses import replace
from types import MethodType

import pytest

from skeleton.ai.runtime.inference import LocalInferenceResult
from skeleton.ai.runtime.training.cli import build_governed_artifact
from skeleton.ai.runtime.training.control import TrainingRepository
from skeleton.ai.runtime.training.data import DatasetRegistry
from skeleton.ai.runtime.training.evaluation import (
    EvaluationCase,
    EvaluationHarness,
    EvaluationLedger,
    EvaluationSuite,
    evaluation_case_passes,
)
from skeleton.ai.runtime.training.evaluation_store import MeasuredEvaluationStore
from skeleton.ai.runtime.training.trainer import ReferenceLocalTrainer
from skeleton.ai.runtime.training.verifier import (
    EvaluationModelSource,
    MeasuredVerifierError,
    MeasuredVerifierRunner,
    VerifierGatePolicy,
    canonical,
    digest,
    parse_verifier_output,
)
from skeleton.learning.model_program import (
    ModelArtifact,
    ModelDevelopmentRegistry,
    ReferenceNGramTrainer,
    TrainingDataset,
    TrainingSpec,
)


class _VoteVerifier:
    """Small local classifier whose votes and confidences are learned from labels."""

    def __init__(self, model_id, votes):
        self.model_id = model_id
        self.votes = votes
        self.calls = []

    def to_dict(self):
        return {"model_id": self.model_id, "votes": self.votes}

    @property
    def model_digest(self):
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()

    def _label(self, answer):
        counts = self.votes.get(answer, {"accept": 0, "reject": 1})
        decision = max(counts, key=lambda label: (counts[label], label))
        return decision, counts[decision] / sum(counts.values())

    def infer(self, request, cancel):
        prompt = json.loads(request.prompt)
        if set(prompt) != {"instruction", "task", "answer"}:
            raise ValueError("verifier prompt contains unauthorized label fields")
        self.calls.append(prompt)
        decision, confidence = self._label(prompt["answer"])
        return LocalInferenceResult(
            text=json.dumps({"decision": decision, "confidence": confidence}),
            model_id=self.model_id,
            model_digest=self.model_digest,
            input_tokens=len(request.rendered_input.split()),
            output_tokens=8,
        )


class _VoteTrainer:
    trainer_id = "test.local-vote-trainer.v1"

    def __init__(self):
        self.model = None

    def train(self, spec, corpora):
        votes = {}
        for document in corpora[spec.dataset_ids[0]]:
            sample = json.loads(document)
            counts = votes.setdefault(sample["answer"], {"accept": 0, "reject": 0})
            counts[sample["decision"]] += 1
        self.model = _VoteVerifier(spec.model_id, votes)
        payload = self.model.to_dict()
        return ModelArtifact(
            model_id=spec.model_id,
            model_digest=self.model.model_digest,
            artifact_digest=digest(payload),
            kind="local-vote-classifier",
            payload=payload,
            training_run_id=spec.run_id,
        ), {"training_documents": len(corpora[spec.dataset_ids[0]])}


def _source(registry, name, documents, trainer=None):
    trainer = trainer or ReferenceNGramTrainer()
    registry.register_dataset(
        TrainingDataset.from_corpus(
            name, documents, source_refs=("fixture:" + name,), rights_refs=("license:owned",)
        )
    )
    artifact, receipt = registry.train(
        TrainingSpec(name + "-run", name, (name,), trainer.trainer_id, "fixture-v1"),
        corpora={name: documents},
        trainer=trainer,
    )
    model = artifact.load_reference_model() if isinstance(trainer, ReferenceNGramTrainer) else trainer.model
    return EvaluationModelSource.from_model_program(registry, receipt, model=model, corpora=(documents,))


def _suite(*, expected="right", prompts=("alpha", "beta")):
    return EvaluationSuite(
        "actual-local-heldout",
        "1",
        tuple(EvaluationCase(p, p, expected, 1) for p in prompts),
        "heldout",
        "a" * 64,
    )


def _sources(
    *, verifier_labels=("accept", "reject"), candidate_word="right", baseline_word="wrong", extra_candidate=()
):
    registry = ModelDevelopmentRegistry()
    candidate = _source(
        registry,
        "candidate",
        (
            "learned alpha " + candidate_word + " fixture",
            "learned beta " + candidate_word + " fixture",
            *extra_candidate,
        ),
    )
    baseline = _source(
        registry,
        "baseline",
        ("learned alpha " + baseline_word + " fixture", "learned beta " + baseline_word + " fixture"),
    )
    documents = tuple(
        json.dumps({"answer": answer, "decision": label})
        for answer, label in zip(("right", "wrong"), verifier_labels)
    )
    verifier = _source(registry, "verifier", documents, _VoteTrainer())
    return registry, (candidate, baseline, verifier)


def _evaluate(runner, sources, *, run_id="measured", suite=None, **kwargs):
    candidate, baseline, verifier = sources
    return asyncio.run(
        runner.evaluate(
            run_id,
            candidate=candidate,
            baseline=baseline,
            verifier=verifier,
            suite=suite or _suite(),
            **kwargs,
        )
    )


def _qualify(runner, receipt, sources):
    return runner.qualify(receipt, **dict(zip(("candidate", "baseline", "verifier"), sources)))


def test_actual_independent_verifier_qualifies_and_proposes_without_gold(tmp_path):
    _registry, sources = _sources()
    ledger = EvaluationLedger(tmp_path / "evaluation.sqlite3")
    runner = MeasuredVerifierRunner(ledger)
    receipt = _evaluate(runner, sources)
    assert receipt.metrics["sample_count"] == 4
    assert receipt.metrics["positive_samples"] == receipt.metrics["negative_samples"] == 2
    assert receipt.metrics["candidate_accuracy"] == 1
    assert receipt.metrics["baseline_accuracy"] == 0
    assert receipt.metrics["false_accept_rate"] == receipt.metrics["false_reject_rate"] == 0
    assert receipt.metrics["calibration_error"] == receipt.metrics["brier_score"] == 0
    qualification = _qualify(runner, receipt, sources)
    assert qualification.status == "qualified_verifier_candidate"
    assert qualification.production_promotion_authorized is False
    reusable = runner.qualified_verifier(qualification, sources[2])
    judgment = asyncio.run(reusable.judge("new independent task", "wrong"))
    assert judgment["decision"] == "reject"
    assert len(sources[2].model.calls) == 5
    for prompt in sources[2].model.calls:
        if set(prompt) != {"instruction", "task", "answer"}:
            raise ValueError("verifier prompt contains unauthorized label fields")
    row = runner.store.case("measured", 0)
    assert row["candidate"]["answer"]["elapsed_ns"] > 0
    assert row["candidate"]["judgment"]["output_tokens"] == 8
    assert ledger._db.execute("SELECT count(*) FROM eval_result").fetchone()[0] == 2
    assert ledger._db.execute("SELECT count(*) FROM verifier_report").fetchone()[0] == 1


@pytest.mark.parametrize(
    "labels,metric",
    [(("accept", "accept"), "false_accept_rate"), (("reject", "reject"), "false_reject_rate")],
)
def test_actual_wrong_verifier_outputs_reject_qualification(tmp_path, labels, metric):
    _, sources = _sources(verifier_labels=labels)
    runner = MeasuredVerifierRunner(EvaluationLedger(tmp_path / "eval.db"))
    receipt = _evaluate(runner, sources)
    assert receipt.metrics[metric] == 1
    qualification = _qualify(runner, receipt, sources)
    assert qualification.status == "rejected"
    assert metric + "_exceeded" in qualification.reasons
    with pytest.raises(MeasuredVerifierError, match="rejected"):
        runner.qualified_verifier(qualification, sources[2])


def test_actual_baseline_regression_and_correlated_wrong_accepts(tmp_path):
    _, sources = _sources(verifier_labels=("accept", "accept"), candidate_word="wrong", baseline_word="other")
    runner = MeasuredVerifierRunner(EvaluationLedger(tmp_path / "eval.db"))
    receipt = _evaluate(runner, sources)
    assert receipt.metrics["jointly_wrong_cases"] == 2
    # Unknown 'other' is rejected by the learned classifier, so errors are independent.
    assert receipt.metrics["correlated_false_accept_rate"] == 0
    assert "insufficient_labeled_class_coverage" in _qualify(runner, receipt, sources).reasons
    _, regressed = _sources(candidate_word="wrong", baseline_word="right")
    receipt = _evaluate(runner, regressed, run_id="regressed")
    assert "candidate_regressed_from_baseline" in _qualify(runner, receipt, regressed).reasons


@pytest.mark.parametrize(
    "raw",
    [
        '{"decision":"accept","confidence":true}',
        '{"decision":"accept","confidence":NaN}',
        '{"decision":"accept","confidence":Infinity}',
        '{"decision":"accept","confidence":0.49}',
        '{"decision":"accept","confidence":1.01}',
        '{"decision":"accept","confidence":1,"confidence":0.8}',
        '{"decision":"accept","confidence":1,"approval":true}',
        '{"decision":"accept","confidence":1} trailing',
        '{"decision":[],"confidence":1}',
        '[{"decision":"accept","confidence":1}]',
        '{"decision":"unknown","confidence":1}',
        " " * 4097,
    ],
)
def test_strict_bounded_verifier_parser(raw):
    with pytest.raises(MeasuredVerifierError):
        parse_verifier_output(raw)


def test_parser_accepts_whitespace_but_only_finite_decision_confidence():
    assert parse_verifier_output(' { "decision": "reject", "confidence": 0.7 } ') == {
        "decision": "reject",
        "confidence": 0.7,
    }
    with pytest.raises(MeasuredVerifierError):
        VerifierGatePolicy(max_false_accept_rate=True)
    with pytest.raises(MeasuredVerifierError):
        VerifierGatePolicy(min_positive_samples=True)


def test_restart_reuses_exact_completed_case_outputs_and_genuine_handles(tmp_path):
    _, sources = _sources()
    path = tmp_path / "eval.db"
    first = MeasuredVerifierRunner(EvaluationLedger(path))
    receipt = _evaluate(first, sources)
    qualification = _qualify(first, receipt, sources)
    calls = len(sources[2].model.calls)
    second = MeasuredVerifierRunner(EvaluationLedger(path))
    recovered = _evaluate(second, sources)
    assert recovered == receipt
    assert recovered is second.receipt("measured")
    assert len(sources[2].model.calls) == calls
    assert _qualify(second, recovered, sources) == qualification
    for forged in (receipt, replace(recovered)):
        with pytest.raises(MeasuredVerifierError, match="issued"):
            _qualify(second, forged, sources)
    with pytest.raises(MeasuredVerifierError, match="issued"):
        second.qualified_verifier(qualification, sources[2])
    with pytest.raises(MeasuredVerifierError, match="immutable"):
        _evaluate(second, sources, seed=1)


def test_partial_case_commit_crash_resumes_without_repeating_completed_case(tmp_path, monkeypatch):
    _, sources = _sources()
    path = tmp_path / "eval.db"
    first = MeasuredVerifierRunner(EvaluationLedger(path))
    original = first.store.record_case

    def fail_second(run_id, index, *args, **kwargs):
        if index == 1:
            raise OSError("injected durable write outage")
        return original(run_id, index, *args, **kwargs)

    monkeypatch.setattr(first.store, "record_case", fail_second)
    with pytest.raises(OSError, match="outage"):
        _evaluate(first, sources)
    assert len(sources[2].model.calls) == 4
    second = MeasuredVerifierRunner(EvaluationLedger(path))
    receipt = _evaluate(second, sources)
    assert receipt.metrics["sample_count"] == 4
    assert len(sources[2].model.calls) == 6
    assert sum(p["task"] == "alpha" for p in sources[2].model.calls) == 2


def test_public_store_cannot_fabricate_actual_output_publication(tmp_path):
    _, sources = _sources()
    runner = MeasuredVerifierRunner(EvaluationLedger(tmp_path / "eval.db"))
    receipt = _evaluate(runner, sources)
    binding = runner.store._load("measured")[0]
    epoch = runner.store.start("fabricated", binding, "forger", 30)
    row = runner.store.case("measured", 0)
    with pytest.raises(MeasuredVerifierError, match="capability"):
        runner.store.record_case("fabricated", 0, row, "forger", epoch)
    with pytest.raises(MeasuredVerifierError, match="capability"):
        runner.store.complete("fabricated", "forger", epoch)
    with pytest.raises(MeasuredVerifierError, match="capability"):
        runner.store.qualify(receipt, sources=sources)
    with pytest.raises(MeasuredVerifierError, match="not issued"):
        MeasuredEvaluationStore(runner.store.ledger, _writer_token=object())
    assert runner.store.case("fabricated", 0) is None


def test_two_connections_lease_epoch_fences_stale_worker(tmp_path, monkeypatch):
    _, sources = _sources()
    path = tmp_path / "eval.db"
    first = MeasuredVerifierRunner(EvaluationLedger(path))
    _evaluate(first, sources)
    binding = first.store._load("measured")[0]
    clock = [100.0]
    monkeypatch.setattr("skeleton.ai.runtime.training.evaluation_store.time.time", lambda: clock[0])
    epoch = first.store.start("leased", binding, "first", 1)
    second = MeasuredVerifierRunner(EvaluationLedger(path))
    with pytest.raises(MeasuredVerifierError, match="active"):
        second.store.start("leased", binding, "second", 30)
    clock[0] = 102.0
    assert second.store.start("leased", binding, "second", 30) == epoch + 1
    with pytest.raises(MeasuredVerifierError, match="stale"):
        first.store.renew("leased", "first", epoch, 30)
    first.store.release("leased", "first", epoch)
    second.store.renew("leased", "second", epoch + 1, 30)


@pytest.mark.parametrize("kind", ["gold", "input", "metric", "report", "missing_case", "oversized_case"])
def test_durable_corruption_fails_closed_even_with_rehashed_case(tmp_path, kind):
    _, sources = _sources()
    ledger = EvaluationLedger(tmp_path / "eval.db")
    runner = MeasuredVerifierRunner(ledger)
    _evaluate(runner, sources)
    if kind in {"gold", "input"}:
        row = runner.store.case("measured", 0)
        if kind == "gold":
            row["candidate"]["gold"] = False
        else:
            row["candidate"]["answer"]["input_digest"] = "b" * 64
        ledger._db.execute(
            "UPDATE measured_eval_case SET payload=?,case_digest=? WHERE case_index=0",
            (canonical(row), digest(row)),
        )
    elif kind == "metric":
        raw = ledger._db.execute("SELECT receipt_json FROM measured_eval_run").fetchone()[0]
        payload = json.loads(raw)
        metrics = json.loads(payload["metrics_json"])
        metrics["false_accept_rate"] = 1
        payload["metrics_json"] = canonical(metrics)
        ledger._db.execute(
            "UPDATE measured_eval_run SET receipt_json=?,receipt_digest=?",
            (canonical(payload), digest(payload)),
        )
    elif kind == "report":
        ledger._db.execute("UPDATE verifier_report SET payload='{}'")
    elif kind == "missing_case":
        ledger._db.execute("DELETE FROM measured_eval_case WHERE case_index=0")
    else:
        ledger._db.execute(
            "UPDATE measured_eval_case SET payload=? WHERE case_index=0", ("x" * (256 * 1024 + 1),)
        )
    ledger._db.commit()
    with pytest.raises(MeasuredVerifierError):
        MeasuredVerifierRunner(EvaluationLedger(tmp_path / "eval.db")).receipt("measured")


def test_heldout_contamination_and_self_verifier_rejected_before_inference(tmp_path):
    _, sources = _sources(extra_candidate=("alpha",))
    runner = MeasuredVerifierRunner(EvaluationLedger(tmp_path / "eval.db"))
    with pytest.raises(MeasuredVerifierError, match="held-out"):
        _evaluate(runner, sources)
    assert sources[2].model.calls == []
    _, sources = _sources()
    with pytest.raises(MeasuredVerifierError, match="distinct"):
        _evaluate(runner, (sources[0], sources[1], sources[0]))


def test_helper_runtime_mutation_after_qualification_rejected(tmp_path):
    _, sources = _sources()
    runner = MeasuredVerifierRunner(EvaluationLedger(tmp_path / "eval.db"))
    qualification = _qualify(runner, _evaluate(runner, sources), sources)

    def altered(self, answer):
        return "accept", 1.0

    sources[2].model._label = MethodType(altered, sources[2].model)
    with pytest.raises(MeasuredVerifierError, match="implementation identity"):
        runner.qualified_verifier(qualification, sources[2])


def test_canonical_ngram_helper_override_is_detected():
    _, sources = _sources()

    def changed_choice(self, context, rng):
        return "wrong"

    sources[0].model._choose = MethodType(changed_choice, sources[0].model)
    with pytest.raises(MeasuredVerifierError, match="implementation identity"):
        sources[0].assert_current()


def test_unicode_casefold_harness_and_measured_gold_agree(tmp_path):
    _, sources = _sources(candidate_word="STRASSE")
    suite = _suite(expected="Straße")
    harness = asyncio.run(EvaluationHarness().evaluate(sources[0].model, suite))
    assert harness.accuracy == 1
    assert evaluation_case_passes(suite.cases[0], "STRASSE")
    receipt = _evaluate(MeasuredVerifierRunner(EvaluationLedger(tmp_path / "eval.db")), sources, suite=suite)
    assert receipt.metrics["candidate_accuracy"] == 1


def test_actual_native_cli_training_artifact_whitespace_and_revocation(tmp_path):
    native_sources = []
    resources = []
    for role, word in (("candidate", "right"), ("baseline", "wrong")):
        directory = tmp_path / role
        directory.mkdir()
        corpus = directory / "corpus.txt"
        corpus.write_text("  learned alpha " + word + " fixture  ", encoding="utf-8")
        result = build_governed_artifact(
            corpus_paths=(corpus,),
            state_directory=directory / "state",
            output_path=directory / "model.json",
            run_id=role,
            dataset_id=role + "-data",
            rights_refs=("license:owned",),
            algorithm="reference",
        )
        datasets = DatasetRegistry(directory / "state" / "datasets.sqlite3")
        runs = TrainingRepository(directory / "state" / "training.sqlite3")
        trainer = ReferenceLocalTrainer(datasets, runs)
        source = EvaluationModelSource.from_training(trainer, role)
        assert source.payload["corpus_digests"] == [
            source.payload["training_identity"]["artifact"]["corpus_digest"]
        ]
        assert datasets.training_corpus(result["dataset_digest"]) == (
            "  learned alpha " + word + " fixture  ",
        )
        native_sources.append(source)
        resources.append((datasets, runs, result))
    _, legacy = _sources()
    sources = (*native_sources, legacy[2])
    runner = MeasuredVerifierRunner(EvaluationLedger(tmp_path / "eval.db"))
    receipt = _evaluate(runner, sources, suite=_suite(prompts=("alpha",)))
    assert receipt.metrics["sample_count"] == 2
    qualification = _qualify(runner, receipt, sources)
    assert qualification.production_promotion_authorized is False
    datasets, runs, result = resources[0]
    materialized = datasets.materialized_sources(result["dataset_digest"])[0]
    datasets.revoke_source_rights(
        materialized.envelope.content_digest, reason="fixture license revoked", command_id="revoke-fixture"
    )
    with pytest.raises(PermissionError, match="revoked"):

        _qualify(runner, receipt, sources)
    assert runner.receipt("measured") == receipt
    for datasets, runs, _ in resources:
        runs.close()
        datasets.close()


def test_empirical_calibration_comes_from_learned_confidence(tmp_path):
    registry, (candidate, baseline, _) = _sources()
    documents = tuple(
        json.dumps({"answer": answer, "decision": decision, "sample": index})
        for answer, labels in (
            ("right", ("accept", "accept", "accept", "reject")),
            ("wrong", ("reject", "reject", "reject", "accept")),
        )
        for index, decision in enumerate(labels)
    )
    verifier = _source(registry, "less-calibrated", documents, _VoteTrainer())
    sources = (candidate, baseline, verifier)
    runner = MeasuredVerifierRunner(EvaluationLedger(tmp_path / "eval.db"))
    receipt = _evaluate(runner, sources)
    assert receipt.metrics["calibration_error"] == pytest.approx(0.25)
    assert receipt.metrics["brier_score"] == pytest.approx(0.0625)
    assert receipt.metrics["false_accept_rate"] == 0
    assert "calibration_error_exceeded" in _qualify(runner, receipt, sources).reasons


def test_actual_correlated_wrong_accepts_are_measured(tmp_path):
    _, sources = _sources(verifier_labels=("accept", "accept"), candidate_word="wrong", baseline_word="wrong")
    runner = MeasuredVerifierRunner(EvaluationLedger(tmp_path / "eval.db"))
    receipt = _evaluate(runner, sources)
    assert receipt.metrics["jointly_wrong_cases"] == 2
    assert receipt.metrics["correlated_false_accepts"] == 2
    assert receipt.metrics["correlated_false_accept_rate"] == 1
    assert "correlated_false_accept_rate_exceeded" in _qualify(runner, receipt, sources).reasons


def test_observed_shared_training_rejects_independent_verifier_gate(tmp_path):
    shared = json.dumps({"answer": "right", "decision": "accept"})
    _, sources = _sources(extra_candidate=(shared,))
    runner = MeasuredVerifierRunner(EvaluationLedger(tmp_path / "eval.db"))
    receipt = _evaluate(runner, sources)
    qualification = _qualify(runner, receipt, sources)
    assert "verifier_training_overlaps_generator_training" in qualification.reasons


@pytest.mark.parametrize("corruption", ["metadata", "orphan", "trigger"])
def test_measured_schema_authority_rejects_corruption(tmp_path, corruption):
    ledger = EvaluationLedger(tmp_path / "eval.db")
    MeasuredVerifierRunner(ledger)
    if corruption == "metadata":
        ledger._db.execute("DELETE FROM measured_eval_metadata")
    elif corruption == "orphan":
        ledger._db.execute("INSERT INTO measured_eval_case VALUES('orphan',0,'{}',?)", ("a" * 64,))
    else:
        ledger._db.execute(
            "CREATE TRIGGER forged_measured_insert AFTER INSERT ON measured_eval_case BEGIN DELETE FROM measured_eval_case; END"
        )
    ledger._db.commit()
    with pytest.raises(MeasuredVerifierError):
        MeasuredVerifierRunner(ledger)


def test_backend_dispatch_alias_to_existing_helper_is_detected():
    _, sources = _sources()
    verifier = sources[2].model
    # Aliasing an already-fingerprinted method still changes the dispatch edge.
    verifier.infer = MethodType(type(verifier)._label, verifier)
    with pytest.raises(MeasuredVerifierError, match="implementation identity"):
        sources[2].assert_current()
