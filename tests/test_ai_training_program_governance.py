from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math

import pytest

from skeleton.ai.learning.model_program import (
    ModelArtifact,
    ModelDevelopmentRegistry,
    ModelProgramError,
    ReferenceNGramTrainer,
    TrainingDataset,
    TrainingReceipt,
    TrainingSpec,
    corpus_digest,
)
from skeleton.ai.learning.training_integrity import (
    IntegritySignal,
    SourceIntegrityDecision,
    TrainingIntegrityError,
    TrainingIntegrityGate,
    TrainingIntegrityReceipt,
    TransformIdentity,
)
from skeleton.ai.learning.promotion_control import (
    CanaryEvidence,
    EvaluationBundle,
    ImprovementCandidate,
    PromotionLedger,
    PromotionStatus,
    decide,
    promote_with_canary,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def corpus() -> tuple[str, ...]:
    return (
        "alpha beta gamma",
        "alpha beta delta",
        "beta gamma delta",
        "alpha gamma epsilon",
    )


def dataset(
    *,
    dataset_id: str = "dataset-a",
    documents: Sequence[str] | None = None,
    metadata: Mapping[str, object] | None = None,
) -> TrainingDataset:
    docs = tuple(documents or corpus())
    return TrainingDataset.from_corpus(
        dataset_id,
        docs,
        source_refs=("source:a",),
        rights_refs=("rights:training",),
        lineage_refs=("lineage:fixture",),
        metadata={} if metadata is None else metadata,
    )


def transform(
    *,
    transform_id: str = "normalize-v1",
    code: str = "transform-code",
    config: str = "transform-config",
) -> TransformIdentity:
    return TransformIdentity(
        transform_id=transform_id,
        implementation_digest=sha(code),
        configuration_digest=sha(config),
        signer_ref="sigstore:fixture",
    )


def signals(
    source_id: str = "source:a",
    *,
    fail_kind: str | None = None,
    suffix: str = "",
) -> tuple[IntegritySignal, ...]:
    result: list[IntegritySignal] = []
    for kind in (
        "content-anomaly",
        "label-anomaly",
        "source-ablation",
        "trigger-canary",
    ):
        result.append(
            IntegritySignal(
                source_id=source_id,
                kind=kind,
                detector_id=f"detector:{kind}{suffix}",
                detector_digest=sha(
                    f"detector:{kind}:v1{suffix}"
                ),
                passed=kind != fail_kind,
                evidence_ref=f"evidence:{source_id}:{kind}{suffix}",
                score=0.1,
            )
        )
    return tuple(result)


def integrity_receipt(
    selected: TrainingDataset,
    *,
    policy: str = "policy-v1",
    fail_kind: str | None = None,
    suffix: str = "",
) -> TrainingIntegrityReceipt:
    return TrainingIntegrityGate(
        policy_digest=sha(policy)
    ).evaluate(
        dataset_id=selected.dataset_id,
        dataset_digest=selected.content_digest,
        source_digests={"source:a": sha("source-a")},
        transforms=(transform(),),
        signals=signals(
            "source:a",
            fail_kind=fail_kind,
            suffix=suffix,
        ),
    )


def training_spec(
    *,
    run_id: str = "run-1",
    model_id: str = "model-1",
    dataset_ids: tuple[str, ...] = ("dataset-a",),
    trainer_id: str = ReferenceNGramTrainer.trainer_id,
    code_revision: str = "revision-1",
    seed: int = 7,
    hyperparameters: Mapping[str, object] | None = None,
) -> TrainingSpec:
    return TrainingSpec(
        run_id=run_id,
        model_id=model_id,
        dataset_ids=dataset_ids,
        trainer_id=trainer_id,
        code_revision=code_revision,
        seed=seed,
        hyperparameters=(
            {"order": 2}
            if hyperparameters is None
            else hyperparameters
        ),
    )


class CountingTrainer:
    trainer_id = ReferenceNGramTrainer.trainer_id

    def __init__(self) -> None:
        self.calls = 0
        self._delegate = ReferenceNGramTrainer()

    def train(
        self,
        spec: TrainingSpec,
        corpora: Mapping[str, Sequence[str]],
    ):
        self.calls += 1
        return self._delegate.train(spec, corpora)


class WrongRunTrainer:
    trainer_id = "fixture.wrong-run.v1"

    def train(
        self,
        spec: TrainingSpec,
        corpora: Mapping[str, Sequence[str]],
    ):
        payload = {"kind": "wrong-run", "run": spec.run_id}
        return (
            ModelArtifact(
                model_id=spec.model_id,
                model_digest=sha("wrong-run-model"),
                artifact_digest=stable_digest(payload),
                kind="fixture",
                payload=payload,
                training_run_id="another-run",
            ),
            {"loss": 1.0},
        )


class WrongModelTrainer:
    trainer_id = "fixture.wrong-model.v1"

    def train(
        self,
        spec: TrainingSpec,
        corpora: Mapping[str, Sequence[str]],
    ):
        payload = {"kind": "wrong-model", "run": spec.run_id}
        return (
            ModelArtifact(
                model_id="different-model",
                model_digest=sha("wrong-model"),
                artifact_digest=stable_digest(payload),
                kind="fixture",
                payload=payload,
                training_run_id=spec.run_id,
            ),
            {"loss": 1.0},
        )


class BadMetricsTrainer:
    trainer_id = "fixture.bad-metrics.v1"

    def train(
        self,
        spec: TrainingSpec,
        corpora: Mapping[str, Sequence[str]],
    ):
        payload = {"kind": "bad-metrics", "run": spec.run_id}
        return (
            ModelArtifact(
                model_id=spec.model_id,
                model_digest=sha("bad-metrics-model"),
                artifact_digest=stable_digest(payload),
                kind="fixture",
                payload=payload,
                training_run_id=spec.run_id,
            ),
            {"loss": float("nan")},
        )


class CollisionTrainer:
    trainer_id = "fixture.collision.v1"

    def train(
        self,
        spec: TrainingSpec,
        corpora: Mapping[str, Sequence[str]],
    ):
        payload = {
            "kind": "collision",
            "run": spec.run_id,
        }
        return (
            ModelArtifact(
                model_id=spec.model_id,
                model_digest=sha("shared-model-digest"),
                artifact_digest=stable_digest(payload),
                kind="fixture",
                payload=payload,
                training_run_id=spec.run_id,
            ),
            {"loss": 1.0},
        )


def strict_registry(
    selected: TrainingDataset,
    *,
    policy: str = "policy-v1",
) -> tuple[ModelDevelopmentRegistry, TrainingIntegrityReceipt]:
    receipt = integrity_receipt(selected, policy=policy)
    registry = ModelDevelopmentRegistry(
        require_integrity_receipts=True,
        allowed_integrity_policy_digests=(sha(policy),),
    )
    registry.register_dataset(selected)
    registry.bind_training_integrity(
        selected.dataset_id,
        receipt,
    )
    return registry, receipt


def test_integrity_signal_score_rejects_nonfinite_values() -> None:
    for value in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(
            TrainingIntegrityError,
            match="finite and in",
        ):
            IntegritySignal(
                source_id="source:a",
                kind="content-anomaly",
                detector_id="detector:x",
                detector_digest=sha("detector"),
                passed=True,
                evidence_ref="evidence:x",
                score=value,
            )


def test_integrity_gate_rejects_normalized_source_id_collision() -> None:
    gate = TrainingIntegrityGate(policy_digest=sha("policy"))
    with pytest.raises(
        TrainingIntegrityError,
        match="collide after normalization",
    ):
        gate.evaluate(
            dataset_id="dataset",
            dataset_digest=sha("dataset"),
            source_digests={
                "source:a": sha("a"),
                " source:a": sha("b"),
            },
            transforms=(transform(),),
            signals=signals("source:a"),
        )


def test_integrity_gate_rejects_duplicate_transform_id_even_if_content_differs() -> None:
    gate = TrainingIntegrityGate(policy_digest=sha("policy"))
    with pytest.raises(
        TrainingIntegrityError,
        match="transform ids must be unique",
    ):
        gate.evaluate(
            dataset_id="dataset",
            dataset_digest=sha("dataset"),
            source_digests={"source:a": sha("a")},
            transforms=(
                transform(),
                transform(code="different-code"),
            ),
            signals=signals("source:a"),
        )


def test_integrity_gate_rejects_duplicate_signal_kind_per_source() -> None:
    gate = TrainingIntegrityGate(policy_digest=sha("policy"))
    rows = signals("source:a")
    duplicate = IntegritySignal(
        source_id="source:a",
        kind="content-anomaly",
        detector_id="detector:duplicate",
        detector_digest=sha("duplicate"),
        passed=True,
        evidence_ref="evidence:duplicate",
        score=0.2,
    )
    with pytest.raises(
        TrainingIntegrityError,
        match="duplicate integrity signal kind",
    ):
        gate.evaluate(
            dataset_id="dataset",
            dataset_digest=sha("dataset"),
            source_digests={"source:a": sha("a")},
            transforms=(transform(),),
            signals=rows + (duplicate,),
        )


def test_integrity_receipt_rejects_admission_flag_incoherence() -> None:
    source = SourceIntegrityDecision(
        source_id="source:a",
        source_digest=sha("a"),
        disposition="admit",
        signal_digests=tuple(
            signal.digest
            for signal in signals("source:a")
        ),
        rationale="required integrity signals passed",
    )
    with pytest.raises(
        TrainingIntegrityError,
        match="admission flag disagrees",
    ):
        TrainingIntegrityReceipt(
            dataset_id="dataset",
            dataset_digest=sha("dataset"),
            transform_identities=(transform().identity,),
            source_decisions=(source,),
            signal_digests=source.signal_digests,
            admitted=False,
            policy_digest=sha("policy"),
        )


def test_integrity_receipt_rejects_signal_inventory_drift() -> None:
    source = SourceIntegrityDecision(
        source_id="source:a",
        source_digest=sha("a"),
        disposition="admit",
        signal_digests=tuple(
            signal.digest
            for signal in signals("source:a")
        ),
        rationale="required integrity signals passed",
    )
    with pytest.raises(
        TrainingIntegrityError,
        match="signal inventory",
    ):
        TrainingIntegrityReceipt(
            dataset_id="dataset",
            dataset_digest=sha("dataset"),
            transform_identities=(transform().identity,),
            source_decisions=(source,),
            signal_digests=source.signal_digests[:-1],
            admitted=True,
            policy_digest=sha("policy"),
        )


def test_integrity_receipt_metadata_is_detached_from_caller_mutation() -> None:
    source = SourceIntegrityDecision(
        source_id="source:a",
        source_digest=sha("a"),
        disposition="admit",
        signal_digests=tuple(
            signal.digest
            for signal in signals("source:a")
        ),
        rationale="required integrity signals passed",
    )
    metadata = {"nested": {"labels": ["a", "b"]}}
    receipt = TrainingIntegrityReceipt(
        dataset_id="dataset",
        dataset_digest=sha("dataset"),
        transform_identities=(transform().identity,),
        source_decisions=(source,),
        signal_digests=source.signal_digests,
        admitted=True,
        policy_digest=sha("policy"),
        metadata=metadata,
    )
    identity = receipt.digest
    metadata["nested"]["labels"].append("c")
    assert receipt.digest == identity
    assert receipt.as_dict()["metadata"] == {
        "nested": {"labels": ["a", "b"]}
    }
    with pytest.raises(TypeError):
        receipt.metadata["new"] = "value"  # type: ignore[index]


def test_integrity_evidence_is_order_independent() -> None:
    gate = TrainingIntegrityGate(policy_digest=sha("policy"))
    source_digests = {
        "source:a": sha("a"),
        "source:b": sha("b"),
    }
    transforms = (
        transform(transform_id="normalize-v1"),
        transform(
            transform_id="dedupe-v1",
            code="dedupe",
            config="dedupe-config",
        ),
    )
    rows = signals("source:a") + signals(
        "source:b",
        suffix=":b",
    )

    first = gate.evaluate_evidence(
        dataset_id="dataset",
        dataset_digest=sha("dataset"),
        source_digests=source_digests,
        transforms=transforms,
        signals=rows,
    )
    second = gate.evaluate_evidence(
        dataset_id="dataset",
        dataset_digest=sha("dataset"),
        source_digests=dict(reversed(tuple(source_digests.items()))),
        transforms=tuple(reversed(transforms)),
        signals=tuple(reversed(rows)),
    )
    assert first.digest == second.digest
    assert first.receipt.digest == second.receipt.digest


def test_integrity_evidence_changes_when_detector_evidence_changes() -> None:
    gate = TrainingIntegrityGate(policy_digest=sha("policy"))
    first = gate.evaluate_evidence(
        dataset_id="dataset",
        dataset_digest=sha("dataset"),
        source_digests={"source:a": sha("a")},
        transforms=(transform(),),
        signals=signals("source:a"),
    )
    second = gate.evaluate_evidence(
        dataset_id="dataset",
        dataset_digest=sha("dataset"),
        source_digests={"source:a": sha("a")},
        transforms=(transform(),),
        signals=signals("source:a", suffix=":new"),
    )
    assert first.signal_inventory_digest != second.signal_inventory_digest
    assert first.digest != second.digest


def test_require_admitted_can_bind_expected_policy() -> None:
    selected = dataset()
    receipt = integrity_receipt(selected)
    TrainingIntegrityGate.require_admitted(
        receipt,
        expected_policy_digest=sha("policy-v1"),
    )
    with pytest.raises(
        TrainingIntegrityError,
        match="policy mismatch",
    ):
        TrainingIntegrityGate.require_admitted(
            receipt,
            expected_policy_digest=sha("other-policy"),
        )


def test_strict_model_registry_requires_integrity_binding() -> None:
    selected = dataset()
    registry = ModelDevelopmentRegistry(
        require_integrity_receipts=True,
        allowed_integrity_policy_digests=(sha("policy-v1"),),
    )
    registry.register_dataset(selected)
    with pytest.raises(
        ModelProgramError,
        match="integrity binding missing",
    ):
        registry.train(
            training_spec(),
            corpora={selected.dataset_id: corpus()},
        )


def test_quarantined_integrity_receipt_cannot_bind_training_dataset() -> None:
    selected = dataset()
    registry = ModelDevelopmentRegistry(
        require_integrity_receipts=True,
    )
    registry.register_dataset(selected)
    quarantined = integrity_receipt(
        selected,
        fail_kind="trigger-canary",
    )
    assert quarantined.admitted is False
    with pytest.raises(
        ModelProgramError,
        match="not admitted",
    ):
        registry.bind_training_integrity(
            selected.dataset_id,
            quarantined,
        )


def test_integrity_binding_requires_exact_dataset_id_and_digest() -> None:
    selected = dataset()
    registry = ModelDevelopmentRegistry()
    registry.register_dataset(selected)

    wrong_id = TrainingIntegrityGate(
        policy_digest=sha("policy-v1")
    ).evaluate(
        dataset_id="other-dataset",
        dataset_digest=selected.content_digest,
        source_digests={"source:a": sha("a")},
        transforms=(transform(),),
        signals=signals("source:a"),
    )
    with pytest.raises(
        ModelProgramError,
        match="dataset id mismatch",
    ):
        registry.bind_training_integrity(
            selected.dataset_id,
            wrong_id,
        )

    wrong_digest = TrainingIntegrityGate(
        policy_digest=sha("policy-v1")
    ).evaluate(
        dataset_id=selected.dataset_id,
        dataset_digest=sha("other-content"),
        source_digests={"source:a": sha("a")},
        transforms=(transform(),),
        signals=signals("source:a"),
    )
    with pytest.raises(
        ModelProgramError,
        match="dataset digest mismatch",
    ):
        registry.bind_training_integrity(
            selected.dataset_id,
            wrong_digest,
        )


def test_integrity_binding_policy_must_be_allowlisted() -> None:
    selected = dataset()
    registry = ModelDevelopmentRegistry(
        allowed_integrity_policy_digests=(sha("allowed"),),
    )
    registry.register_dataset(selected)
    receipt = integrity_receipt(
        selected,
        policy="not-allowed",
    )
    with pytest.raises(
        ModelProgramError,
        match="policy is not allowlisted",
    ):
        registry.bind_training_integrity(
            selected.dataset_id,
            receipt,
        )


def test_integrity_binding_is_idempotent_but_not_rebindable() -> None:
    selected = dataset()
    registry = ModelDevelopmentRegistry()
    registry.register_dataset(selected)
    first = integrity_receipt(selected, suffix=":first")
    binding = registry.bind_training_integrity(
        selected.dataset_id,
        first,
    )
    replay = registry.bind_training_integrity(
        selected.dataset_id,
        first,
    )
    assert replay == binding

    second = integrity_receipt(selected, suffix=":second")
    assert second.digest != first.digest
    with pytest.raises(
        ModelProgramError,
        match="binding conflict",
    ):
        registry.bind_training_integrity(
            selected.dataset_id,
            second,
        )


def test_strict_training_binds_dataset_integrity_into_run_evidence() -> None:
    selected = dataset()
    registry, receipt = strict_registry(selected)
    artifact, training_receipt = registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
    )
    evidence = registry.run_evidence("run-1")
    binding = registry.integrity_binding(selected.dataset_id)

    assert training_receipt.spec_digest == training_spec().digest
    assert training_receipt.dataset_identity_digests == (
        selected.digest,
    )
    assert training_receipt.integrity_binding_digests == (
        binding.digest,
    )
    assert evidence.dataset_identity_digests == (
        selected.digest,
    )
    assert evidence.integrity_binding_digests == (
        binding.digest,
    )
    assert evidence.artifact_identity_digest == artifact.identity_digest
    assert evidence.training_receipt_digest == training_receipt.digest
    assert binding.integrity_receipt_digest == receipt.digest


