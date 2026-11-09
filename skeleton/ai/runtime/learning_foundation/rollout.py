"""Measured shadow/canary evidence inside the existing lifecycle candidate owner.

These assignments select bounded local test outputs. They never configure a
production router, activate a hosted provider, or authorize production promotion.
"""

from __future__ import annotations

import hashlib
import marshal
import math
import time
import types
import weakref
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field

from skeleton.ai.runtime.inference.local import (
    LocalInferenceEngine,
    LocalInferenceRequest,
)
from skeleton.ai.runtime.training.evaluation import (
    EvaluationSuite,
    evaluation_case_passes,
)
from skeleton.ai.runtime.training.evaluation_store import _measurement, _source, _suite
from skeleton.ai.runtime.training.verifier import (
    EvaluationModelSource,
    LocalVerifier,
    VerifierGatePolicy,
    _fingerprint,
    _generate,
    canonical,
    decode,
    derive_metrics,
    digest,
    integer,
    parse_verifier_output,
    qualification_reasons,
    rate,
    sha,
    source_authority,
    text,
    validate_suite,
)
from skeleton.learning.model_program import TrainingReceipt

from .lifecycle import (
    MigrationParityCase,
    ModelBillOfMaterials,
    ModelLifecycleError,
    ModelLifecycleRegistry,
    ModelLifecycleState,
)

MAX_ROLLOUTS = 32
MAX_CASES = 64
MAX_CASE_BYTES = 262144
MAX_COST = 1_000_000_000_000
_PHASES = ("shadow", "canary")


class MeasuredRolloutError(ModelLifecycleError):
    """A bounded rollout cannot prove valid current candidate authority."""


class _Writer:
    pass


_WRITERS = weakref.WeakSet()


def _issued_writer(value):
    return type(value) is _Writer and value in _WRITERS


def _keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise MeasuredRolloutError(name + " has unknown or missing fields")


def _implementation_digest():
    implementations = {
        "bounds": {
            "rollouts": MAX_ROLLOUTS,
            "cases": MAX_CASES,
            "case_bytes": MAX_CASE_BYTES,
            "cost": MAX_COST,
            "phases": _PHASES,
        }
    }
    for name, value in globals().items():
        if isinstance(value, types.FunctionType):
            implementations[name] = {
                "module": value.__module__,
                "name": value.__qualname__,
                "code": hashlib.sha256(marshal.dumps(value.__code__, 0)).hexdigest(),
            }
        elif isinstance(value, type) and (
            value.__module__ == __name__
            or value in (LocalVerifier, EvaluationModelSource, LocalInferenceEngine, LocalInferenceRequest)
        ):
            for member_name, member in vars(value).items():
                if isinstance(member, (classmethod, staticmethod)):
                    member = member.__func__
                if isinstance(member, types.FunctionType):
                    implementations[name + "." + member_name] = hashlib.sha256(
                        marshal.dumps(member.__code__, 0)
                    ).hexdigest()
    return digest(implementations)


@dataclass(frozen=True, slots=True)
class LocalUsageTariff:
    """Declared accounting proxy; cost is derived from actual measured tokens."""

    input_unit_cost: int = 1
    output_unit_cost: int = 1

    def __post_init__(self):
        integer(self.input_unit_cost, "input unit cost", maximum=1_000_000)
        integer(self.output_unit_cost, "output unit cost", maximum=1_000_000)


@dataclass(frozen=True, slots=True)
class RolloutGatePolicy:
    verifier_policy: VerifierGatePolicy = field(default_factory=VerifierGatePolicy)
    min_output_parity: float = 0.0
    max_additional_output_tokens: int = 0
    max_additional_cost_units: int = 0
    max_total_cost_units: int = MAX_COST
    max_total_tokens: int = 10_000_000
    max_inference_elapsed_ns: int = 60_000_000_000
    required_rights_refs: tuple[str, ...] = ()
    candidate_tariff: LocalUsageTariff = field(default_factory=LocalUsageTariff)
    baseline_tariff: LocalUsageTariff = field(default_factory=LocalUsageTariff)
    verifier_tariff: LocalUsageTariff = field(default_factory=LocalUsageTariff)

    def __post_init__(self):
        if not isinstance(self.verifier_policy, VerifierGatePolicy):
            raise TypeError("existing verifier gate policy is required")
        object.__setattr__(self, "min_output_parity", rate(self.min_output_parity, "output parity"))
        for name in (
            "max_additional_output_tokens",
            "max_additional_cost_units",
            "max_total_cost_units",
            "max_total_tokens",
            "max_inference_elapsed_ns",
        ):
            integer(getattr(self, name), name, maximum=MAX_COST)
        if (
            not isinstance(self.required_rights_refs, tuple)
            or len(self.required_rights_refs) > 128
            or len(set(self.required_rights_refs)) != len(self.required_rights_refs)
        ):
            raise MeasuredRolloutError("required rights must be a bounded unique tuple")
        for value in self.required_rights_refs:
            text(value, "required rights")
        for name in ("candidate_tariff", "baseline_tariff", "verifier_tariff"):
            if not isinstance(getattr(self, name), LocalUsageTariff):
                raise TypeError("local tariff must be an explicit LocalUsageTariff")


def _policy(payload):
    _keys(payload, asdict(RolloutGatePolicy()), "rollout policy")
    arguments = dict(payload)
    arguments["verifier_policy"] = VerifierGatePolicy(**arguments["verifier_policy"])
    arguments["required_rights_refs"] = tuple(arguments["required_rights_refs"])
    for name in ("candidate_tariff", "baseline_tariff", "verifier_tariff"):
        arguments[name] = LocalUsageTariff(**arguments[name])
    policy = RolloutGatePolicy(**arguments)
    if decode(canonical(asdict(policy))) != payload:
        raise MeasuredRolloutError("rollout policy is not normalized")
    return policy


