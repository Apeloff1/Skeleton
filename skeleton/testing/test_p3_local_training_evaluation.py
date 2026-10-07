from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import pytest

import skeleton.ai.runtime.training.trainer as trainer_module

from skeleton.ai.runtime.inference import LocalInferenceEngine, LocalInferenceRequest
from skeleton.ai.runtime.training import (
    CandidateQualification,
    DataQualityReport,
    DataQualityRule,
    DatasetManifest,
    DatasetRegistry,
    DatasetSplit,
    EvaluationCase,
    EvaluationHarness,
    EvaluationLedger,
    EvaluationSuite,
    IngestEnvelope,
    ReferenceLocalTrainer,
    TrainingEvaluationGate,
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    VerifierReport,
    corpus_digest,
)


NOW=datetime(2026,10,2,10,0,tzinfo=timezone.utc)


def _digest(text:str)->str:
    return hashlib.sha256(text.encode()).hexdigest()


def _fixture(tmp_path):
    corpus=("two plus two four","two plus two four","two plus two four","three plus three six")
    datasets=DatasetRegistry(tmp_path/"datasets.sqlite3")
    ingest=IngestEnvelope.from_bytes(
        source_id="fixture://math",
        payload="\n".join(corpus).encode(),
        parser_version="plain-text@1",
        classification="internal",
        rights=("training","evaluation"),
        trusted=True,
        acquired_at=NOW,
    )
    datasets.register_ingest(ingest)
    dataset=DatasetManifest(
        dataset_id="local-math",
        version="1",
        splits=(DatasetSplit("train",corpus_digest(corpus),len(corpus)),),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training","evaluation"),
        retention_class="model-development",
        parser_versions=("plain-text@1",),
    )
    datasets.register_dataset(dataset)
    datasets.record_quality(DataQualityReport.evaluate(
        dataset.digest,
        (DataQualityRule("validity","valid_fraction",">=",1.0),),
        {"valid_fraction":1.0},
    ))
    runs=TrainingRepository(tmp_path/"runs.sqlite3")
    manifest=TrainingRunManifest(
        run_id="math-train-001",
        dataset_digest=dataset.digest,
        base_model_digest=_digest("empty-reference-model"),
        code_digest=_digest("reference-trainer-v1"),
        environment_digest=_digest("python-3.11"),
        hyperparameters={"order":2},
        seed=23,
        resource_budget={"max_steps":100},
    )
    runs.register_run(manifest,datasets,created_at=NOW)
    return corpus,datasets,runs,manifest


@pytest.mark.asyncio
async def test_registered_dataset_trains_executable_local_model(tmp_path):
    corpus,datasets,runs,manifest=_fixture(tmp_path)
    model,artifact=ReferenceLocalTrainer(datasets,runs).train(
        manifest,corpus,order=2,now=NOW
    )
    assert runs.state(manifest.run_id)=="completed"
    assert artifact.model_digest==model.model_digest
    assert runs.latest_checkpoint(manifest.run_id).model_digest==model.model_digest

    response=await LocalInferenceEngine(model,cache_size=0).generate(
        LocalInferenceRequest(prompt="two plus two",max_output_tokens=3,seed=0)
    )
    assert response.text is not None
    assert "four" in response.text.lower()


def test_training_rejects_corpus_not_bound_to_registered_split(tmp_path):
    corpus,datasets,runs,manifest=_fixture(tmp_path)
    with pytest.raises(ValueError,match="registered split digest"):
        ReferenceLocalTrainer(datasets,runs).train(
            manifest,("different corpus",),order=2,now=NOW
        )


@pytest.mark.asyncio
async def test_candidate_requires_versioned_eval_and_independent_verifier(tmp_path):
    corpus,datasets,runs,manifest=_fixture(tmp_path)
    model,_=ReferenceLocalTrainer(datasets,runs).train(manifest,corpus,order=2,now=NOW)
    suite=EvaluationSuite(
        suite_id="math-core",
        version="1.0.0",
        cases=(
            EvaluationCase("two-plus-two","two plus two","four",3),
            EvaluationCase("three-plus-three","three plus three","six",3),
        ),
        population="fixture arithmetic prompts",
        contamination_fingerprint=_digest("math-core-cases-v1"),
    )
    ledger=EvaluationLedger(tmp_path/"eval.sqlite3")
    ledger.register_suite(suite)
    result=await EvaluationHarness().evaluate(model,suite,seed=0)
    ledger.record_result(result)
    assert result.accuracy==1.0

    verifier=VerifierReport(
        verifier_id="independent-fixture-verifier",
        verifier_model_digest=_digest("different-verifier-model"),
        candidate_model_digest=model.model_digest,
        calibration_error=0.01,
        false_accept_rate=0.0,
        false_reject_rate=0.0,
        sample_count=100,
    )
    qualification=TrainingEvaluationGate(
        min_accuracy=1.0,
        max_calibration_error=0.05,
        max_false_accept_rate=0.01,
    ).qualify(result,verifier)
    assert qualification.status=="qualified_candidate"
    assert qualification.as_dict()["production_promotion_authorized"] is False
    assert ledger.record_verifier(verifier)==verifier.digest
    ledger.record_qualification(qualification)