def test_training_run_replay_is_idempotent_without_reexecuting_trainer() -> None:
    selected = dataset()
    registry, _ = strict_registry(selected)
    trainer = CountingTrainer()
    spec = training_spec()
    first_artifact, first_receipt = registry.train(
        spec,
        corpora={selected.dataset_id: corpus()},
        trainer=trainer,
    )
    second_artifact, second_receipt = registry.train(
        spec,
        corpora={selected.dataset_id: corpus()},
        trainer=trainer,
    )

    assert trainer.calls == 1
    assert second_artifact == first_artifact
    assert second_receipt == first_receipt


def test_run_id_cannot_be_rebound_to_different_spec() -> None:
    selected = dataset()
    registry, _ = strict_registry(selected)
    trainer = CountingTrainer()
    registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
        trainer=trainer,
    )
    changed = training_spec(
        code_revision="revision-2",
    )
    with pytest.raises(
        ModelProgramError,
        match="different spec",
    ):
        registry.train(
            changed,
            corpora={selected.dataset_id: corpus()},
            trainer=trainer,
        )
    assert trainer.calls == 1


def test_run_replay_revalidates_corpus_before_returning_receipt() -> None:
    selected = dataset()
    registry, _ = strict_registry(selected)
    trainer = CountingTrainer()
    spec = training_spec()
    registry.train(
        spec,
        corpora={selected.dataset_id: corpus()},
        trainer=trainer,
    )
    tampered = tuple(corpus()[:-1]) + ("tampered corpus",)
    with pytest.raises(
        ModelProgramError,
        match="content digest drift",
    ):
        registry.train(
            spec,
            corpora={selected.dataset_id: tampered},
            trainer=trainer,
        )
    assert trainer.calls == 1


