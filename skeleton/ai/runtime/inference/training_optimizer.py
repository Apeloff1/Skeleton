"""Bounded local training-mix optimization.

This module closes the development loop without acquiring promotion authority:
1. discover training methods compatible with the supplied examples;
2. train one bounded probe artifact per selected method;
3. evaluate each exact probe against one exact local baseline on a
   development-only suite;
4. feed verified gain-per-compute observations to the adaptive allocator;
5. train one final candidate using the allocated method repeats.

Probe artifacts may be deleted after their content-addressed evaluation reports
are produced. The final candidate is still unpromoted and must pass the normal
Mirror/firewall/lifecycle path before activation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from .artifact import LocalModelArtifactError, load_local_model_artifact
from .developmental_eval import (
    DevelopmentalComparisonReport,
    DevelopmentalEvalSuite,
    DevelopmentalEvaluationError,
    evaluate_training_receipt_developmentally,
)
from .training_allocation import (
    AdaptiveMethodAllocation,
    TrainingAllocationPolicy,
    TrainingAllocationError,
    allocate_training_methods,
)
from .training_methods import (
    TrainingEfficiencyPolicy,
    TrainingExample,
    TrainingMethod,
    compatible_training_methods,
)


_MAX_PROBES = 20


class TrainingOptimizationError(RuntimeError):
    """A bounded developmental training optimization round failed."""


def _json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TrainingOptimizationError(
            "training optimization state is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(value: object, field: str, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrainingOptimizationError(
            f"{field} must be non-empty text"
        )
    result = value.strip()
    if len(result) > maximum:
        raise TrainingOptimizationError(
            f"{field} exceeds maximum length"
        )
    return result


@dataclass(frozen=True, slots=True)
class TrainingOptimizationPolicy:
    """Resource envelope for one local method-probing round."""

    max_probes: int = 20
    probe_epochs: int = 1
    probe_gradient_accumulation_steps: int = 2
    final_gradient_accumulation_steps: int = 4
    cleanup_probe_artifacts: bool = True

    def __post_init__(self) -> None:
        for field, value, minimum, maximum in (
            ("max_probes", self.max_probes, 1, _MAX_PROBES),
            ("probe_epochs", self.probe_epochs, 1, 64),
            (
                "probe_gradient_accumulation_steps",
                self.probe_gradient_accumulation_steps,
                1,
                64,
            ),
            (
                "final_gradient_accumulation_steps",
                self.final_gradient_accumulation_steps,
                1,
                64,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise TrainingOptimizationError(
                    f"{field} must be in [{minimum}, {maximum}]"
                )
        if not isinstance(self.cleanup_probe_artifacts, bool):
            raise TrainingOptimizationError(
                "cleanup_probe_artifacts must be boolean"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "max_probes": self.max_probes,
                "probe_epochs": self.probe_epochs,
                "probe_gradient_accumulation_steps": (
                    self.probe_gradient_accumulation_steps
                ),
                "final_gradient_accumulation_steps": (
                    self.final_gradient_accumulation_steps
                ),
                "cleanup_probe_artifacts": self.cleanup_probe_artifacts,
            }
        )


@dataclass(frozen=True, slots=True)
class TrainingOptimizationResult:
    """Evidence and final candidate from one bounded optimization round."""

    baseline_model_digest: str
    baseline_artifact_sha256: str
    source_example_digests: tuple[str, ...]
    probed_methods: tuple[TrainingMethod, ...]
    reports: tuple[DevelopmentalComparisonReport, ...]
    allocation: AdaptiveMethodAllocation
    final_receipt: Mapping[str, object]
    policy_digest: str
    optimization_digest: str

    def __post_init__(self) -> None:
        if not self.probed_methods or not self.reports:
            raise TrainingOptimizationError(
                "optimization result requires probes"
            )
        if len(self.probed_methods) != len(self.reports):
            raise TrainingOptimizationError(
                "probe methods and reports must align"
            )
        if any(
            report.method is not method
            for method, report in zip(
                self.probed_methods,
                self.reports,
                strict=True,
            )
        ):
            raise TrainingOptimizationError(
                "probe report method order drift"
            )
        if any(
            report.attribution_verified is not True
            for report in self.reports
        ):
            raise TrainingOptimizationError(
                "all probe reports require verified attribution"
            )
        object.__setattr__(self, "final_receipt", dict(self.final_receipt))

    def as_dict(self) -> dict[str, object]:
        training_plan = self.final_receipt.get("training_plan")
        return {
            "schema_version": "skeleton.training_optimization.v1",
            "baseline_model_digest": self.baseline_model_digest,
            "baseline_artifact_sha256": self.baseline_artifact_sha256,
            "source_example_digests": list(self.source_example_digests),
            "probed_methods": [item.value for item in self.probed_methods],
            "probe_report_digests": [
                item.digest for item in self.reports
            ],
            "allocation_digest": self.allocation.allocation_digest,
            "final_model_digest": self.final_receipt.get("model_digest"),
            "final_artifact_sha256": self.final_receipt.get(
                "artifact_sha256"
            ),
            "final_training_plan_digest": (
                training_plan.get("plan_digest")
                if isinstance(training_plan, Mapping)
                else None
            ),
            "policy_digest": self.policy_digest,
            "optimization_digest": self.optimization_digest,
            "production_authority": False,
        }


def _select_probe_methods(
    examples: tuple[TrainingExample, ...],
    *,
    requested_methods: Sequence[TrainingMethod] | None,
    allocation_policy: TrainingAllocationPolicy,
    optimization_policy: TrainingOptimizationPolicy,
) -> tuple[TrainingMethod, ...]:
    compatible = compatible_training_methods(examples)
    compatible_set = set(compatible)
    if requested_methods is None:
        requested = compatible
    else:
        requested_list: list[TrainingMethod] = []
        for raw in requested_methods:
            try:
                method = TrainingMethod(raw)
            except ValueError as exc:
                raise TrainingOptimizationError(
                    "requested probe method is unsupported"
                ) from exc
            if method not in compatible_set:
                raise TrainingOptimizationError(
                    "requested probe method lacks required training signals: "
                    + method.value
                )
            if method not in requested_list:
                requested_list.append(method)
        requested = tuple(requested_list)

    methods: list[TrainingMethod] = []
    for method in allocation_policy.mandatory_methods:
        if method not in compatible_set:
            raise TrainingOptimizationError(
                "mandatory allocation method lacks required training signals"
            )
        if method not in methods:
            methods.append(method)
    for method in requested:
        if method not in methods:
            methods.append(method)

    if len(methods) > optimization_policy.max_probes:
        mandatory = tuple(allocation_policy.mandatory_methods)
        remaining_budget = optimization_policy.max_probes - len(mandatory)
        if remaining_budget < 0:
            raise TrainingOptimizationError(
                "max_probes cannot fit mandatory allocation methods"
            )
        optional = tuple(
            item for item in methods if item not in set(mandatory)
        )
        methods = [*mandatory, *optional[:remaining_budget]]
    return tuple(methods)


def optimize_training_mix(
    *,
    examples: Sequence[TrainingExample],
    baseline_path: str | Path,
    suite: DevelopmentalEvalSuite,
    work_dir: str | Path,
    final_output_path: str | Path,
    model_id: str,
    requested_methods: Sequence[TrainingMethod] | None = None,
    allocation_policy: TrainingAllocationPolicy | None = None,
    optimization_policy: TrainingOptimizationPolicy | None = None,
    efficiency_policy: TrainingEfficiencyPolicy | None = None,
    hidden_size: int = 32,
    final_epochs: int = 4,
    learning_rate: float = 0.05,
    max_vocab: int = 4_096,
    max_document_tokens: int = 1_024,
    seed: int = 0,
    temperature: float = 0.8,
) -> TrainingOptimizationResult:
    """Probe, evaluate, allocate, and train one final unpromoted candidate."""

    # Keep the inference package importable without the optional NumPy
    # training extra. Numeric training is materialized only when optimization
    # is explicitly executed.
    try:
        from .train import (
            LocalModelBuildError,
            build_multi_method_recurrent_artifact,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise TrainingOptimizationError(
            "local numeric training dependency is not materialized"
        ) from exc

    rows = tuple(examples)
    if not rows or any(not isinstance(item, TrainingExample) for item in rows):
        raise TrainingOptimizationError(
            "examples must contain at least one TrainingExample"
        )
    if not isinstance(suite, DevelopmentalEvalSuite):
        raise TypeError("suite must be DevelopmentalEvalSuite")
    actual_allocation = allocation_policy or TrainingAllocationPolicy()
    actual_optimization = (
        optimization_policy or TrainingOptimizationPolicy()
    )
    selected = _select_probe_methods(
        rows,
        requested_methods=requested_methods,
        allocation_policy=actual_allocation,
        optimization_policy=actual_optimization,
    )
    if not selected:
        raise TrainingOptimizationError(
            "optimization produced no compatible probe methods"
        )

    root = Path(work_dir).expanduser()
    if not root.exists() or not root.is_dir():
        raise TrainingOptimizationError(
            "work_dir must be an existing directory"
        )
    final_path = Path(final_output_path).expanduser()
    try:
        baseline_resolved = Path(baseline_path).expanduser().resolve(
            strict=True
        )
        final_resolved = final_path.resolve(strict=False)
    except OSError as exc:
        raise TrainingOptimizationError(
            "baseline/final path cannot be resolved"
        ) from exc
    if final_resolved == baseline_resolved:
        raise TrainingOptimizationError(
            "optimized candidate cannot overwrite baseline artifact"
        )
    if final_resolved.exists():
        raise TrainingOptimizationError(
            "final_output_path already exists"
        )

    try:
        baseline = load_local_model_artifact(baseline_resolved)
    except LocalModelArtifactError as exc:
        raise TrainingOptimizationError(
            "baseline artifact cannot be authenticated"
        ) from exc

    example_digests = tuple(sorted(item.digest for item in rows))
    source_digest = _digest(
        {
            "example_digests": list(example_digests),
            "suite_digest": suite.digest,
            "baseline_model_digest": baseline.receipt.model_digest,
            "methods": [item.value for item in selected],
            "optimization_policy_digest": actual_optimization.digest,
        }
    )

    reports: list[DevelopmentalComparisonReport] = []
    probe_paths: list[Path] = []
    try:
        for index, method in enumerate(selected):
            probe_path = root / (
                f".probe-{index:02d}-{method.value}-"
                f"{source_digest[:12]}.json"
            )
            if probe_path.exists():
                raise TrainingOptimizationError(
                    "deterministic probe path already exists"
                )
            probe_paths.append(probe_path)
            try:
                receipt = build_multi_method_recurrent_artifact(
                    examples=rows,
                    output_path=probe_path,
                    model_id=(
                        _text(model_id, "model_id", maximum=256)
                        + "-probe-"
                        + method.value
                    ),
                    methods=(method,),
                    efficiency_policy=efficiency_policy,
                    hidden_size=hidden_size,
                    epochs=actual_optimization.probe_epochs,
                    learning_rate=learning_rate,
                    max_vocab=max_vocab,
                    max_document_tokens=max_document_tokens,
                    seed=seed + index,
                    temperature=temperature,
                    early_stopping_patience=0,
                    gradient_accumulation_steps=(
                        actual_optimization
                        .probe_gradient_accumulation_steps
                    ),
                )
                report = evaluate_training_receipt_developmentally(
                    baseline_path=baseline_resolved,
                    candidate_receipt=receipt,
                    suite=suite,
                    method=method,
                )
            except (
                LocalModelBuildError,
                DevelopmentalEvaluationError,
            ) as exc:
                raise TrainingOptimizationError(
                    "method probe failed: " + method.value
                ) from exc
            reports.append(report)

        observations = tuple(
            report.allocation_observation()
            for report in reports
        )
        try:
            allocation = allocate_training_methods(
                observations,
                available_methods=selected,
                policy=actual_allocation,
            )
        except TrainingAllocationError as exc:
            raise TrainingOptimizationError(
                "adaptive method allocation failed"
            ) from exc

        try:
            final_receipt = build_multi_method_recurrent_artifact(
                examples=rows,
                output_path=final_resolved,
                model_id=_text(model_id, "model_id", maximum=256),
                methods=allocation.method_weights,
                efficiency_policy=efficiency_policy,
                hidden_size=hidden_size,
                epochs=final_epochs,
                learning_rate=learning_rate,
                max_vocab=max_vocab,
                max_document_tokens=max_document_tokens,
                seed=seed,
                temperature=temperature,
                gradient_accumulation_steps=(
                    actual_optimization
                    .final_gradient_accumulation_steps
                ),
            )
        except LocalModelBuildError as exc:
            raise TrainingOptimizationError(
                "optimized final candidate build failed"
            ) from exc
    finally:
        if actual_optimization.cleanup_probe_artifacts:
            for path in probe_paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    training_plan = final_receipt.get("training_plan")
    if not isinstance(training_plan, Mapping):
        raise TrainingOptimizationError(
            "optimized final receipt lacks training plan"
        )
    payload = {
        "schema_version": "skeleton.training_optimization.v1",
        "baseline_model_digest": baseline.receipt.model_digest,
        "baseline_artifact_sha256": baseline.receipt.artifact_sha256,
        "source_example_digests": list(example_digests),
        "probed_methods": [item.value for item in selected],
        "probe_report_digests": [item.digest for item in reports],
        "allocation_digest": allocation.allocation_digest,
        "final_model_digest": final_receipt.get("model_digest"),
        "final_artifact_sha256": final_receipt.get("artifact_sha256"),
        "final_training_plan_digest": training_plan.get("plan_digest"),
        "policy_digest": actual_optimization.digest,
        "production_authority": False,
    }
    return TrainingOptimizationResult(
        baseline_model_digest=baseline.receipt.model_digest,
        baseline_artifact_sha256=baseline.receipt.artifact_sha256,
        source_example_digests=example_digests,
        probed_methods=selected,
        reports=tuple(reports),
        allocation=allocation,
        final_receipt=final_receipt,
        policy_digest=actual_optimization.digest,
        optimization_digest=_digest(payload),
    )


__all__ = [
    "TrainingOptimizationError",
    "TrainingOptimizationPolicy",
    "TrainingOptimizationResult",
    "optimize_training_mix",
]
