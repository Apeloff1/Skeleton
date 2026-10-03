from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import pytest

from scripts.check_p3_training_execution_map import validate as validate_authority
from skeleton.ai.runtime.inference import LocalInferenceEngine, LocalInferenceRequest
from skeleton.ai.runtime.training import (
    CurriculumEngine,
    CurriculumStage,
    DataQualityReport,
    DataQualityRule,
    DatasetManifest,
    DatasetRegistry,
    DatasetSplit,
    DeterministicRLEnvironment,
    EvaluationCase,
    EvaluationHarness,
    EvaluationLedger,
    EvaluationResult,
    EvaluationSuite,
    IngestEnvelope,
    PostTrainingExperiment,
    PostTrainingLedger,
    RLEnvironmentSpec,
    ReferenceLocalTrainer,
    TrainingEvaluationGate,
    TrainingRepository,
    TrainingRunManifest,
    VerifierReport,
    corpus_digest,
)


NOW=datetime(2026,10,2,12,0,tzinfo=timezone.utc)


def _digest(text:str)->str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.asyncio
async def test_p3_t2_provider_independent_training_transaction(tmp_path):
    authority=validate_authority()
    assert authority["scheduled_volume_count"]==19
    assert authority["queued_volume_count"]==178

    corpus=(
        "two plus two four",
        "two plus two four",
        "two plus two four",
        "three plus three six",
    )
    datasets=DatasetRegistry(tmp_path/"datasets.sqlite3")
    ingest=IngestEnvelope.from_bytes(
        source_id="acceptance://math",
        payload="\n".join(corpus).encode(),
        parser_version="acceptance-parser@1",
        classification="internal",
        rights=("training","evaluation"),
        trusted=True,
        acquired_at=NOW,
    )
    datasets.register_ingest(ingest)
    dataset=DatasetManifest(
        dataset_id="p3-t2-acceptance",
        version="1",
        splits=(DatasetSplit("train",corpus_digest(corpus),len(corpus)),),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training","evaluation"),
        retention_class="acceptance",
        parser_versions=("acceptance-parser@1",),
    )
    datasets.register_dataset(dataset)
    datasets.record_quality(DataQualityReport.evaluate(
        dataset.digest,
        (
            DataQualityRule("validity","valid_fraction",">=",1.0,True),
            DataQualityRule("duplicates","duplicate_fraction","<=",0.8,True),
        ),
        {"valid_fraction":1.0,"duplicate_fraction":0.5},
    ))
    assert datasets.require_training_ready(dataset.digest).digest==dataset.digest

    runs=TrainingRepository(tmp_path/"training.sqlite3")
    run=TrainingRunManifest(
        run_id="p3-t2-acceptance-run",
        dataset_digest=dataset.digest,
        base_model_digest=_digest("blank-local-model"),
        code_digest=_digest("reference-local-trainer"),
        environment_digest=_digest("python-3.11"),
        hyperparameters={"order":2},
        seed=42,
        world_size=1,
        parallelism="single",
        resource_budget={"max_steps":100},
    )
    runs.register_run(run,datasets,created_at=NOW)
    model,artifact=ReferenceLocalTrainer(datasets,runs).train(
        run,corpus,order=2,now=NOW
    )
    assert runs.state(run.run_id)=="completed"
    assert runs.latest_checkpoint(run.run_id).model_digest==model.model_digest
    assert artifact.model_digest==model.model_digest

    direct=await LocalInferenceEngine(model,cache_size=0).generate(
        LocalInferenceRequest(prompt="two plus two",max_output_tokens=3,seed=0)
    )
    assert direct.text is not None and "four" in direct.text.lower()

    suite=EvaluationSuite(
        suite_id="p3-t2-acceptance-suite",
        version="1",
        cases=(
            EvaluationCase("2+2","two plus two","four",3),
            EvaluationCase("3+3","three plus three","six",3),
        ),
        population="deterministic acceptance arithmetic",
        contamination_fingerprint=_digest("p3-t2-suite-v1"),
    )
    eval_ledger=EvaluationLedger(tmp_path/"evaluation.sqlite3")
    eval_ledger.register_suite(suite)
    result=await EvaluationHarness().evaluate(model,suite,seed=0)
    assert result.accuracy==1.0
    eval_ledger.record_result(result)

    verifier=VerifierReport(
        verifier_id="p3-t2-independent-verifier",
        verifier_model_digest=_digest("independent-verifier"),
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
    assert eval_ledger.record_verifier(verifier)==verifier.digest
    eval_ledger.record_qualification(qualification)

    post=PostTrainingLedger(tmp_path/"post.sqlite3")
    experiment=PostTrainingExperiment(
        experiment_id="p3-t2-post",
        base_candidate_digest=model.model_digest,
        dataset_digest=dataset.digest,
        objective="exercise bounded post-training acceptance",
        algorithm="deterministic-rl-fixture",
        configuration={"seed":42},
        evaluation_suite_digest=suite.digest,
    )
    post.register_experiment(experiment)
    env_spec=RLEnvironmentSpec(
        environment_id="p3-t2-bandit",
        version="1",
        state_schema_digest=_digest("state"),
        action_schema_digest=_digest("action"),
        reward_logic_digest=_digest("reward"),
    )
    post.register_environment(env_spec)
    env=DeterministicRLEnvironment(
        env_spec,
        rewards={"practice":0.1,"finish":1.0},
        terminal_actions=("finish",),
    )
    env.reset(episode_id="acceptance-episode",seed=42)
    post.record_step(env.step("practice"))
    terminal=env.step("finish")
    post.record_step(terminal)
    assert terminal.terminal is True

    curriculum=CurriculumEngine((
        CurriculumStage("foundation","local model basics","accuracy",0.9),
        CurriculumStage("post","post-training readiness","accuracy",1.0,("foundation",)),
    ))
    foundation=curriculum.decide("foundation",metrics={"accuracy":result.accuracy},completed=())
    assert foundation.status=="advance"
    post.record_curriculum(foundation)
    advanced=curriculum.decide("post",metrics={"accuracy":result.accuracy},completed=("foundation",))
    assert advanced.status=="advance"
    post.record_curriculum(advanced)

def test_evaluation_ledger_rejects_selective_suite_omission(tmp_path):
    suite=EvaluationSuite(
        suite_id="full-suite",
        version="1",
        cases=(
            EvaluationCase("easy","easy prompt","ok"),
            EvaluationCase("hard","hard prompt","hard"),
        ),
        population="coverage regression",
        contamination_fingerprint=_digest("full-suite"),
    )
    ledger=EvaluationLedger(tmp_path/"coverage.sqlite3")
    ledger.register_suite(suite)
    cherry_picked=EvaluationResult(
        candidate_model_digest=_digest("candidate"),
        suite_digest=suite.digest,
        passed_case_ids=("easy",),
        failed_case_ids=(),
        outputs={"easy":"ok"},
    )

    assert cherry_picked.accuracy==1.0
    with pytest.raises(ValueError,match="cover every registered suite case"):
        ledger.record_result(cherry_picked)


def test_evaluation_ledger_rejects_unknown_case_substitution(tmp_path):
    suite=EvaluationSuite(
        suite_id="identity-suite",
        version="1",
        cases=(EvaluationCase("canonical","prompt","expected"),),
        population="identity regression",
        contamination_fingerprint=_digest("identity-suite"),
    )
    ledger=EvaluationLedger(tmp_path/"identity.sqlite3")
    ledger.register_suite(suite)
    substituted=EvaluationResult(
        candidate_model_digest=_digest("candidate"),
        suite_digest=suite.digest,
        passed_case_ids=("easier-substitute",),
        failed_case_ids=(),
        outputs={"easier-substitute":"expected"},
    )

    with pytest.raises(ValueError,match="cover every registered suite case"):
        ledger.record_result(substituted)


def test_evaluation_ledger_detects_stored_suite_corruption(tmp_path):
    suite=EvaluationSuite(
        suite_id="durable-suite",
        version="1",
        cases=(EvaluationCase("case","prompt","expected"),),
        population="durable regression",
        contamination_fingerprint=_digest("durable-suite"),
    )
    ledger=EvaluationLedger(tmp_path/"durable.sqlite3")
    ledger.register_suite(suite)
    result=EvaluationResult(
        candidate_model_digest=_digest("candidate"),
        suite_digest=suite.digest,
        passed_case_ids=("case",),
        failed_case_ids=(),
        outputs={"case":"expected"},
    )
    import json
    payload=suite.as_dict()
    payload["population"]="tampered population"
    ledger._db.execute(
        "UPDATE eval_suite SET payload=? WHERE suite_digest=?",
        (json.dumps(payload,sort_keys=True,separators=(",",":")),suite.digest),
    )
    ledger._db.commit()

    with pytest.raises(ValueError,match="suite digest mismatch"):
        ledger.record_result(result)