def test_training_rejects_extra_unbound_corpus_inputs() -> None:
    selected = dataset()
    registry, _ = strict_registry(selected)
    with pytest.raises(
        ModelProgramError,
        match="unbound dataset ids",
    ):
        registry.train(
            training_spec(),
            corpora={
                selected.dataset_id: corpus(),
                "dataset-extra": ("unbound",),
            },
        )


def test_custom_trainer_cannot_return_artifact_for_another_run() -> None:
    selected = dataset()
    registry, _ = strict_registry(selected)
    spec = training_spec(
        trainer_id=WrongRunTrainer.trainer_id,
    )
    with pytest.raises(
        ModelProgramError,
        match="another run",
    ):
        registry.train(
            spec,
            corpora={selected.dataset_id: corpus()},
            trainer=WrongRunTrainer(),
        )


def test_custom_trainer_cannot_return_artifact_for_another_model() -> None:
    selected = dataset()
    registry, _ = strict_registry(selected)
    spec = training_spec(
        trainer_id=WrongModelTrainer.trainer_id,
    )
    with pytest.raises(
        ModelProgramError,
        match="another model",
    ):
        registry.train(
            spec,
            corpora={selected.dataset_id: corpus()},
            trainer=WrongModelTrainer(),
        )


def test_training_metrics_must_be_finite() -> None:
    selected = dataset()
    registry, _ = strict_registry(selected)
    spec = training_spec(
        trainer_id=BadMetricsTrainer.trainer_id,
    )
    with pytest.raises(
        ModelProgramError,
        match="must be finite",
    ):
        registry.train(
            spec,
            corpora={selected.dataset_id: corpus()},
            trainer=BadMetricsTrainer(),
        )


