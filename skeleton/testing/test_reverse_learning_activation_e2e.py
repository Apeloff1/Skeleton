from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import hashlib
import json
from pathlib import Path
import threading
from uuid import uuid4

import pytest

from skeleton.ai.runtime.inference.local import (
    LocalInferenceRequest,
    ReferenceNGramModel,
)
from skeleton.ai.runtime.inference.training_methods import TrainingMethod
from skeleton.ai.runtime.product.activation import (
    build_local_model_activation_manifest,
    load_local_model_activation_manifest,
    write_local_model_activation_manifest,
)
from skeleton.ai.runtime.product.learning import (
    build_learning_candidate,
    build_learning_candidate_artifact,
)
from skeleton.ai.runtime.product.lifecycle import (
    ModelLifecycleRegistry,
    ModelLifecycleState,
)
from skeleton.ai.runtime.product.model_program_bridge import (
    bridge_product_training_to_model_program,
    model_promotion_receipt_from_qualification,
)
from skeleton.ai.runtime.product.qualification import (
    MirrorModelBinding,
    qualify_learning_candidate,
)
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
)
from skeleton.eval.experiment_registry import (
    ExperimentBudget,
    ExperimentEligibility,
    ExperimentManifest,
    ExperimentMetric,
    MetricDirection,
    TrafficMode,
)
from skeleton.eval.firewall import (
    EvaluationFirewall,
    EvaluationSet,
    EvaluatorIdentity,
)
from skeleton.provider_runtime import ProviderRegistry, ProviderRequest
from skeleton.learning.mirror_room import (
    EpisodeOutcome,
    MirrorBudget,
    MirrorCandidate,
    MirrorMetricPolicy,
    MirrorRoom,
    MirrorRoomSpec,
    MirrorScenario,
    SandboxPolicy,
    ScenarioSplit,
    qualify_for_external_promotion,
)


NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_baseline(path: Path) -> tuple[ReferenceNGramModel, str]:
    model = ReferenceNGramModel.train(
        (
            "baseline stable local answer",
            "baseline verified local behavior",
        ),
        order=2,
        model_id="reverse-e2e-baseline",
    )
    path.write_text(
        json.dumps(
            model.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    return model, hashlib.sha256(path.read_bytes()).hexdigest()


def _accepted_turn() -> tuple[ConversationMessage, ConversationMessage]:
    thread_id = str(uuid4())
    branch_id = str(uuid4())
    user_id = str(uuid4())
    assistant_id = str(uuid4())
    user = ConversationMessage(
        message_id=user_id,
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=NOW,
        idempotency_key="reverse-e2e-turn",
        content="Give the verified deterministic local answer.",
        data_class="internal",
    )
    assistant = ConversationMessage(
        message_id=assistant_id,
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=NOW,
        idempotency_key="reverse-e2e-turn:assistant",
        content="Use the verified deterministic local path.",
        parent_message_id=user_id,
        causal_user_message_id=user_id,
        operation_id=str(uuid4()),
        ai_result_id="ai-result:" + _sha("reverse-e2e-result")[:32],
        context_id=str(uuid4()),
        context_digest=_sha("reverse-e2e-context"),
        context_source_snapshot=((str(uuid4()), _sha("source-snapshot")),),
        context_compiler_version="reverse-e2e-compiler-v1",
        provider_receipt_refs=("provider-receipt:reverse-e2e-local",),
        data_class="internal",
    )
    return user, assistant


class _MirrorExecutor:
    executor_id = "reverse-e2e-sandbox-executor"

    def execute(self, *, candidate, scenario, seed, policy):
        score = float(candidate.parameters["score"])
        return EpisodeOutcome(
            metric_values={"quality": score},
            observation_digest=_sha(
                f"{candidate.digest}:{scenario.digest}:{seed}:{score}"
            ),
            steps=1,
            tokens=4,
            cost_units=0.01,
            capabilities_used=("compute",),
        )


class _FixedCandidateGenerator:
    generator_id = "reverse-e2e-generator"

    def __init__(self, candidate: MirrorCandidate) -> None:
        self.candidate = candidate

    def propose(self, feedback, *, limit):
        assert feedback.champion.candidate_id == "baseline-model"
        return (self.candidate,)[:limit]


def _mirror_spec(
    *,
    baseline_model_digest: str,
) -> MirrorRoomSpec:
    baseline = MirrorCandidate(
        candidate_id="baseline-model",
        version="baseline-v1",
        producer_id="release-authority",
        change_ref="model:baseline",
        change_digest=baseline_model_digest,
        parameters={
            "score": 0.2,
            "model_digest": baseline_model_digest,
        },
    )
    manifest = ExperimentManifest(
        experiment_id="reverse-e2e-mirror-v1",
        hypothesis="Qualified local candidate improves the sealed offline quality metric.",
        owner="reverse-learning",
        source_commit="a" * 40,
        environment_id="mirror.offline",
        candidate_ref="candidate:reverse-e2e",
        eligibility=ExperimentEligibility(
            traffic_mode=TrafficMode.OFFLINE,
            max_traffic_fraction=0.0,
            allowed_data_classes=("public",),
            external_side_effects_allowed=False,
        ),
        budget=ExperimentBudget(
            max_samples=16,
            max_tokens=512,
            max_cost_units=1.0,
            max_wall_time_s=60.0,
        ),
        metrics=(
            ExperimentMetric(
                metric_id="quality",
                direction=MetricDirection.MAXIMIZE,
                minimum_samples=1,
                source="reverse-e2e-independent-eval",
            ),
        ),
        tags=("reverse-learning", "activation"),
    )
    return MirrorRoomSpec(
        manifest=manifest,
        production_baseline=baseline,
        metrics=(
            MirrorMetricPolicy(
                metric_id="quality",
                direction=MetricDirection.MAXIMIZE,
                minimum_improvement=0.01,
                confidence_level=0.95,
                weight=1.0,
            ),
        ),
        sandbox_policy=SandboxPolicy(
            allowed_capabilities=("compute",),
            max_steps_per_episode=4,
            max_tokens_per_episode=16,
            max_cost_units_per_episode=0.05,
        ),
        budget=MirrorBudget(
            max_generations=1,
            max_candidates_per_generation=1,
            max_episodes=8,
            max_total_steps=16,
            max_total_tokens=64,
            max_total_cost_units=0.2,
            max_validation_candidate_evaluations=1,
        ),
        hard_example_limit=1,
        stagnation_patience=1,
    )


def _mirror_scenarios() -> tuple[MirrorScenario, ...]:
    return (
        MirrorScenario(
            scenario_id="train-1",
            split=ScenarioSplit.TRAIN,
            payload={"case": "train"},
        ),
        MirrorScenario(
            scenario_id="validation-1",
            split=ScenarioSplit.VALIDATION,
            payload={"case": "validation"},
        ),
        MirrorScenario(
            scenario_id="holdout-1",
            split=ScenarioSplit.HOLDOUT,
            payload={"case": "holdout"},
        ),
    )


def test_reverse_learning_reaches_governed_activation_and_offline_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pytest.importorskip("numpy")

    baseline_path = tmp_path / "baseline.json"
    baseline, _baseline_artifact_sha = _write_baseline(baseline_path)
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", str(baseline_path))

    user, assistant = _accepted_turn()
    learning_candidate = build_learning_candidate(
        (user, assistant),
        accepted_assistant_message_ids=(assistant.message_id,),
    )
    candidate_path = tmp_path / "candidate.json"
    product_receipt = build_learning_candidate_artifact(
        learning_candidate,
        output_path=candidate_path,
        model_id="reverse-e2e-candidate",
        hidden_size=8,
        epochs=1,
        learning_rate=0.03,
        max_vocab=48,
        max_document_tokens=64,
        seed=23,
        temperature=0.7,
        training_methods=(TrainingMethod.SUPERVISED_INSTRUCTION,),
        gradient_accumulation_steps=1,
    )

    assert product_receipt["promotion_state"] == "candidate_only"
    assert (
        product_receipt["evaluation_manifest"]["baseline"]["model_digest"]
        == baseline.model_digest
    )

    bridged = bridge_product_training_to_model_program(
        product_receipt,
        run_id="reverse-e2e-training-run",
        trainer_id="reverse-e2e-training-authority",
        code_revision="reverse-e2e-test",
    )
    lifecycle_registry = ModelLifecycleRegistry()
    candidate_transition = lifecycle_registry.register_candidate(
        bridged,
        authority_id="reverse-e2e-training-registration",
    )
    assert candidate_transition.to_state is ModelLifecycleState.CANDIDATE

    mirror_candidate = MirrorCandidate(
        candidate_id="candidate-model",
        version="candidate-v2",
        producer_id=_FixedCandidateGenerator.generator_id,
        change_ref="model:candidate",
        change_digest=product_receipt["model_digest"],
        parameters={
            "score": 0.8,
            "model_digest": product_receipt["model_digest"],
        },
        parent_candidate_id="baseline-model",
        evidence_refs=(
            "training-plan:"
            + product_receipt["training_plan"]["plan_digest"],
        ),
    )
    spec = _mirror_spec(
        baseline_model_digest=baseline.model_digest,
    )
    mirror_run = MirrorRoom(
        spec,
        _MirrorExecutor(),
    ).learn(
        run_id="reverse-e2e-mirror-run",
        generator=_FixedCandidateGenerator(mirror_candidate),
        scenarios=_mirror_scenarios(),
        generations=1,
    )
    assert mirror_run.eligible_for_external_promotion is True

    mirror_evidence = qualify_for_external_promotion(
        mirror_run,
        verifier_id="reverse-e2e-mirror-verifier",
        evaluation_refs=(
            "eval:reverse-e2e-validation",
            "eval:reverse-e2e-holdout",
        ),
        verified_at=1,
    )

    firewall = EvaluationFirewall()
    holdout = firewall.register_set(
        EvaluationSet(
            set_id="reverse-e2e-promotion-holdout",
            eval_class="promotion_holdout",
            content_digest=_sha("reverse-e2e-firewall-holdout"),
            population_id="standalone-local-ai",
            query_budget=1,
            training_excluded=True,
            metadata={"sealed": True},
        )
    )
    evaluator = firewall.register_evaluator(
        EvaluatorIdentity(
            evaluator_id="reverse-e2e-firewall-evaluator",
            implementation_digest=_sha("reverse-e2e-firewall-code"),
            policy_digest=_sha("reverse-e2e-firewall-policy"),
        )
    )
    firewall.assert_training_exclusion(
        (
            product_receipt["learning_candidate_ref"],
            "training-plan-sha256:"
            + product_receipt["training_plan"]["plan_digest"],
        )
    )
    firewall_candidate_id = (
        "local-model:" + product_receipt["model_digest"]
    )
    firewall.query(
        candidate_id=firewall_candidate_id,
        set_id=holdout.set_id,
        evaluator_id=evaluator.evaluator_id,
        purpose="promotion-qualification",
    )
    firewall_evidence = firewall.promotion_evidence(
        candidate_id=firewall_candidate_id,
        holdout_set_id=holdout.set_id,
        evaluator_id=evaluator.evaluator_id,
    )

    binding = MirrorModelBinding(
        candidate_model_digest=product_receipt["model_digest"],
        baseline_model_digest=baseline.model_digest,
        candidate_artifact_sha256=product_receipt["artifact_sha256"],
        training_plan_digest=product_receipt["training_plan"]["plan_digest"],
        mirror_candidate_id=mirror_evidence.candidate_id,
        mirror_candidate_digest=mirror_evidence.candidate_digest,
        mirror_baseline_candidate_id=mirror_evidence.baseline_candidate_id,
        mirror_baseline_candidate_digest=(
            mirror_evidence.baseline_candidate_digest
        ),
        firewall_candidate_id=firewall_candidate_id,
    )
    qualification = qualify_learning_candidate(
        training_receipt=product_receipt,
        binding=binding,
        mirror_promotion_evidence=mirror_evidence,
        firewall_promotion_evidence=firewall_evidence,
    )
    assert qualification.production_authority is False
    assert qualification.direct_self_modify is False
    validated_transition = lifecycle_registry.validate(
        bridged.artifact.model_digest,
        qualification,
        verifier_id="reverse-e2e-lifecycle-validator",
    )
    assert validated_transition.to_state is ModelLifecycleState.VALIDATED

    promotion = model_promotion_receipt_from_qualification(
        bridged,
        qualification,
        verifier_id="reverse-e2e-model-promotion-verifier",
    )
    promoted_transition = lifecycle_registry.promote(
        bridged.artifact.model_digest,
        promotion,
    )
    assert promoted_transition.to_state is ModelLifecycleState.PROMOTED

    activation = build_local_model_activation_manifest(
        candidate_path=candidate_path,
        baseline_path=baseline_path,
        promotion_receipt=promotion,
        qualification=qualification,
        model_program_bridge_digest=bridged.bridge_digest,
        operator_authorization_ref="operator-authorization:reverse-e2e",
        cache_size=0,
        default_seed=23,
    )
    activation_path = write_local_model_activation_manifest(
        activation,
        tmp_path / "activation.json",
    )
    loaded = load_local_model_activation_manifest(
        activation_path,
        expected_manifest_digest=activation.manifest_digest,
    )
    activated_transition = lifecycle_registry.activate(
        bridged.artifact.model_digest,
        activation,
        deployment_authority_id="reverse-e2e-deployment-authority",
    )
    assert activated_transition.to_state is ModelLifecycleState.ACTIVATED
    assert (
        lifecycle_registry.snapshot(bridged.artifact.model_digest).state
        is ModelLifecycleState.ACTIVATED
    )

    assert loaded.manifest.candidate_model_digest == product_receipt["model_digest"]
    assert loaded.manifest.baseline_model_digest == baseline.model_digest
    assert loaded.manifest.rollback_target()["model_digest"] == baseline.model_digest
    assert loaded.manifest.direct_self_modify is False

    result = loaded.candidate.model.infer(
        LocalInferenceRequest(
            prompt="Give the verified deterministic local answer.",
            max_output_tokens=8,
            seed=23,
        ),
        threading.Event(),
    )
    assert result.model_digest == product_receipt["model_digest"]
    assert result.text is not None and result.text.strip()
    assert result.response_id is not None

    # Prove the exact promoted bytes are selected by the same environment
    # bootstrap used by the real engine provider registry, not merely by a
    # direct test-only artifact loader.
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv(
        "AI_LOCAL_ACTIVATION_MANIFEST",
        str(activation_path),
    )
    monkeypatch.setenv(
        "AI_LOCAL_ACTIVATION_DIGEST",
        activation.manifest_digest,
    )
    monkeypatch.setenv("AI_LOCAL_ACTIVATION_TARGET", "candidate")
    monkeypatch.delenv("AI_LOCAL_MODEL_PATH", raising=False)
    monkeypatch.delenv("AI_LOCAL_MODEL_CACHE_SIZE", raising=False)
    monkeypatch.delenv("AI_LOCAL_MODEL_SEED", raising=False)
    monkeypatch.delenv("AI_SECONDARY_API_KEY", raising=False)
    monkeypatch.delenv("AI_SECONDARY_BASE_URL", raising=False)
    monkeypatch.delenv("AI_SECONDARY_MODEL", raising=False)
    monkeypatch.delenv("AI_VERIFICATION_MODEL", raising=False)

    registry = ProviderRegistry.from_env()
    adapter = registry.active
    assert adapter is not None
    assert adapter.provider_id == "local"
    assert adapter.model == product_receipt["model_id"]
    assert adapter.activation_target == "candidate"
    assert (
        adapter.artifact_receipt.artifact_sha256
        == product_receipt["artifact_sha256"]
    )
    assert (
        adapter.activation_manifest.manifest_digest
        == activation.manifest_digest
    )
    status = adapter.status()
    assert status["network_policy"] == "none"
    assert status["execution_mode"] == "local"
    assert status["activation"]["rollback_required"] is True
    assert status["activation"]["direct_self_modify"] is False

    provider_response = asyncio.run(
        adapter.generate(
            ProviderRequest(
                instructions=(
                    "Answer using only the activated offline local model."
                ),
                prompt="Give the verified deterministic local answer.",
                max_output_tokens=8,
                model=product_receipt["model_id"],
                data_class="internal",
                operation_id="reverse-e2e-activated-provider",
            )
        )
    )
    assert provider_response.provider == "local"
    assert provider_response.model == product_receipt["model_id"]
    assert provider_response.text is not None
    assert provider_response.text.strip()

    # The same digest-pinned manifest must make the exact pre-promotion model
    # executable as the rollback target through the real provider bootstrap.
    monkeypatch.setenv("AI_LOCAL_ACTIVATION_TARGET", "rollback")
    rollback_registry = ProviderRegistry.from_env()
    rollback_adapter = rollback_registry.active
    assert rollback_adapter is not None
    assert rollback_adapter.provider_id == "local"
    assert rollback_adapter.model == baseline.model_id
    assert rollback_adapter.activation_target == "rollback"
    assert (
        rollback_adapter.activation_manifest.manifest_digest
        == activation.manifest_digest
    )
    assert (
        rollback_adapter.artifact_receipt.model_digest
        == baseline.model_digest
    )

    rollback_response = asyncio.run(
        rollback_adapter.generate(
            ProviderRequest(
                instructions=(
                    "Answer using only the authenticated rollback model."
                ),
                prompt="Give the stable baseline local answer.",
                max_output_tokens=8,
                model=baseline.model_id,
                data_class="internal",
                operation_id="reverse-e2e-rollback-provider",
            )
        )
    )
    assert rollback_response.provider == "local"
    assert rollback_response.model == baseline.model_id
    assert rollback_response.text is not None
    assert rollback_response.text.strip()

    rolled_back_transition = lifecycle_registry.rollback(
        bridged.artifact.model_digest,
        activation,
        deployment_authority_id="reverse-e2e-deployment-authority",
    )
    assert (
        rolled_back_transition.to_state
        is ModelLifecycleState.ROLLED_BACK
    )
    final_snapshot = lifecycle_registry.snapshot(
        bridged.artifact.model_digest
    )
    assert final_snapshot.state is ModelLifecycleState.ROLLED_BACK
    assert final_snapshot.rollback_model_digest == baseline.model_digest
    assert lifecycle_registry.verify_history(
        bridged.artifact.model_digest
    ) is True