@pytest.mark.asyncio
async def test_candidate_cannot_self_verify(tmp_path):
    corpus,datasets,runs,manifest=_fixture(tmp_path)
    model,_=ReferenceLocalTrainer(datasets,runs).train(manifest,corpus,order=2,now=NOW)
    suite=EvaluationSuite(
        suite_id="single",
        version="1",
        cases=(EvaluationCase("case","two plus two","four",3),),
        population="fixture",
        contamination_fingerprint=_digest("single"),
    )
    result=await EvaluationHarness().evaluate(model,suite)
    verifier=VerifierReport(
        verifier_id="self",
        verifier_model_digest=model.model_digest,
        candidate_model_digest=model.model_digest,
        calibration_error=0.0,
        false_accept_rate=0.0,
        false_reject_rate=0.0,
        sample_count=10,
    )
    qualification=TrainingEvaluationGate(
        min_accuracy=1.0,
        max_calibration_error=0.1,
        max_false_accept_rate=0.1,
    ).qualify(result,verifier)
    assert qualification.status=="rejected"
    assert "verifier_not_independent" in qualification.reasons


def test_evaluation_suite_version_is_immutable(tmp_path):
    ledger=EvaluationLedger(tmp_path/"eval.sqlite3")
    suite=EvaluationSuite(
        suite_id="immutable",
        version="1",
        cases=(EvaluationCase("a","x","y"),),
        population="fixture",
        contamination_fingerprint=_digest("suite-a"),
    )
    ledger.register_suite(suite)
    drifted=EvaluationSuite(
        suite_id="immutable",
        version="1",
        cases=(EvaluationCase("a","changed","y"),),
        population="fixture",
        contamination_fingerprint=_digest("suite-a"),
    )
    with pytest.raises(ValueError,match="immutable"):
        ledger.register_suite(drifted)

def test_evaluation_result_requires_exact_disjoint_case_partition():
    with pytest.raises(ValueError,match="unique and disjoint"):
        from skeleton.ai.runtime.training import EvaluationResult
        EvaluationResult(
            candidate_model_digest=_digest("candidate"),
            suite_digest=_digest("suite"),
            passed_case_ids=("same",),
            failed_case_ids=("same",),
            outputs={"same":"output"},
        )


def test_qualification_requires_registered_verifier_evidence(tmp_path):
    ledger=EvaluationLedger(tmp_path/"eval-evidence.sqlite3")
    suite=EvaluationSuite(
        suite_id="evidence",
        version="1",
        cases=(EvaluationCase("case","prompt","expected"),),
        population="fixture",
        contamination_fingerprint=_digest("evidence-suite"),
    )
    ledger.register_suite(suite)
    from skeleton.ai.runtime.training import EvaluationResult
    result=EvaluationResult(
        candidate_model_digest=_digest("candidate-evidence"),
        suite_digest=suite.digest,
        passed_case_ids=("case",),
        failed_case_ids=(),
        outputs={"case":"expected"},
    )
    ledger.record_result(result)
    verifier=VerifierReport(
        verifier_id="independent",
        verifier_model_digest=_digest("verifier-evidence"),
        candidate_model_digest=result.candidate_model_digest,
        calibration_error=0.0,
        false_accept_rate=0.0,
        false_reject_rate=0.0,
        sample_count=10,
    )
    qualification=TrainingEvaluationGate(
        min_accuracy=1.0,
        max_calibration_error=0.1,
        max_false_accept_rate=0.1,
    ).qualify(result,verifier)

    with pytest.raises(ValueError,match="verifier report is not registered"):
        ledger.record_qualification(qualification)