@dataclass(frozen=True, slots=True)
class RolloutPlan:
    run_id: str
    suite: EvaluationSuite
    canary_basis_points: int = 1000
    assignment_salt: str = "bounded-local-canary-v1"
    seed: int = 0
    policy: RolloutGatePolicy = field(default_factory=RolloutGatePolicy)

    def __post_init__(self):
        text(self.run_id, "run_id", 256)
        validate_suite(self.suite)
        if len(self.suite.cases) > MAX_CASES:
            raise MeasuredRolloutError("rollout suite exceeds bounded case count")
        integer(self.canary_basis_points, "canary basis points", 1, 9999)
        text(self.assignment_salt, "assignment salt")
        integer(self.seed, "rollout seed", maximum=(1 << 63) - 8192)
        if not isinstance(self.policy, RolloutGatePolicy):
            raise TypeError("RolloutGatePolicy is required")

    def as_dict(self):
        return {
            "run_id": self.run_id,
            "suite": self.suite.as_dict(),
            "canary_basis_points": self.canary_basis_points,
            "assignment_salt": self.assignment_salt,
            "seed": self.seed,
            "policy": asdict(self.policy),
        }

    @property
    def digest(self):
        return digest(self.as_dict())


def _plan(payload):
    _keys(
        payload,
        {"run_id", "suite", "canary_basis_points", "assignment_salt", "seed", "policy"},
        "rollout plan",
    )
    result = RolloutPlan(
        **{**payload, "suite": _suite(payload["suite"]), "policy": _policy(payload["policy"])}
    )
    if decode(canonical(result.as_dict())) != payload:
        raise MeasuredRolloutError("rollout plan is not normalized")
    return result


def _assignment(plan, phase, index):
    case = plan.suite.cases[index]
    identity = {
        "run_id": plan.run_id,
        "phase": phase,
        "request_id": case.case_id,
        "suite_digest": plan.suite.digest,
        "salt": plan.assignment_salt,
    }
    assignment_digest = digest(identity)
    bucket = int(assignment_digest[:16], 16) % 10000
    selected = "candidate" if phase == "canary" and bucket < plan.canary_basis_points else "baseline"
    return {
        "request_id": case.case_id,
        "phase": phase,
        "index": index,
        "bucket": bucket,
        "selected_role": selected,
        "assignment_digest": assignment_digest,
    }


def _validate_observation(observation, index, binding, phase, plan):
    _keys(observation, {"assignment", "measurement"}, "rollout observation")
    if canonical(observation["assignment"]) != canonical(_assignment(plan, phase, index)):
        raise MeasuredRolloutError("deterministic request assignment was changed")
    row = observation["measurement"]
    _keys(row, {"case_id", "index", "candidate", "baseline"}, "measured paired request")
    case = plan.suite.cases[index]
    if type(row["index"]) is not int or row["index"] != index or row["case_id"] != case.case_id:
        raise MeasuredRolloutError("paired request case identity changed")
    seed = plan.seed + (4096 if phase == "canary" else 0) + index * 4
    for role in ("candidate", "baseline"):
        sample = row[role]
        _keys(sample, {"answer", "judgment", "gold"}, "labeled paired output")
        _measurement(
            sample["answer"],
            prompt=case.prompt,
            max_tokens=case.max_output_tokens,
            seed=seed,
            model_digest=binding[role]["model_digest"],
        )
        if type(sample["gold"]) is not bool or sample["gold"] != evaluation_case_passes(
            case, sample["answer"]["output"]
        ):
            raise MeasuredRolloutError("actual paired output gold classification changed")
        judgment = sample["judgment"]
        _keys(
            judgment,
            {
                "input_digest",
                "output",
                "input_tokens",
                "output_tokens",
                "elapsed_ns",
                "model_digest",
                "decision",
                "confidence",
            },
            "actual verifier judgment",
        )
        parsed = parse_verifier_output(judgment["output"])
        if type(judgment["confidence"]) is bool or parsed != {
            "decision": judgment["decision"],
            "confidence": judgment["confidence"],
        }:
            raise MeasuredRolloutError("actual verifier parser evidence changed")
        _measurement(
            {key: value for key, value in judgment.items() if key not in {"decision", "confidence"}},
            prompt=LocalVerifier.prompt(case.prompt, sample["answer"]["output"]),
            max_tokens=256,
            seed=seed + 2,
            model_digest=binding["verifier"]["model_digest"],
        )
    if len(canonical(observation).encode("utf-8")) > MAX_CASE_BYTES:
        raise MeasuredRolloutError("rollout case evidence exceeds byte bound")


def _lifecycle_identity(registry, model_digest, sequence):
    integer(sequence, "lifecycle sequence", maximum=len(registry._history))
    history = [item for item in registry._history[:sequence] if item.model_digest == model_digest]
    state = history[-1].to_state if history else ModelLifecycleState.CANDIDATE.value
    return digest(
        {
            "model_digest": model_digest,
            "mbom_digest": registry.mbom(model_digest).digest,
            "state": state,
            "history": [item.receipt_digest for item in history],
        }
    )