def test_model_digest_cannot_rebind_to_different_artifact() -> None:
    selected = dataset()
    registry, _ = strict_registry(selected)
    trainer = CollisionTrainer()

    first = training_spec(
        run_id="run-a",
        model_id="model-a",
        trainer_id=CollisionTrainer.trainer_id,
    )
    registry.train(
        first,
        corpora={selected.dataset_id: corpus()},
        trainer=trainer,
    )

    second = training_spec(
        run_id="run-b",
        model_id="model-a",
        trainer_id=CollisionTrainer.trainer_id,
    )
    with pytest.raises(
        ModelProgramError,
        match="already bound to another artifact",
    ):
        registry.train(
            second,
            corpora={selected.dataset_id: corpus()},
            trainer=trainer,
        )


def test_training_dataset_metadata_is_immutable_after_construction() -> None:
    metadata = {"nested": {"labels": ["a"]}}
    selected = dataset(metadata=metadata)
    identity = selected.digest
    metadata["nested"]["labels"].append("b")

    assert selected.digest == identity
    assert selected.as_dict()["metadata"] == {
        "nested": {"labels": ["a"]}
    }
    with pytest.raises(TypeError):
        selected.metadata["x"] = 1  # type: ignore[index]


def test_training_spec_hyperparameters_are_immutable_after_construction() -> None:
    hyperparameters = {
        "order": 2,
        "nested": {"schedule": [1, 2]},
    }
    spec = training_spec(
        hyperparameters=hyperparameters,
    )
    identity = spec.digest
    hyperparameters["nested"]["schedule"].append(3)

    assert spec.digest == identity
    assert spec.as_dict()["hyperparameters"] == {
        "nested": {"schedule": [1, 2]},
        "order": 2,
    }
    with pytest.raises(TypeError):
        spec.hyperparameters["order"] = 3  # type: ignore[index]