def test_qualification_candidate_must_match_stored_result(tmp_path):
    ledger=EvaluationLedger(tmp_path/"eval-join.sqlite3")
    suite=EvaluationSuite(
        suite_id="join",
        version="1",
        cases=(EvaluationCase("case","prompt","expected"),),
        population="fixture",
        contamination_fingerprint=_digest("join-suite"),
    )
    ledger.register_suite(suite)
    from skeleton.ai.runtime.training import EvaluationResult
    result=EvaluationResult(
        candidate_model_digest=_digest("candidate-a"),
        suite_digest=suite.digest,
        passed_case_ids=("case",),
        failed_case_ids=(),
        outputs={"case":"expected"},
    )
    ledger.record_result(result)
    verifier=VerifierReport(
        verifier_id="join-verifier",
        verifier_model_digest=_digest("independent-verifier"),
        candidate_model_digest=_digest("candidate-b"),
        calibration_error=0.0,
        false_accept_rate=0.0,
        false_reject_rate=0.0,
        sample_count=10,
    )
    ledger.record_verifier(verifier)
    forged=CandidateQualification(
        candidate_model_digest=_digest("candidate-b"),
        evaluation_result_digest=result.digest,
        verifier_report_digest=verifier.digest,
        status="qualified_candidate",
        reasons=(),
    )

    with pytest.raises(ValueError,match="does not match evaluation result"):
        ledger.record_qualification(forged)



def test_reference_trainer_fails_before_execution_when_step_budget_is_exceeded(
    tmp_path,
):
    corpus,datasets,runs,manifest=_fixture(tmp_path)
    constrained=TrainingRunManifest(
        run_id="budgeted-run",
        dataset_digest=manifest.dataset_digest,
        base_model_digest=manifest.base_model_digest,
        code_digest=manifest.code_digest,
        environment_digest=manifest.environment_digest,
        hyperparameters=manifest.hyperparameters,
        seed=manifest.seed,
        resource_budget={"max_steps":3},
    )

    with pytest.raises(TrainingStateError,match="training budget exceeded: max_steps"):
        ReferenceLocalTrainer(datasets,runs).train(
            constrained,
            corpus,
            order=2,
            now=NOW,
        )

    with pytest.raises(KeyError):
        runs.state(constrained.run_id)


def test_reference_trainer_rejects_distributed_topology_it_cannot_execute(
    tmp_path,
):
    corpus,datasets,runs,manifest=_fixture(tmp_path)
    distributed=TrainingRunManifest(
        run_id="distributed-run",
        dataset_digest=manifest.dataset_digest,
        base_model_digest=manifest.base_model_digest,
        code_digest=manifest.code_digest,
        environment_digest=manifest.environment_digest,
        hyperparameters=manifest.hyperparameters,
        seed=manifest.seed,
        world_size=2,
        parallelism="data_parallel",
        resource_budget={"max_steps":100},
    )

    with pytest.raises(
        TrainingStateError,
        match="only supports world_size=1 and parallelism=single",
    ):
        ReferenceLocalTrainer(datasets,runs).train(
            distributed,
            corpus,
            order=2,
            now=NOW,
        )

    with pytest.raises(KeyError):
        runs.state(distributed.run_id)


def test_reference_trainer_enforces_document_and_byte_budgets(tmp_path):
    corpus,datasets,runs,manifest=_fixture(tmp_path)
    for run_id,budget_name,limit in (
        ("doc-budget","max_documents",len(corpus)-1),
        ("byte-budget","max_corpus_bytes",1),
    ):
        constrained=TrainingRunManifest(
            run_id=run_id,
            dataset_digest=manifest.dataset_digest,
            base_model_digest=manifest.base_model_digest,
            code_digest=manifest.code_digest,
            environment_digest=manifest.environment_digest,
            hyperparameters=manifest.hyperparameters,
            seed=manifest.seed,
            resource_budget={budget_name:limit},
        )
        with pytest.raises(
            TrainingStateError,
            match=f"training budget exceeded: {budget_name}",
        ):
            ReferenceLocalTrainer(datasets,runs).train(
                constrained,
                corpus,
                order=2,
                now=NOW,
            )


def test_reference_trainer_marks_run_failed_on_execution_crash(
    tmp_path,
    monkeypatch,
):
    corpus,datasets,runs,manifest=_fixture(tmp_path)

    def crash(*args,**kwargs):
        raise RuntimeError("injected trainer crash")

    monkeypatch.setattr(
        trainer_module.ReferenceNGramModel,
        "train",
        staticmethod(crash),
    )

    with pytest.raises(RuntimeError,match="injected trainer crash"):
        ReferenceLocalTrainer(datasets,runs).train(
            manifest,
            corpus,
            order=2,
            now=NOW,
        )

    assert runs.state(manifest.run_id)=="failed"