def _check_mbom_source(mbom, source):
    if mbom.model_id != source["model_id"] or mbom.model_digest != source["model_digest"]:
        raise MeasuredRolloutError("MBOM and actual model identity mismatch")
    identity = source["training_identity"]
    if identity["kind"] == "model_program":
        receipt = TrainingReceipt(**identity["receipt"])
        if (
            mbom.artifact_digest,
            mbom.training_run_id,
            mbom.training_receipt_digest,
            mbom.dataset_digests,
            mbom.trainer_id,
            mbom.code_revision,
        ) != (
            receipt.artifact_digest,
            receipt.run_id,
            receipt.digest,
            receipt.dataset_digests,
            receipt.trainer_id,
            receipt.code_revision,
        ):
            raise MeasuredRolloutError("MBOM is not bound to the issued training receipt")
    else:
        artifact = identity["artifact"]
        if (mbom.training_run_id, mbom.dataset_digests, mbom.training_receipt_digest) != (
            artifact["run_id"],
            (artifact["dataset_digest"],),
            artifact.get("training_receipt_digest", digest(artifact)),
        ):
            raise MeasuredRolloutError("MBOM is not bound to the completed native training artifact")


def _binding(registry, binding):
    _keys(
        binding,
        {
            "plan",
            "candidate",
            "baseline",
            "verifier",
            "candidate_mbom_digest",
            "baseline_mbom_digest",
            "candidate_lifecycle_digest",
            "baseline_lifecycle_digest",
            "lifecycle_sequence",
            "controller_code_digest",
            "shared_training_fingerprints",
        },
        "rollout binding",
    )
    plan = _plan(binding["plan"])
    for role in ("candidate", "baseline", "verifier"):
        _source(binding[role])
    if len({binding[role]["model_digest"] for role in ("candidate", "baseline", "verifier")}) != 3:
        raise MeasuredRolloutError("rollout verifier must be independent of both generators")
    sha(binding["controller_code_digest"], "controller code digest")
    for role in ("candidate", "baseline"):
        mbom = registry.mbom(binding[role]["model_digest"])
        _check_mbom_source(mbom, binding[role])
        if set(plan.policy.required_rights_refs) - set(mbom.rights_refs):
            raise MeasuredRolloutError("required rights declarations do not cover rollout scope")
        if binding[role + "_mbom_digest"] != mbom.digest or binding[
            role + "_lifecycle_digest"
        ] != _lifecycle_identity(registry, mbom.model_digest, binding["lifecycle_sequence"]):
            raise MeasuredRolloutError("rollout does not bind exact admitted lifecycle history")
    source_history = [
        item
        for item in registry._history[: binding["lifecycle_sequence"]]
        if item.model_digest == binding["baseline"]["model_digest"]
    ]
    candidate_history = [
        item
        for item in registry._history[: binding["lifecycle_sequence"]]
        if item.model_digest == binding["candidate"]["model_digest"]
    ]
    if (
        not source_history
        or source_history[-1].to_state != "active"
        or not candidate_history
        or candidate_history[-1].to_state != "validated"
    ):
        raise MeasuredRolloutError("rollout requires an admitted active baseline and validated candidate")
    heldout = {_fingerprint(case.prompt) for case in plan.suite.cases} | {
        _fingerprint(case.prompt + "\n" + case.expected_substring) for case in plan.suite.cases
    }
    if any(
        heldout.intersection(binding[role]["document_fingerprints"])
        for role in ("candidate", "baseline", "verifier")
    ):
        raise MeasuredRolloutError("rollout held-out sample is present in training corpus")
    shared = sorted(
        set(binding["verifier"]["document_fingerprints"])
        & (
            set(binding["candidate"]["document_fingerprints"])
            | set(binding["baseline"]["document_fingerprints"])
        )
    )
    if shared != binding["shared_training_fingerprints"]:
        raise MeasuredRolloutError("shared training evidence mismatch")
    return plan


def _metrics(binding, phase, observations):
    plan = _plan(binding["plan"])
    cases = [item["measurement"] for item in observations]
    metrics = derive_metrics(cases)
    metrics["output_parity"] = sum(
        row["candidate"]["answer"]["output"] == row["baseline"]["answer"]["output"] for row in cases
    ) / len(cases)
    metrics["selected_candidate_requests"] = sum(
        item["assignment"]["selected_role"] == "candidate" for item in observations
    )
    metrics["selected_baseline_requests"] = len(cases) - metrics["selected_candidate_requests"]
    metrics["total_tokens"] = metrics["total_cost_units"] = 0
    maximum_elapsed = 0
    for role in ("candidate", "baseline", "verifier"):
        measurements = (
            [row[role]["answer"] for row in cases]
            if role != "verifier"
            else [row[generator]["judgment"] for row in cases for generator in ("candidate", "baseline")]
        )
        tariff = getattr(plan.policy, role + "_tariff")
        metrics[role + "_input_tokens"] = sum(row["input_tokens"] for row in measurements)
        metrics[role + "_output_tokens"] = sum(row["output_tokens"] for row in measurements)
        metrics[role + "_cost_units"] = integer(
            metrics[role + "_input_tokens"] * tariff.input_unit_cost
            + metrics[role + "_output_tokens"] * tariff.output_unit_cost,
            "actual local cost",
            maximum=MAX_COST,
        )
        metrics["total_tokens"] += metrics[role + "_input_tokens"] + metrics[role + "_output_tokens"]
        metrics["total_cost_units"] += metrics[role + "_cost_units"]
        maximum_elapsed = max(maximum_elapsed, *(row["elapsed_ns"] for row in measurements))
    integer(metrics["total_cost_units"], "total actual local cost", maximum=MAX_COST)
    metrics["max_inference_elapsed_ns"] = maximum_elapsed
    metrics["selected_output_digest"] = digest(
        [
            {
                "request_id": item["assignment"]["request_id"],
                "model_digest": binding[item["assignment"]["selected_role"]]["model_digest"],
                "output": item["measurement"][item["assignment"]["selected_role"]]["answer"]["output"],
            }
            for item in observations
        ]
    )
    return metrics