def test_training_receipt_metrics_are_immutable_and_finite() -> None:
    metrics = {"loss": 1.0}
    receipt = TrainingReceipt(
        run_id="run",
        spec_digest=sha("spec"),
        dataset_digests=(sha("dataset"),),
        trainer_id="trainer",
        code_revision="revision",
        model_id="model",
        model_digest=sha("model"),
        artifact_digest=sha("artifact"),
        metrics=metrics,
    )
    identity = receipt.digest
    metrics["loss"] = 99.0
    assert receipt.digest == identity
    assert receipt.metrics["loss"] == 1.0
    with pytest.raises(TypeError):
        receipt.metrics["loss"] = 2.0  # type: ignore[index]

    for value in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(
            ModelProgramError,
            match="must be finite",
        ):
            TrainingReceipt(
                run_id="run",
                spec_digest=sha("spec"),
                dataset_digests=(sha("dataset"),),
                trainer_id="trainer",
                code_revision="revision",
                model_id="model",
                model_digest=sha("model"),
                artifact_digest=sha("artifact"),
                metrics={"loss": value},
            )


def test_model_artifact_payload_is_immutable_and_reloadable() -> None:
    selected = dataset()
    registry, _ = strict_registry(selected)
    artifact, _ = registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
    )
    identity = artifact.identity_digest
    with pytest.raises(TypeError):
        artifact.payload["new"] = "value"  # type: ignore[index]
    assert artifact.identity_digest == identity
    reloaded = artifact.load_reference_model()
    assert reloaded.model_digest == artifact.model_digest


