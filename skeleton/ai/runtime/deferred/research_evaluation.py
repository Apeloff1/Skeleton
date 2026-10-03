"""Research, evaluation, provider and evidence controls for deferred AI work."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from statistics import mean
from typing import Iterable, Mapping, Sequence

from .contracts import sha256_json


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _digest(value: str, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be lowercase sha256")
    return value


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class ArtifactRevision:
    artifact_id: str
    version: int
    digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", _text(self.artifact_id, "artifact_id"))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("version must be positive integer")
        object.__setattr__(self, "digest", _digest(self.digest, "digest"))


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    artifact: ArtifactRevision
    reviewer_id: str
    approved: bool
    review_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reviewer_id", _text(self.reviewer_id, "reviewer_id"))
        if not isinstance(self.approved, bool):
            raise TypeError("approved must be boolean")
        object.__setattr__(self, "review_digest", _digest(self.review_digest, "review_digest"))


class ArtifactReviewWorkflow:
    def __init__(self) -> None:
        self._latest: dict[str, ArtifactRevision] = {}
        self._reviews: dict[tuple[str, int], ReviewDecision] = {}

    def submit(self, artifact: ArtifactRevision) -> None:
        prior = self._latest.get(artifact.artifact_id)
        if prior is not None and artifact.version <= prior.version:
            if artifact == prior:
                return
            raise ValueError("artifact revision must advance monotonically")
        self._latest[artifact.artifact_id] = artifact

    def decide(self, decision: ReviewDecision) -> None:
        current = self._latest.get(decision.artifact.artifact_id)
        if current != decision.artifact:
            raise ValueError("review targets stale artifact revision")
        key = (decision.artifact.artifact_id, decision.artifact.version)
        prior = self._reviews.get(key)
        if prior is not None and prior != decision:
            raise ValueError("review decision collision")
        self._reviews[key] = decision


@dataclass(frozen=True, slots=True)
class ResearchRole:
    role_id: str
    purpose: str
    independence_group: str

    def __post_init__(self) -> None:
        for name in ("role_id", "purpose", "independence_group"):
            object.__setattr__(self, name, _text(getattr(self, name), name))


class ResearchTeam:
    def __init__(self, roles: Sequence[ResearchRole]) -> None:
        roles = tuple(roles)
        ids = [r.role_id for r in roles]
        if len(ids) < 2 or len(ids) != len(set(ids)):
            raise ValueError("research team requires at least two unique roles")
        if len({r.independence_group for r in roles}) < 2:
            raise ValueError("research team needs independent review groups")
        self.roles = roles


@dataclass(frozen=True, slots=True)
class LiteratureItem:
    source_id: str
    version: str
    title: str
    source_digest: str
    retracted: bool = False

    def __post_init__(self) -> None:
        for name in ("source_id", "version", "title"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "source_digest", _digest(self.source_digest, "source_digest"))
        if not isinstance(self.retracted, bool):
            raise TypeError("retracted must be boolean")


class LiteratureWatch:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], LiteratureItem] = {}

    def ingest(self, item: LiteratureItem) -> None:
        key = (item.source_id, item.version)
        prior = self._items.get(key)
        if prior is not None and prior != item:
            raise ValueError("literature source/version collision")
        self._items[key] = item

    def active(self) -> tuple[LiteratureItem, ...]:
        return tuple(sorted(
            (item for item in self._items.values() if not item.retracted),
            key=lambda item: (item.source_id, item.version),
        ))


@dataclass(frozen=True, slots=True)
class CitationEdge:
    source_id: str
    target_id: str
    relation: str = "supports"

    def __post_init__(self) -> None:
        for name in ("source_id", "target_id", "relation"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.source_id == self.target_id:
            raise ValueError("self citation edge is forbidden")


class CitationGraph:
    def __init__(self) -> None:
        self._edges: set[CitationEdge] = set()

    def add(self, edge: CitationEdge) -> None:
        self._edges.add(edge)

    def independent_sources(self, target_id: str) -> tuple[str, ...]:
        return tuple(sorted({
            edge.source_id
            for edge in self._edges
            if edge.target_id == target_id and edge.relation in {"supports", "replicates"}
        }))

    def support_count(self, target_id: str) -> int:
        return len(self.independent_sources(target_id))


@dataclass(frozen=True, slots=True)
class ReproductionBundle:
    experiment_id: str
    code_digest: str
    environment_digest: str
    data_digest: str
    command: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "experiment_id", _text(self.experiment_id, "experiment_id"))
        for name in ("code_digest", "environment_digest", "data_digest"):
            object.__setattr__(self, name, _digest(getattr(self, name), name))
        if not self.command or any(not isinstance(item, str) or not item for item in self.command):
            raise ValueError("command must contain non-empty arguments")

    @property
    def digest(self) -> str:
        return sha256_json({
            "experiment_id": self.experiment_id,
            "code_digest": self.code_digest,
            "environment_digest": self.environment_digest,
            "data_digest": self.data_digest,
            "command": list(self.command),
        })


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    run_id: str
    experiment_id: str
    dataset_digest: str
    config_digest: str
    metric_name: str
    metric_value: float
    seed: int

    def __post_init__(self) -> None:
        for name in ("run_id", "experiment_id", "metric_name"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("dataset_digest", "config_digest"):
            object.__setattr__(self, name, _digest(getattr(self, name), name))
        object.__setattr__(self, "metric_value", _finite(self.metric_value, "metric_value"))
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be integer")


class ExperimentComparator:
    @staticmethod
    def comparable(a: ExperimentRun, b: ExperimentRun) -> bool:
        return (
            a.experiment_id == b.experiment_id
            and a.dataset_digest == b.dataset_digest
            and a.metric_name == b.metric_name
        )

    @classmethod
    def delta(cls, baseline: ExperimentRun, candidate: ExperimentRun) -> float:
        if not cls.comparable(baseline, candidate):
            raise ValueError("experiment runs are not comparable")
        return candidate.metric_value - baseline.metric_value


@dataclass(frozen=True, slots=True)
class Sample:
    sample_id: str
    value: float
    group_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "sample_id", _text(self.sample_id, "sample_id"))
        object.__setattr__(self, "group_id", _text(self.group_id, "group_id"))
        object.__setattr__(self, "value", _finite(self.value, "value"))


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    count: int
    average: float
    minimum: float
    maximum: float
    groups: int


class StatisticalAnalyzer:
    @staticmethod
    def summarize(samples: Sequence[Sample]) -> AnalysisResult:
        if not samples:
            raise ValueError("analysis requires samples")
        ids = [item.sample_id for item in samples]
        if len(ids) != len(set(ids)):
            raise ValueError("sample ids must be unique")
        values = [item.value for item in samples]
        return AnalysisResult(
            count=len(samples),
            average=mean(values),
            minimum=min(values),
            maximum=max(values),
            groups=len({item.group_id for item in samples}),
        )


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    input_digest: str
    expected_digest: str
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _text(self.case_id, "case_id"))
        object.__setattr__(self, "input_digest", _digest(self.input_digest, "input_digest"))
        object.__setattr__(self, "expected_digest", _digest(self.expected_digest, "expected_digest"))
        tags = tuple(_text(item, "tag") for item in self.tags)
        if len(tags) != len(set(tags)):
            raise ValueError("eval tags must be unique")
        object.__setattr__(self, "tags", tags)


@dataclass(frozen=True, slots=True)
class EvalOutcome:
    case_id: str
    output_digest: str
    score: float
    trajectory_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _text(self.case_id, "case_id"))
        object.__setattr__(self, "output_digest", _digest(self.output_digest, "output_digest"))
        score = _finite(self.score, "score")
        if not 0.0 <= score <= 1.0:
            raise ValueError("score must be in [0, 1]")
        object.__setattr__(self, "score", score)
        if self.trajectory_digest is not None:
            object.__setattr__(self, "trajectory_digest", _digest(self.trajectory_digest, "trajectory_digest"))


class EvaluationHarness:
    def __init__(self, cases: Sequence[EvalCase]) -> None:
        self.cases = tuple(cases)
        ids = [case.case_id for case in self.cases]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("evaluation case ids must be unique and non-empty")

    def evaluate(self, outcomes: Sequence[EvalOutcome]) -> dict[str, float]:
        by_id = {item.case_id: item for item in outcomes}
        if len(by_id) != len(outcomes):
            raise ValueError("duplicate evaluation outcomes")
        expected = {case.case_id for case in self.cases}
        if set(by_id) != expected:
            raise ValueError("evaluation must cover every case exactly once")
        scores = [by_id[case.case_id].score for case in self.cases]
        return {
            "count": float(len(scores)),
            "mean_score": mean(scores),
            "minimum_score": min(scores),
        }


class ContaminationAuditor:
    @staticmethod
    def overlaps(train_digests: Iterable[str], eval_digests: Iterable[str]) -> tuple[str, ...]:
        train = {_digest(item, "train digest") for item in train_digests}
        evaluate = {_digest(item, "eval digest") for item in eval_digests}
        return tuple(sorted(train & evaluate))


@dataclass(frozen=True, slots=True)
class HumanJudgment:
    evaluator_id: str
    case_id: str
    rubric_version: str
    score: float

    def __post_init__(self) -> None:
        for name in ("evaluator_id", "case_id", "rubric_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        score = _finite(self.score, "score")
        if not 0.0 <= score <= 1.0:
            raise ValueError("score must be in [0, 1]")
        object.__setattr__(self, "score", score)


class HumanEvaluation:
    @staticmethod
    def aggregate(judgments: Sequence[HumanJudgment], *, min_raters: int = 2) -> Mapping[str, float]:
        if isinstance(min_raters, bool) or not isinstance(min_raters, int) or min_raters < 1:
            raise ValueError("min_raters must be positive integer")
        grouped: dict[str, list[HumanJudgment]] = {}
        for item in judgments:
            grouped.setdefault(item.case_id, []).append(item)
        result: dict[str, float] = {}
        for case_id, items in grouped.items():
            rater_ids=[item.evaluator_id for item in items]
            raters=set(rater_ids)
            if len(rater_ids)!=len(raters):
                raise ValueError(
                    f"duplicate evaluator judgment for {case_id}"
                )
            if len(raters) < min_raters:
                raise ValueError(f"insufficient independent raters for {case_id}")
            if len({item.rubric_version for item in items}) != 1:
                raise ValueError("rubric version drift within case")
            result[case_id] = mean(item.score for item in items)
        return result


@dataclass(frozen=True, slots=True)
class ComponentCard:
    component_id: str
    version: str
    kind: str
    artifact_digest: str
    intended_use: str
    limitations: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("component_id", "version", "kind", "intended_use"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "artifact_digest", _digest(self.artifact_digest, "artifact_digest"))
        if self.kind not in {"model", "dataset", "tool", "agent"}:
            raise ValueError("unsupported card kind")
        if not self.limitations or not self.evidence_refs:
            raise ValueError("component card needs limitations and evidence refs")


@dataclass(frozen=True, slots=True)
class HealthScore:
    component_id: str
    reliability: float
    security: float
    freshness: float
    dependency_health: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        for name in ("reliability", "security", "freshness", "dependency_health"):
            object.__setattr__(self, name, max(0.0, min(1.0, _finite(getattr(self, name), name))))

    @property
    def total(self) -> float:
        return min(self.reliability, self.security, self.freshness, self.dependency_health)


@dataclass(frozen=True, slots=True)
class ProviderRisk:
    provider_id: str
    risk_score: float
    data_classes: tuple[str, ...]
    regions: tuple[str, ...]
    available: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", _text(self.provider_id, "provider_id"))
        object.__setattr__(self, "risk_score", _finite(self.risk_score, "risk_score"))
        if not 0.0 <= self.risk_score <= 1.0:
            raise ValueError("risk_score must be in [0, 1]")
        if not isinstance(self.available, bool):
            raise TypeError("available must be boolean")


class ProviderFailover:
    def choose(
        self,
        providers: Sequence[ProviderRisk],
        *,
        required_data_class: str,
        allowed_regions: Iterable[str],
        max_risk: float,
    ) -> ProviderRisk:
        required_data_class = _text(required_data_class, "required_data_class")
        allowed = set(allowed_regions)
        risk = _finite(max_risk, "max_risk")
        candidates = [
            item for item in providers
            if item.available
            and item.risk_score <= risk
            and required_data_class in item.data_classes
            and bool(set(item.regions) & allowed)
        ]
        if not candidates:
            raise RuntimeError("no policy-compatible provider")
        return min(candidates, key=lambda item: (item.risk_score, item.provider_id))


@dataclass(frozen=True, slots=True)
class DeploymentProfile:
    profile_id: str
    network_mode: str
    credential_mode: str
    locality: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _text(self.profile_id, "profile_id"))
        if self.network_mode not in {"online", "offline", "air_gapped"}:
            raise ValueError("unsupported network_mode")
        if self.credential_mode not in {"hosted", "local_only", "federated"}:
            raise ValueError("unsupported credential_mode")
        object.__setattr__(self, "locality", _text(self.locality, "locality"))
        if self.network_mode == "air_gapped" and self.credential_mode == "hosted":
            raise ValueError("air-gapped profile cannot require hosted credentials")


@dataclass(frozen=True, slots=True)
class InstructionRevision:
    instruction_id: str
    version: int
    content_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "instruction_id", _text(self.instruction_id, "instruction_id"))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("instruction version must be positive integer")
        object.__setattr__(self, "content_digest", _digest(self.content_digest, "content_digest"))


class InstructionRegistry:
    def __init__(self) -> None:
        self._revisions: dict[str, InstructionRevision] = {}

    def publish(self, revision: InstructionRevision) -> None:
        prior = self._revisions.get(revision.instruction_id)
        if prior is not None and revision.version <= prior.version:
            if prior == revision:
                return
            raise ValueError("instruction versions must increase")
        self._revisions[revision.instruction_id] = revision

    def current(self, instruction_id: str) -> InstructionRevision:
        return self._revisions[instruction_id]