def _reasons(binding, metrics):
    plan = _plan(binding["plan"])
    policy = plan.policy
    reasons = list(qualification_reasons(metrics, policy.verifier_policy, binding))
    if metrics["output_parity"] < policy.min_output_parity:
        reasons.append("output_parity_below_threshold")
    if (
        metrics["candidate_output_tokens"] - metrics["baseline_output_tokens"]
        > policy.max_additional_output_tokens
    ):
        reasons.append("candidate_output_usage_regressed")
    if metrics["candidate_cost_units"] - metrics["baseline_cost_units"] > policy.max_additional_cost_units:
        reasons.append("candidate_cost_proxy_regressed")
    if metrics["total_tokens"] > policy.max_total_tokens:
        reasons.append("actual_usage_budget_exceeded")
    if metrics["total_cost_units"] > policy.max_total_cost_units:
        reasons.append("actual_cost_proxy_budget_exceeded")
    if metrics["max_inference_elapsed_ns"] > policy.max_inference_elapsed_ns:
        reasons.append("actual_latency_budget_exceeded")
    # Rights references are declarations, while current native authority is
    # checked by source_authority at each live admission/publication boundary.
    return tuple(reasons)


@dataclass(frozen=True, slots=True)
class RolloutMeasurementReceipt:
    run_id: str
    phase: str
    binding_digest: str
    cases_digest: str
    metrics_json: str

    def __post_init__(self):
        text(self.run_id, "run_id", 256)
        if self.phase not in _PHASES:
            raise MeasuredRolloutError("unsupported rollout phase")
        sha(self.binding_digest, "binding digest")
        sha(self.cases_digest, "cases digest")
        if not isinstance(decode(self.metrics_json), dict):
            raise MeasuredRolloutError("rollout metrics must be canonical JSON object")

    @property
    def metrics(self):
        return decode(self.metrics_json)

    @property
    def digest(self):
        return digest(asdict(self))


@dataclass(frozen=True, slots=True)
class RolloutStageReceipt:
    run_id: str
    binding_digest: str
    shadow_receipt_digest: str
    canary_receipt_digest: str
    status: str
    reasons: tuple[str, ...]

    def __post_init__(self):
        text(self.run_id, "run_id", 256)
        for name in ("binding_digest", "shadow_receipt_digest", "canary_receipt_digest"):
            sha(getattr(self, name), name)
        if (
            self.status not in {"staged_candidate", "rejected"}
            or not isinstance(self.reasons, tuple)
            or len(set(self.reasons)) != len(self.reasons)
            or (self.status == "rejected") != bool(self.reasons)
        ):
            raise MeasuredRolloutError("rollout stage status/reasons are invalid")
        for reason in self.reasons:
            text(reason, "stage reason")

    @property
    def digest(self):
        return digest(asdict(self))

    @property
    def production_routing_authorized(self):
        return False


@dataclass(frozen=True, slots=True)
class RolloutActionReceipt:
    run_id: str
    stage_digest: str
    action: str
    lifecycle_receipt_digest: str | None
    evidence_refs: tuple[str, ...]

    def __post_init__(self):
        text(self.run_id, "run_id", 256)
        sha(self.stage_digest, "stage digest")
        if self.action not in {"cutover_candidate", "rollback_candidate", "withdraw_stage"}:
            raise MeasuredRolloutError("unsupported rollout action")
        if (self.lifecycle_receipt_digest is None) != (self.action == "withdraw_stage"):
            raise MeasuredRolloutError("rollout action lacks exact lifecycle evidence")
        if self.lifecycle_receipt_digest is not None:
            sha(self.lifecycle_receipt_digest, "lifecycle receipt digest")
        if (
            not isinstance(self.evidence_refs, tuple)
            or not 2 <= len(self.evidence_refs) <= 128
            or len(set(self.evidence_refs)) != len(self.evidence_refs)
        ):
            raise MeasuredRolloutError("rollout action needs bounded unique evidence references")
        for value in self.evidence_refs:
            text(value, "action evidence")

    @property
    def digest(self):
        return digest(asdict(self))

    @property
    def production_routing_authorized(self):
        return False


def _payload(receipt):
    return decode(canonical(asdict(receipt)))


def _measurement_receipt(binding, phase, observations):
    return RolloutMeasurementReceipt(
        binding["plan"]["run_id"],
        phase,
        digest(binding),
        digest(observations),
        canonical(_metrics(binding, phase, observations)),
    )


def _stage_receipt(binding, phases):
    reasons = []
    receipts = []
    for phase in _PHASES:
        receipt = _measurement_receipt(binding, phase, phases[phase]["cases"])
        receipts.append(receipt)
        reasons.extend(phase + ":" + reason for reason in _reasons(binding, receipt.metrics))
        if phase == "canary" and (
            receipt.metrics["selected_candidate_requests"] == 0
            or receipt.metrics["selected_baseline_requests"] == 0
        ):
            reasons.append("canary:assignment_coverage_insufficient")
    return RolloutStageReceipt(
        binding["plan"]["run_id"],
        digest(binding),
        receipts[0].digest,
        receipts[1].digest,
        "rejected" if reasons else "staged_candidate",
        tuple(reasons),
    )


def _decode_stage(payload):
    _keys(
        payload,
        asdict(RolloutStageReceipt("valid", "a" * 64, "b" * 64, "c" * 64, "staged_candidate", ())),
        "stage",
    )
    return RolloutStageReceipt(**{**payload, "reasons": tuple(payload["reasons"])})


def _decode_action(payload):
    _keys(
        payload, {"run_id", "stage_digest", "action", "lifecycle_receipt_digest", "evidence_refs"}, "action"
    )
    return RolloutActionReceipt(**{**payload, "evidence_refs": tuple(payload["evidence_refs"])})