def test_promotion_requires_verifier_independent_from_trainer() -> None:
    selected = dataset()
    registry, _ = strict_registry(selected)
    registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
    )
    with pytest.raises(
        ModelProgramError,
        match="cannot independently verify",
    ):
        registry.promote(
            run_id="run-1",
            verifier_id=ReferenceNGramTrainer.trainer_id,
            evaluation_refs=("eval:a", "eval:b"),
        )


def test_promotion_is_order_canonical_and_idempotent() -> None:
    selected = dataset()
    registry, _ = strict_registry(selected)
    registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
    )
    first = registry.promote(
        run_id="run-1",
        verifier_id="independent-verifier",
        evaluation_refs=("eval:b", "eval:a"),
    )
    second = registry.promote(
        run_id="run-1",
        verifier_id="independent-verifier",
        evaluation_refs=("eval:a", "eval:b"),
    )
    assert first == second
    assert first.evaluation_refs == ("eval:a", "eval:b")


def test_promotion_identity_cannot_be_rebound() -> None:
    selected = dataset()
    registry, _ = strict_registry(selected)
    registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
    )
    registry.promote(
        run_id="run-1",
        verifier_id="verifier-a",
        evaluation_refs=("eval:a", "eval:b"),
    )
    with pytest.raises(
        ModelProgramError,
        match="already bound to another decision",
    ):
        registry.promote(
            run_id="run-1",
            verifier_id="verifier-b",
            evaluation_refs=("eval:a", "eval:b"),
        )


def test_registry_getters_fail_closed_for_unknown_identity() -> None:
    registry = ModelDevelopmentRegistry()
    with pytest.raises(
        ModelProgramError,
        match="artifact is unavailable",
    ):
        registry.artifact(sha("unknown"))
    with pytest.raises(
        ModelProgramError,
        match="training receipt is unavailable",
    ):
        registry.training_receipt("unknown-run")
    with pytest.raises(
        ModelProgramError,
        match="training run evidence is unavailable",
    ):
        registry.run_evidence("unknown-run")
    with pytest.raises(
        ModelProgramError,
        match="integrity binding is unavailable",
    ):
        registry.integrity_binding("unknown-dataset")


