from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import pytest

from skeleton.ai.runtime.inference import LocalInferenceEngine, LocalInferenceRequest
from skeleton.ai.runtime.training import (
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