def validate_rollouts(registry, records):
    """Validate complete historical rollout evidence without live inference."""
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_ROLLOUTS:
        raise MeasuredRolloutError("snapshot rollout count is invalid")
    result = {}
    for record in records:
        _keys(record, {"binding", "phases", "stage", "cutover", "rollback", "withdrawal"}, "rollout record")
        binding = record["binding"]
        plan = _binding(registry, binding)
        if plan.run_id in result:
            raise MeasuredRolloutError("duplicate rollout identity")
        _keys(record["phases"], _PHASES, "phases")
        for phase in _PHASES:
            state = record["phases"][phase]
            _keys(state, {"owner", "epoch", "expires", "cases", "receipt", "decisions"}, "phase state")
            if state["decisions"] != [
                _assignment(plan, phase, index) for index in range(len(plan.suite.cases))
            ]:
                raise MeasuredRolloutError("persisted request assignment decisions changed")
            integer(state["epoch"], "worker epoch")
            if (state["owner"] is None) != (state["expires"] is None):
                raise MeasuredRolloutError("phase lease is malformed")
            if state["owner"] is not None:
                text(state["owner"], "worker owner")
                if (
                    isinstance(state["expires"], bool)
                    or not isinstance(state["expires"], (int, float))
                    or not math.isfinite(state["expires"])
                ):
                    raise MeasuredRolloutError("lease expiry must be finite")
            observations = state["cases"]
            if state["epoch"] == 0 and (
                state["owner"] is not None or observations or state["receipt"] is not None
            ):
                raise MeasuredRolloutError("unstarted phase carries fabricated worker evidence")
            if not isinstance(observations, list) or len(observations) > len(plan.suite.cases):
                raise MeasuredRolloutError("phase case count is invalid")
            for index, observation in enumerate(observations):
                _validate_observation(observation, index, binding, phase, plan)
            if state["receipt"] is not None:
                if (
                    len(observations) != len(plan.suite.cases)
                    or state["owner"] is not None
                    or state["receipt"] != asdict(_measurement_receipt(binding, phase, observations))
                ):
                    raise MeasuredRolloutError("phase receipt does not bind drained complete measurements")
            elif record["stage"] is not None:
                raise MeasuredRolloutError("stage lacks both completed measured phases")
        if record["phases"]["canary"]["epoch"] and record["phases"]["shadow"]["receipt"] is None:
            raise MeasuredRolloutError("canary started before shadow completed")
        stage = None
        if record["stage"] is not None:
            stage = _decode_stage(record["stage"])
            if stage != _stage_receipt(binding, record["phases"]):
                raise MeasuredRolloutError("rollout stage gate evidence was changed")
        for name, action_name in (
            ("cutover", "cutover_candidate"),
            ("rollback", "rollback_candidate"),
            ("withdrawal", "withdraw_stage"),
        ):
            if record[name] is None:
                continue
            action = _decode_action(record[name])
            if (
                stage is None
                or action.run_id != plan.run_id
                or action.stage_digest != stage.digest
                or action.action != action_name
            ):
                raise MeasuredRolloutError("rollout action is orphaned or rebound")
            if name == "cutover":
                if stage.reasons or record["withdrawal"] is not None:
                    raise MeasuredRolloutError("failed or withdrawn stage was cut over")
                migration = next(
                    (
                        item
                        for item in registry._migrations.values()
                        if item.receipt_digest == action.lifecycle_receipt_digest
                    ),
                    None,
                )
                if (
                    migration is None
                    or (migration.source_model_digest, migration.target_model_digest)
                    != (binding["baseline"]["model_digest"], binding["candidate"]["model_digest"])
                    or migration.evaluation_refs != action.evidence_refs
                ):
                    raise MeasuredRolloutError("cutover lacks exact lifecycle migration")
                evaluation = registry._decisions[migration.decision_digest].evaluation
                if (
                    migration.evaluation_refs
                    != ("rollout-stage:" + stage.digest, "rollout-canary:" + stage.canary_receipt_digest)
                    or migration.verifier_id != "measured-rollout:" + binding["verifier"]["model_digest"]
                    or migration.source_lifecycle_digest != binding["baseline_lifecycle_digest"]
                    or migration.target_lifecycle_digest != binding["candidate_lifecycle_digest"]
                    or evaluation.required_score != plan.policy.min_output_parity
                ):
                    raise MeasuredRolloutError("cutover identity does not bind the exact measured stage")
                if tuple(evaluation.cases) != _parity_cases(record):
                    raise MeasuredRolloutError(
                        "cutover migration parity is not actual canary output evidence"
                    )
            elif name == "rollback":
                if record["cutover"] is None:
                    raise MeasuredRolloutError("rollback has no cutover")
                rollback = next(
                    (
                        item
                        for item in registry._rollbacks.values()
                        if item.receipt_digest == action.lifecycle_receipt_digest
                    ),
                    None,
                )
                if (
                    rollback is None
                    or rollback.migration_receipt_digest != record["cutover"]["lifecycle_receipt_digest"]
                    or rollback.evidence_refs != action.evidence_refs
                ):
                    raise MeasuredRolloutError("rollback lacks exact lifecycle compensation")
            elif record["cutover"] is not None:
                raise MeasuredRolloutError("withdrawal cannot replace an applied cutover")
        result[plan.run_id] = decode(canonical(record))
    return result


def require_rollout_extension(previous, current):
    for run_id, prior in previous.items():
        updated = current.get(run_id)
        if updated is None or updated["binding"] != prior["binding"]:
            raise MeasuredRolloutError("immutable rollout binding was removed or changed")
        for phase in _PHASES:
            old, new = prior["phases"][phase], updated["phases"][phase]
            if (
                new["cases"][: len(old["cases"])] != old["cases"]
                or new["epoch"] < old["epoch"]
                or old["receipt"] is not None
                and new["receipt"] != old["receipt"]
            ):
                raise MeasuredRolloutError("rollout immutable case/lease history was changed")
        for key in ("stage", "cutover", "rollback", "withdrawal"):
            if prior[key] is not None and updated[key] != prior[key]:
                raise MeasuredRolloutError("immutable rollout receipt was removed or changed")