def governed_candidate(model_digest: str) -> ImprovementCandidate:
    return ImprovementCandidate(
        candidate_id="CANDIDATE.MODEL1",
        champion_digest=sha("champion-model"),
        challenger_digest=model_digest,
        experiment_scope="isolated:model-program",
        metric_ids=("METRIC.QUALITY",),
        builder_id="ACTOR.BUILDER",
    )


def governed_decision(candidate_value: ImprovementCandidate):
    evaluation = EvaluationBundle(
        candidate_digest=candidate_value.digest,
        metric_values=(("METRIC.QUALITY", 0.95),),
        safety_passed=True,
        cost_passed=True,
        robustness_passed=True,
        evidence_digest=sha("governance-evaluation"),
    )
    canary = CanaryEvidence(
        candidate_digest=candidate_value.digest,
        canary_digest=sha("canary-run"),
        safety_passed=True,
        quality_passed=True,
        rollback_ready=True,
        verifier_id="ACTOR.CANARY",
    )
    decision = promote_with_canary(
        candidate_value,
        evaluation,
        "ACTOR.VERIFIER",
        canary,
    )
    ledger = PromotionLedger()
    ledger.record_decision(
        candidate_value,
        decision,
        evaluation=evaluation,
        canary=canary,
    )
    return decision, ledger


def governed_registry(
    selected: TrainingDataset,
) -> ModelDevelopmentRegistry:
    receipt = integrity_receipt(selected)
    registry = ModelDevelopmentRegistry(
        require_integrity_receipts=True,
        allowed_integrity_policy_digests=(sha("policy-v1"),),
        require_governed_promotion_decisions=True,
    )
    registry.register_dataset(selected)
    registry.bind_training_integrity(
        selected.dataset_id,
        receipt,
    )
    return registry


def test_governed_model_promotion_requires_typed_promotion_decision() -> None:
    selected = dataset()
    registry = governed_registry(selected)
    registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
    )
    with pytest.raises(
        ModelProgramError,
        match="governed promotion decision is required",
    ):
        registry.promote(
            run_id="run-1",
            verifier_id="ACTOR.VERIFIER",
            evaluation_refs=("eval:a", "eval:b"),
        )


def test_governed_model_promotion_binds_exact_trained_challenger() -> None:
    selected = dataset()
    registry = governed_registry(selected)
    artifact, _ = registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
    )
    candidate_value = governed_candidate(artifact.model_digest)
    decision, ledger = governed_decision(candidate_value)
    promotion = registry.promote(
        run_id="run-1",
        verifier_id="ACTOR.VERIFIER",
        evaluation_refs=("eval:b", "eval:a"),
        governance_candidate=candidate_value,
        governance_decision=decision,
        governance_ledger=ledger,
    )

    assert promotion.model_digest == artifact.model_digest
    assert promotion.governance_decision_digest == decision.digest
    assert promotion.verifier_id == decision.verifier_id
    assert promotion.evaluation_refs == ("eval:a", "eval:b")


def test_governed_model_promotion_rejects_wrong_challenger_model() -> None:
    selected = dataset()
    registry = governed_registry(selected)
    registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
    )
    candidate_value = governed_candidate(sha("different-model"))
    decision, ledger = governed_decision(candidate_value)

    with pytest.raises(
        ModelProgramError,
        match="challenger does not match trained model",
    ):
        registry.promote(
            run_id="run-1",
            verifier_id="ACTOR.VERIFIER",
            evaluation_refs=("eval:a", "eval:b"),
            governance_candidate=candidate_value,
            governance_decision=decision,
            governance_ledger=ledger,
        )


def test_governed_model_promotion_rejects_rejected_decision() -> None:
    selected = dataset()
    registry = governed_registry(selected)
    artifact, _ = registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
    )
    candidate_value = governed_candidate(artifact.model_digest)
    rejected_evaluation = EvaluationBundle(
        candidate_digest=candidate_value.digest,
        metric_values=(("METRIC.QUALITY", 0.95),),
        safety_passed=False,
        cost_passed=True,
        robustness_passed=True,
        evidence_digest=sha("rejected-evaluation"),
    )
    rejected = decide(
        candidate_value,
        rejected_evaluation,
        "ACTOR.VERIFIER",
        canary_digest=None,
    )
    assert rejected.status is PromotionStatus.REJECT
    ledger = PromotionLedger()
    ledger.record_decision(
        candidate_value,
        rejected,
        evaluation=rejected_evaluation,
        canary=None,
    )

    with pytest.raises(
        ModelProgramError,
        match="does not authorize promotion",
    ):
        registry.promote(
            run_id="run-1",
            verifier_id="ACTOR.VERIFIER",
            evaluation_refs=("eval:a", "eval:b"),
            governance_candidate=candidate_value,
            governance_decision=rejected,
            governance_ledger=ledger,
        )