def _parity_cases(record):
    return tuple(
        MigrationParityCase(
            case_id=item["assignment"]["request_id"],
            input_digest=item["measurement"]["baseline"]["answer"]["input_digest"],
            source_output_digest=digest(item["measurement"]["baseline"]["answer"]["output"]),
            target_output_digest=digest(item["measurement"]["candidate"]["answer"]["output"]),
        )
        for item in record["phases"]["canary"]["cases"]
    )


class MeasuredModelRollout:
    """Actual bounded local rollout with lifecycle-owned restart-safe evidence."""

    def __init__(self, registry: ModelLifecycleRegistry):
        if not isinstance(registry, ModelLifecycleRegistry):
            raise TypeError("existing ModelLifecycleRegistry is required")
        self.registry = registry
        self._token = _Writer()
        _WRITERS.add(self._token)
        self._handles = {}

    def _access(self, callback, *, fence=None):
        return self.registry._rollout_access(callback, _token=self._token, _commit_fence=fence)

    def _issue(self, receipt):
        cached = self._handles.get(receipt.digest)
        handle = cached if cached == receipt else receipt
        self._handles[receipt.digest] = handle
        return handle

    def _require(self, receipt):
        if (
            not isinstance(receipt, (RolloutMeasurementReceipt, RolloutStageReceipt, RolloutActionReceipt))
            or self._handles.get(receipt.digest) is not receipt
        ):
            raise MeasuredRolloutError("rollout action requires a controller-issued receipt handle")

    @staticmethod
    def mbom_for_source(
        source: EvaluationModelSource, *, license_refs: Sequence[str], rights_refs: Sequence[str]
    ):
        source.assert_current()
        payload = source.payload
        identity = payload["training_identity"]
        if identity["kind"] == "model_program":
            receipt = TrainingReceipt(**identity["receipt"])
            values = {
                "artifact_digest": receipt.artifact_digest,
                "training_run_id": receipt.run_id,
                "training_receipt_digest": receipt.digest,
                "dataset_digests": receipt.dataset_digests,
                "trainer_id": receipt.trainer_id,
                "code_revision": receipt.code_revision,
            }
        else:
            artifact = identity["artifact"]
            values = {
                "artifact_digest": digest(source.model.to_dict()),
                "training_run_id": artifact["run_id"],
                "training_receipt_digest": artifact.get("training_receipt_digest", digest(artifact)),
                "dataset_digests": (artifact["dataset_digest"],),
                "trainer_id": "canonical-completed-local-training",
                "code_revision": identity["manifest_digest"],
            }
        return ModelBillOfMaterials(
            model_id=payload["model_id"],
            model_digest=payload["model_digest"],
            artifact_kind="local-text-evaluation-artifact",
            license_refs=tuple(license_refs),
            rights_refs=tuple(rights_refs),
            **values,
        )

    def _sources(self, record, sources, *, restoring=False):
        roles = ("baseline", "verifier") if restoring else ("candidate", "baseline", "verifier")
        for role in roles:
            source = sources[role]
            if not isinstance(source, EvaluationModelSource) or source.payload != record["binding"][role]:
                raise MeasuredRolloutError("current rollout source identity differs from admitted binding")
            source.assert_current()
            if role != "verifier" and self.registry.mbom(source.model.model_digest).artifact_digest != digest(
                source.model.to_dict()
            ):
                raise MeasuredRolloutError("actual weights do not match the admitted MBOM artifact")
        if record["binding"]["controller_code_digest"] != _implementation_digest():
            raise MeasuredRolloutError("rollout implementation identity changed")

    def _current(self, record):
        for role in ("candidate", "baseline"):
            pinned = record["binding"][role + "_lifecycle_digest"]
            if self.registry.lifecycle_digest(record["binding"][role]["model_digest"]) != pinned:
                raise MeasuredRolloutError("rollout model lifecycle identity is stale")

    async def run(
        self,
        plan: RolloutPlan,
        *,
        candidate: EvaluationModelSource,
        baseline: EvaluationModelSource,
        verifier: EvaluationModelSource,
        phase: str = "shadow",
        worker_id: str = "local-rollout-worker",
        lease_seconds: int = 30,
    ):
        if not isinstance(plan, RolloutPlan) or phase not in _PHASES:
            raise MeasuredRolloutError("typed plan and declared phase are required")
        text(worker_id, "worker id")
        integer(lease_seconds, "lease seconds", 1, 3600)
        sources = {"candidate": candidate, "baseline": baseline, "verifier": verifier}
        if any(not isinstance(source, EvaluationModelSource) for source in sources.values()):
            raise TypeError("issued actual local model sources are required")
        with source_authority(tuple(sources.values())):

            def admit(registry):
                existing = registry._rollouts.get(plan.run_id)
                if existing is None:
                    if len(registry._rollouts) >= MAX_ROLLOUTS or phase != "shadow":
                        raise MeasuredRolloutError("rollout intake requires shadow and available inventory")
                    binding = {
                        "plan": decode(canonical(plan.as_dict())),
                        **{role: source.payload for role, source in sources.items()},
                        "lifecycle_sequence": len(registry._history),
                        "controller_code_digest": _implementation_digest(),
                        "shared_training_fingerprints": sorted(
                            set(verifier.payload["document_fingerprints"])
                            & (
                                set(candidate.payload["document_fingerprints"])
                                | set(baseline.payload["document_fingerprints"])
                            )
                        ),
                    }
                    for role in ("candidate", "baseline"):
                        binding[role + "_mbom_digest"] = registry.mbom(
                            sources[role].model.model_digest
                        ).digest
                        binding[role + "_lifecycle_digest"] = registry.lifecycle_digest(
                            sources[role].model.model_digest
                        )
                    _binding(registry, binding)
                    for role in ("candidate", "baseline"):
                        if set(plan.policy.required_rights_refs) - set(
                            registry.mbom(sources[role].model.model_digest).rights_refs
                        ):
                            raise MeasuredRolloutError(
                                "required rollout rights are not declared by both MBOMs"
                            )
                    existing = {
                        "binding": binding,
                        "phases": {
                            name: {
                                "owner": None,
                                "epoch": 0,
                                "expires": None,
                                "cases": [],
                                "receipt": None,
                                "decisions": [
                                    _assignment(plan, name, index) for index in range(len(plan.suite.cases))
                                ],
                            }
                            for name in _PHASES
                        },
                        "stage": None,
                        "cutover": None,
                        "rollback": None,
                        "withdrawal": None,
                    }
                    registry._rollouts[plan.run_id] = existing
                if existing["binding"]["plan"] != decode(canonical(plan.as_dict())):
                    raise MeasuredRolloutError("rollout plan is immutable")
                self._sources(existing, sources)
                state = existing["phases"][phase]
                if state["receipt"] is not None:
                    return None
                self._current(existing)
                if (
                    existing["stage"] is not None
                    or existing["withdrawal"] is not None
                    or phase == "canary"
                    and existing["phases"]["shadow"]["receipt"] is None
                ):
                    raise MeasuredRolloutError("rollout phase is not admitted")
                if state["owner"] is not None and state["expires"] > time.time():
                    raise MeasuredRolloutError("rollout phase already has an active worker")
                state.update(
                    owner=worker_id,
                    epoch=integer(state["epoch"] + 1, "epoch", 1),
                    expires=time.time() + lease_seconds,
                )
                return state["epoch"]

            def admission_fence(registry):
                state = registry._rollouts[plan.run_id]["phases"][phase]
                if state["receipt"] is None:
                    self._owned(registry._rollouts[plan.run_id], phase, worker_id, state["epoch"])

            epoch = self._access(admit, fence=admission_fence)
        if epoch is None:
            return self.receipt(plan.run_id, phase)
        try:
            for index, case in enumerate(plan.suite.cases):

                def claim(registry, index=index):
                    record = registry._rollouts[plan.run_id]
                    self._sources(record, sources)
                    self._current(record)
                    state = self._owned(record, phase, worker_id, epoch)
                    if len(state["cases"]) > index:
                        return True
                    state["expires"] = time.time() + lease_seconds
                    return False

                with source_authority(tuple(sources.values())):
                    if self._access(
                        claim,
                        fence=lambda registry: self._owned(
                            registry._rollouts[plan.run_id], phase, worker_id, epoch
                        ),
                    ):
                        continue
                row = {"case_id": case.case_id, "index": index}
                base_seed = plan.seed + (4096 if phase == "canary" else 0) + index * 4
                for offset, role in enumerate(("candidate", "baseline")):
                    answer = await _generate(sources[role], case.prompt, case.max_output_tokens, base_seed)
                    judgment = await LocalVerifier(verifier).judge(
                        case.prompt, answer["output"], seed=base_seed + 2
                    )
                    row[role] = {
                        "answer": answer,
                        "judgment": judgment,
                        "gold": evaluation_case_passes(case, answer["output"]),
                    }
                observation = {"assignment": _assignment(plan, phase, index), "measurement": row}

                def append(registry, index=index, observation=observation):
                    record = registry._rollouts[plan.run_id]
                    self._sources(record, sources)
                    self._current(record)
                    state = self._owned(record, phase, worker_id, epoch)
                    if len(state["cases"]) != index:
                        raise MeasuredRolloutError("rollout case compare-and-swap conflict")
                    _validate_observation(observation, index, record["binding"], phase, plan)
                    self._owned(record, phase, worker_id, epoch)
                    state["cases"].append(observation)

                with source_authority(tuple(sources.values())):
                    self._access(
                        append,
                        fence=lambda registry: self._owned(
                            registry._rollouts[plan.run_id], phase, worker_id, epoch
                        ),
                    )

            completion = {}

            def complete(registry):
                record = registry._rollouts[plan.run_id]
                self._sources(record, sources)
                self._current(record)
                state = self._owned(record, phase, worker_id, epoch)
                if len(state["cases"]) != len(plan.suite.cases):
                    raise MeasuredRolloutError("phase lacks full measured coverage")
                receipt = _measurement_receipt(record["binding"], phase, state["cases"])
                self._owned(record, phase, worker_id, epoch)
                completion["deadline"] = state["expires"]
                completion["receipt"] = asdict(receipt)
                state.update(owner=None, expires=None, receipt=asdict(receipt))
                return receipt

            def completion_fence(registry):
                state = registry._rollouts[plan.run_id]["phases"][phase]
                if (
                    time.time() >= completion["deadline"]
                    or state["epoch"] != epoch
                    or state["receipt"] != completion["receipt"]
                ):
                    raise MeasuredRolloutError("rollout completion lease expired before publication")

            with source_authority(tuple(sources.values())):
                return self._issue(self._access(complete, fence=completion_fence))
        except BaseException:

            def release(registry):
                state = registry._rollouts[plan.run_id]["phases"][phase]
                if (state["owner"], state["epoch"]) == (worker_id, epoch):
                    state.update(owner=None, expires=None)

            self._access(release)
            raise

    @staticmethod
    def _owned(record, phase, worker_id, epoch):
        state = record["phases"][phase]
        if (
            state["receipt"] is not None
            or state["owner"] != worker_id
            or state["epoch"] != epoch
            or state["expires"] is None
            or state["expires"] <= time.time()
        ):
            raise MeasuredRolloutError("rollout worker epoch is stale or expired")
        return state

    def receipt(self, run_id, phase):
        def read(registry):
            text(run_id, "run_id", 256)
            if (
                phase not in _PHASES
                or run_id not in registry._rollouts
                or registry._rollouts[run_id]["phases"][phase]["receipt"] is None
            ):
                raise MeasuredRolloutError("rollout phase has no completed issued receipt")
            return RolloutMeasurementReceipt(**registry._rollouts[run_id]["phases"][phase]["receipt"])

        return self._issue(self._access(read))

    def request_decision(self, run_id, phase, index):
        def read(registry):
            record = registry._rollouts.get(text(run_id, "run id", 256))
            if record is None or phase not in _PHASES:
                raise MeasuredRolloutError("unknown rollout phase")
            integer(index, "request index", maximum=len(record["phases"][phase]["decisions"]) - 1)
            return decode(canonical(record["phases"][phase]["decisions"][index]))

        return self._access(read)

    def request_result(self, run_id, phase, index):
        def read(registry):
            record = registry._rollouts.get(text(run_id, "run id", 256))
            if record is None or phase not in _PHASES:
                raise MeasuredRolloutError("unknown rollout phase")
            integer(index, "request index", maximum=len(record["phases"][phase]["cases"]) - 1)
            return decode(canonical(record["phases"][phase]["cases"][index]))

        return self._access(read)

    def stage(self, receipt: RolloutMeasurementReceipt, *, candidate, baseline, verifier):
        self._require(receipt)
        sources = {"candidate": candidate, "baseline": baseline, "verifier": verifier}
        with source_authority(tuple(sources.values())):

            def stage(registry):
                record = registry._rollouts[receipt.run_id]
                self._sources(record, sources)
                if receipt.phase != "canary" or record["phases"]["canary"]["receipt"] != asdict(receipt):
                    raise MeasuredRolloutError("stage requires exact issued canary receipt")
                if record["stage"] is None:
                    self._current(record)
                    record["stage"] = _payload(_stage_receipt(record["binding"], record["phases"]))
                return _decode_stage(record["stage"])

            return self._issue(self._access(stage))

    def cutover(self, stage: RolloutStageReceipt, *, candidate, baseline, verifier):
        self._require(stage)
        sources = {"candidate": candidate, "baseline": baseline, "verifier": verifier}
        with source_authority(tuple(sources.values())):

            def cutover(registry):
                record = registry._rollouts[stage.run_id]
                self._sources(record, sources)
                if (
                    record["stage"] != decode(canonical(asdict(stage)))
                    or stage.reasons
                    or record["withdrawal"] is not None
                ):
                    raise MeasuredRolloutError("rollout stage is unissued, rejected or withdrawn")
                if record["cutover"] is not None:
                    return _decode_action(record["cutover"])
                self._current(record)
                refs = ("rollout-stage:" + stage.digest, "rollout-canary:" + stage.canary_receipt_digest)
                decision = registry.evaluate_migration(
                    source_model_digest=baseline.model.model_digest,
                    target_model_digest=candidate.model.model_digest,
                    cases=_parity_cases(record),
                    required_score=_plan(record["binding"]["plan"]).policy.min_output_parity,
                    verifier_id="measured-rollout:" + verifier.model.model_digest,
                    evaluation_refs=refs,
                )
                migration = registry.apply_migration(decision)
                action = RolloutActionReceipt(
                    stage.run_id, stage.digest, "cutover_candidate", migration.receipt_digest, refs
                )
                record["cutover"] = _payload(action)
                return action

            return self._issue(self._access(cutover))

    def rollback(self, receipt, *, baseline, verifier, evidence_refs: Sequence[str]):
        self._require(receipt)
        refs = tuple(evidence_refs)
        sources = {"baseline": baseline, "verifier": verifier}
        with source_authority(tuple(sources.values())):

            def rollback(registry):
                record = registry._rollouts[receipt.run_id]
                self._sources(record, sources, restoring=True)
                stage = _decode_stage(record["stage"])
                if isinstance(receipt, RolloutStageReceipt):
                    if receipt != stage or record["cutover"] is not None:
                        raise MeasuredRolloutError("stage withdrawal is stale")
                    key = "withdrawal"
                    action = RolloutActionReceipt(stage.run_id, stage.digest, "withdraw_stage", None, refs)
                    self._current(record)
                elif isinstance(receipt, RolloutActionReceipt) and record["cutover"] == decode(
                    canonical(asdict(receipt))
                ):
                    key = "rollback"
                    migration = next(
                        item
                        for item in registry.migrations
                        if item.receipt_digest == receipt.lifecycle_receipt_digest
                    )
                    restored = registry.rollback_migration(
                        migration,
                        verifier_id="measured-rollout:" + verifier.model.model_digest,
                        evidence_refs=refs,
                    )
                    action = RolloutActionReceipt(
                        stage.run_id, stage.digest, "rollback_candidate", restored.receipt_digest, refs
                    )
                else:
                    raise MeasuredRolloutError("rollback requires the exact stage or applied cutover")
                prior = record[key]
                if prior is not None and prior != decode(canonical(asdict(action))):
                    raise MeasuredRolloutError("rollback replay changed evidence")
                record[key] = _payload(action)
                return action

            return self._issue(self._access(rollback))

    def action(self, run_id, action="cutover"):
        def read(registry):
            if (
                action not in {"cutover", "rollback", "withdrawal"}
                or run_id not in registry._rollouts
                or registry._rollouts[run_id][action] is None
            ):
                raise MeasuredRolloutError("rollout action receipt is unavailable")
            return _decode_action(registry._rollouts[run_id][action])

        return self._issue(self._access(read))