def test_governed_model_promotion_verifier_must_match_decision() -> None:
    selected = dataset()
    registry = governed_registry(selected)
    artifact, _ = registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
    )
    candidate_value = governed_candidate(artifact.model_digest)
    decision, ledger = governed_decision(candidate_value)
    with pytest.raises(
        ModelProgramError,
        match="verifier must match governance verifier",
    ):
        registry.promote(
            run_id="run-1",
            verifier_id="ACTOR.OTHER",
            evaluation_refs=("eval:a", "eval:b"),
            governance_candidate=candidate_value,
            governance_decision=decision,
            governance_ledger=ledger,
        )


def test_governance_candidate_and_decision_must_be_supplied_together() -> None:
    selected = dataset()
    registry = governed_registry(selected)
    artifact, _ = registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
    )
    candidate_value = governed_candidate(artifact.model_digest)
    decision, ledger = governed_decision(candidate_value)

    with pytest.raises(
        TypeError,
        match="governance_decision",
    ):
        registry.promote(
            run_id="run-1",
            verifier_id="ACTOR.VERIFIER",
            evaluation_refs=("eval:a", "eval:b"),
            governance_candidate=candidate_value,
            governance_decision=None,
            governance_ledger=ledger,
        )

    with pytest.raises(
        TypeError,
        match="governance_candidate",
    ):
        registry.promote(
            run_id="run-1",
            verifier_id="ACTOR.VERIFIER",
            evaluation_refs=("eval:a", "eval:b"),
            governance_candidate=None,
            governance_decision=decision,
            governance_ledger=ledger,
        )

    with pytest.raises(
        TypeError,
        match="governance_ledger",
    ):
        registry.promote(
            run_id="run-1",
            verifier_id="ACTOR.VERIFIER",
            evaluation_refs=("eval:a", "eval:b"),
            governance_candidate=candidate_value,
            governance_decision=decision,
            governance_ledger=None,
        )


def test_governed_promotion_replay_is_idempotent_and_decision_bound() -> None:
    selected = dataset()
    registry = governed_registry(selected)
    artifact, _ = registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
    )
    candidate_value = governed_candidate(artifact.model_digest)
    decision, ledger = governed_decision(candidate_value)

    first = registry.promote(
        run_id="run-1",
        verifier_id="ACTOR.VERIFIER",
        evaluation_refs=("eval:a", "eval:b"),
        governance_candidate=candidate_value,
        governance_decision=decision,
        governance_ledger=ledger,
    )
    second = registry.promote(
        run_id="run-1",
        verifier_id="ACTOR.VERIFIER",
        evaluation_refs=("eval:b", "eval:a"),
        governance_candidate=candidate_value,
        governance_decision=decision,
        governance_ledger=ledger,
    )
    assert first == second
    assert first.governance_decision_digest == decision.digest


def test_model_registry_rejects_decision_not_verified_by_supplied_ledger() -> None:
    selected = dataset()
    registry = governed_registry(selected)
    artifact, _ = registry.train(
        training_spec(),
        corpora={selected.dataset_id: corpus()},
    )
    candidate_value = governed_candidate(artifact.model_digest)
    decision, _verified_ledger = governed_decision(candidate_value)
    empty_ledger = PromotionLedger()

    with pytest.raises(
        ModelProgramError,
        match="not verified by promotion ledger",
    ):
        registry.promote(
            run_id="run-1",
            verifier_id="ACTOR.VERIFIER",
            evaluation_refs=("eval:a", "eval:b"),
            governance_candidate=candidate_value,
            governance_decision=decision,
            governance_ledger=empty_ledger,
        )


def test_strict_registry_boolean_and_policy_configuration_are_validated() -> None:
    with pytest.raises(TypeError):
        ModelDevelopmentRegistry(
            require_integrity_receipts=1,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        ModelDevelopmentRegistry(
            require_governed_promotion_decisions=1,  # type: ignore[arg-type]
        )
    with pytest.raises(
        ModelProgramError,
        match="must be unique",
    ):
        ModelDevelopmentRegistry(
            allowed_integrity_policy_digests=(
                sha("policy"),
                sha("policy"),
            ),
        )


def test_corpus_digest_rejects_empty_and_is_order_sensitive() -> None:
    with pytest.raises(
        ModelProgramError,
        match="non-empty",
    ):
        corpus_digest(())
    assert corpus_digest(("a", "b")) != corpus_digest(("b", "a"))
