"""Evidence-bound comparative, objective and final originality review for Jeeves.

Release order: comparative -> objective -> copyright/provenance -> creative
rewrite. The final two stages must run last, against the *same exact* source
snapshot. Review decisions never constitute a legal guarantee; checker scope
and evidence are mandatory. The host, not the generative model, supplies the
measurements, provenance and independent content-review callbacks.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Callable, Mapping, Sequence

from .code_delivery_quality import required_delivery_kind
from .types import Goal, stable_fingerprint

_CORE_AXES = (
    "modularity", "efficiency", "performance", "cleanliness",
    "maintainability", "machine_friendly",
)
_STAGES = ("comparative", "objective", "copyright", "creative_rewrite")
_RIGHTS_AXES = ("provenance", "permissions", "license_conditions", "source_similarity")
_REWRITE_AXES = ("originality", "substantive_transformation", "canon", "author_voice")
_SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class FinalReviewError(ValueError):
    """The submitted artifact does not satisfy its release requirements."""


_CREATIVE_INTENT = re.compile(
    r"\b(?:write|draft|create|generate|compose|develop|rewrite|revise|"
    r"produce|design)\b", re.I,
)
_CREATIVE_OUTPUT = re.compile(
    r"\b(?:story|screenplay|novel|poem|poetry|lyrics|song|dialogue|"
    r"narrative|short fiction|film script|stage play|character arc)\b", re.I,
)


def required_final_kind(goal: Goal) -> str | None:
    """Classify authored creative work without weakening the code/game gate."""
    declared = goal.metadata.get("delivery_kind")
    if declared == "creative":
        return "creative"
    if declared in {"code", "game"}:
        return str(declared)
    existing_kind = required_delivery_kind(goal)
    if existing_kind == "game" and re.search(
        r"\b(?:game|engine|asset|emulator|rom|sprite|npc|world|level|quest)\b",
        goal.objective, re.I,
    ):
        return "game"
    if _CREATIVE_INTENT.search(goal.objective) and _CREATIVE_OUTPUT.search(goal.objective):
        return "creative"
    return existing_kind


def _digest_sources(sources: Mapping[str, str]) -> str:
    if not sources or any(
        not isinstance(path, str) or not path or path.startswith("/")
        or ".." in path.split("/") or not isinstance(content, str)
        for path, content in sources.items()
    ):
        raise FinalReviewError("final review requires nonempty safe text sources")
    return stable_fingerprint(dict(sources))


@dataclass(frozen=True, slots=True)
class MeasuredCriterion:
    """One independently sourced comparison and measurable objective threshold.

    Both measurements use the same declared unit/method and direction. The
    comparison never claims to be a complete industry ranking.
    """

    axis: str
    unit: str
    method: str
    direction: str
    observed: float
    baseline: float
    target: float
    observed_evidence: str
    baseline_evidence: str
    target_evidence: str
    sample_count: int
    baseline_sample_count: int
    regression_tolerance: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.axis, str) or not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", self.axis):
            raise FinalReviewError("invalid metric axis")
        if any(not isinstance(value, str) or not value.strip() for value in (
            self.unit, self.method, self.observed_evidence,
            self.baseline_evidence, self.target_evidence,
        )):
            raise FinalReviewError("comparison requires unit, method and evidence for all values")
        if self.direction not in {"higher", "lower"}:
            raise FinalReviewError("metric direction must be higher or lower")
        for number in (self.observed, self.baseline, self.target, self.regression_tolerance):
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
                raise FinalReviewError("comparative metrics must be finite numbers")
        if self.regression_tolerance < 0:
            raise FinalReviewError("negative regression tolerance")
        if any(type(number) is not int or number < 1 for number in (
            self.sample_count, self.baseline_sample_count,
        )):
            raise FinalReviewError("metrics require nonempty observed and baseline samples")

    @property
    def comparison_ok(self) -> bool:
        if self.direction == "higher":
            return self.observed + self.regression_tolerance >= self.baseline
        return self.observed <= self.baseline + self.regression_tolerance

    @property
    def objective_ok(self) -> bool:
        if self.direction == "higher":
            return self.observed >= self.target
        return self.observed <= self.target

    @property
    def improvement(self) -> float:
        return float(self.observed - self.baseline) * (1 if self.direction == "higher" else -1)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "axis": self.axis, "unit": self.unit, "method": self.method,
            "direction": self.direction, "observed": self.observed,
            "baseline": self.baseline, "target": self.target,
            "observed_evidence": self.observed_evidence,
            "baseline_evidence": self.baseline_evidence,
            "target_evidence": self.target_evidence,
            "samples": [self.sample_count, self.baseline_sample_count],
            "tolerance": self.regression_tolerance,
        })


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    """Explicit rights assertions; checker still independently validates them."""

    path: str
    content_digest: str
    origin: str
    rights_evidence: str
    permitted_use: bool
    license_condition_evidence: str = ""

    def __post_init__(self) -> None:
        if not self.path or self.path.startswith("/") or ".." in self.path.split("/"):
            raise FinalReviewError("invalid provenance path")
        if self.origin not in {
            "original", "user_authorized", "licensed", "public_domain", "unknown",
        }:
            raise FinalReviewError("unknown source-origin classification")
        if not _SHA_PATTERN.fullmatch(self.content_digest):
            raise FinalReviewError("provenance digest must be SHA-256")
        if not isinstance(self.permitted_use, bool) or not self.rights_evidence.strip():
            raise FinalReviewError("provenance lacks independently reviewable rights evidence")
        if self.origin == "licensed" and not self.license_condition_evidence.strip():
            raise FinalReviewError("licensed material requires condition/attribution evidence")

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "path": self.path, "content": self.content_digest,
            "origin": self.origin, "rights_evidence": self.rights_evidence,
            "permitted": self.permitted_use,
            "license_conditions": self.license_condition_evidence,
        })


@dataclass(frozen=True, slots=True)
class ContentReviewResult:
    """Exact-source independent verifier attestation with explicit scope.

    An empty list of findings is not itself an attestation. The callback must
    supply a real evidence reference, including the corpus/rights search scope.
    """

    stage: str
    source_digest: str
    checker: str
    evidence_ref: str
    review_scope: str
    covered_paths: tuple[str, ...]
    passed: bool
    findings: tuple[str, ...] = ()
    checked_dimensions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.stage not in {"copyright", "creative_rewrite"}:
            raise FinalReviewError("invalid final review stage")
        if not _SHA_PATTERN.fullmatch(self.source_digest):
            raise FinalReviewError("invalid reviewed source digest")
        if any(not isinstance(value, str) or not value.strip() for value in (
            self.checker, self.evidence_ref, self.review_scope,
        )):
            raise FinalReviewError("final checker lacks identity, evidence or scope")
        if not isinstance(self.passed, bool):
            raise FinalReviewError("final checker requires a typed verdict")
        if not isinstance(self.covered_paths, tuple) or len(set(self.covered_paths)) != len(self.covered_paths):
            raise FinalReviewError("final checker coverage is invalid")
        if any(not isinstance(path, str) or not path for path in self.covered_paths):
            raise FinalReviewError("invalid final checker path")
        if any(not isinstance(item, str) or not item.strip() for item in self.findings):
            raise FinalReviewError("invalid final checker findings")
        if self.passed and self.findings:
            raise FinalReviewError("final checker cannot pass with unresolved findings")
        if (
            not isinstance(self.checked_dimensions, tuple)
            or len(set(self.checked_dimensions)) != len(self.checked_dimensions)
            or any(
                not isinstance(item, str) or not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", item)
                for item in self.checked_dimensions
            )
        ):
            raise FinalReviewError("final checker dimensions are invalid")

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "stage": self.stage, "source": self.source_digest, "checker": self.checker,
            "evidence": self.evidence_ref, "scope": self.review_scope,
            "paths": self.covered_paths, "passed": self.passed,
            "findings": self.findings,
            "checked_dimensions": self.checked_dimensions,
        })


@dataclass(frozen=True, slots=True)
class FinalStageReceipt:
    sequence: int
    serial: str
    stage: str
    subject_digest: str
    previous: str
    digest: str

    @classmethod
    def create(cls, sequence: int, stage: str, subject_digest: str,
               previous: str) -> "FinalStageReceipt":
        serial = f"JVR-{sequence:06X}-P{sequence:06d}"
        digest = stable_fingerprint({
            "sequence": sequence, "serial": serial, "stage": stage,
            "subject_digest": subject_digest, "previous": previous,
        })
        return cls(sequence, serial, stage, subject_digest, previous, digest)


@dataclass(frozen=True, slots=True)
class FinalReleaseReview:
    kind: str
    source_digest: str
    upstream_quality_digest: str | None
    measurements: tuple[MeasuredCriterion, ...]
    provenance: tuple[SourceProvenance, ...]
    copyright: ContentReviewResult
    creative_rewrite: ContentReviewResult
    receipts: tuple[FinalStageReceipt, ...]
    passed: bool
    findings: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "kind": self.kind, "source": self.source_digest,
            "upstream": self.upstream_quality_digest,
            "metrics": [metric.fingerprint for metric in self.measurements],
            "provenance": [item.fingerprint for item in self.provenance],
            "copyright": self.copyright.fingerprint,
            "rewrite": self.creative_rewrite.fingerprint,
            "receipts": [receipt.digest for receipt in self.receipts],
            "passed": self.passed, "findings": self.findings,
        })


ContentChecker = Callable[
    [Mapping[str, str], tuple[SourceProvenance, ...]], ContentReviewResult,
]


def _review_findings(
    kind: str, sources: Mapping[str, str],
    metrics: Sequence[MeasuredCriterion], rights: Sequence[SourceProvenance],
    copyright: ContentReviewResult, rewrite: ContentReviewResult,
    upstream_quality_digest: str | None,
) -> tuple[str, ...]:
    expected_paths = set(sources)
    metric_axes = [m.axis for m in metrics]
    if not metrics or len(metric_axes) != len(set(metric_axes)):
        raise FinalReviewError("comparative and objective metrics must be unique and nonempty")
    required_axes = _CORE_AXES if kind in {"code", "game"} else ("originality", "coherence")
    missing = set(required_axes) - set(metric_axes)
    if missing:
        raise FinalReviewError("objective metrics absent: " + ", ".join(sorted(missing)))
    if kind in {"code", "game"} and not (
        isinstance(upstream_quality_digest, str) and _SHA_PATTERN.fullmatch(upstream_quality_digest)
    ):
        raise FinalReviewError("upstream source quality receipt is required")
    if set(item.path for item in rights) != expected_paths or len(rights) != len(expected_paths):
        raise FinalReviewError("copyright inventory does not cover every artifact")
    if any(item.content_digest != stable_fingerprint(sources[item.path]) for item in rights):
        raise FinalReviewError("copyright inventory contains stale source")
    source_digest = _digest_sources(sources)
    if copyright.checker == rewrite.checker or copyright.evidence_ref == rewrite.evidence_ref:
        raise FinalReviewError("copyright and creative rewrite require independent evidence and reviewers")
    for name, report in (("copyright", copyright), ("creative_rewrite", rewrite)):
        if report.passed:
            mandatory = (
                _RIGHTS_AXES if name == "copyright"
                else _REWRITE_AXES if kind in {"game", "creative"}
                else _REWRITE_AXES[:2]
            )
            if not set(mandatory).issubset(set(report.checked_dimensions)):
                raise FinalReviewError(f"{name} reviewer omitted mandatory scrutiny dimensions")
        if report.stage != name or report.source_digest != source_digest:
            raise FinalReviewError(f"{name} checker is stale or misidentified")
        if set(report.covered_paths) != expected_paths or len(report.covered_paths) != len(expected_paths):
            raise FinalReviewError(f"{name} checker did not inspect all source artifacts")
    failures = []
    for measurement in metrics:
        if not measurement.comparison_ok:
            failures.append(f"comparative:{measurement.axis}:regressed")
        if not measurement.objective_ok:
            failures.append(f"objective:{measurement.axis}:below_target")
    for item in rights:
        if item.origin == "unknown" or not item.permitted_use:
            failures.append(f"copyright:{item.path}:rights_unresolved")
    if not copyright.passed:
        failures.append("copyright:independent_review_failed")
        failures.extend(f"copyright:{issue}" for issue in copyright.findings)
    if not rewrite.passed:
        failures.append("creative_rewrite:independent_review_failed")
        failures.extend(f"creative_rewrite:{issue}" for issue in rewrite.findings)
    return tuple(failures)


def verify_final_release(
    result: FinalReleaseReview, sources: Mapping[str, str],
    *, upstream_quality_digest: str | None = None,
) -> None:
    if result.kind not in {"code", "game", "creative"}:
        raise FinalReviewError("invalid release domain")
    if result.source_digest != _digest_sources(sources):
        raise FinalReviewError("review no longer applies to current source")
    if result.upstream_quality_digest != upstream_quality_digest:
        raise FinalReviewError("previous quality review receipt changed")
    expected_failures = _review_findings(
        result.kind, sources, result.measurements, result.provenance,
        result.copyright, result.creative_rewrite, upstream_quality_digest,
    )
    if result.findings != expected_failures or result.passed != (not expected_failures):
        raise FinalReviewError("release verdict does not follow verified findings")
    if len(result.receipts) != len(_STAGES):
        raise FinalReviewError("all four release stages must be serialized")
    subject_digests = (
        stable_fingerprint([m.fingerprint for m in result.measurements if m.comparison_ok]),
        stable_fingerprint([m.fingerprint for m in result.measurements if m.objective_ok]),
        stable_fingerprint({
            "rights": [p.fingerprint for p in result.provenance],
            "copyright": result.copyright.fingerprint,
        }),
        result.creative_rewrite.fingerprint,
    )
    previous = "0" * 64
    for number, (stage, subject, given) in enumerate(
        zip(_STAGES, subject_digests, result.receipts), 1,
    ):
        expected = FinalStageReceipt.create(number, stage, subject, previous)
        if given != expected:
            raise FinalReviewError("release stage ordering or hash receipts corrupted")
        previous = expected.digest
    # Copyright and creative-rewrite validators must be the final two passes.
    if tuple(receipt.stage for receipt in result.receipts[-2:]) != (
        "copyright", "creative_rewrite",
    ):
        raise FinalReviewError("copyright and rewrite did not execute last")


class ComparativeObjectiveFinalReviewer:
    """Executes ordered checks without allowing output rewriting after the checks."""

    def inspect(
        self, kind: str, sources: Mapping[str, str], *,
        metrics: Sequence[MeasuredCriterion],
        provenance: Sequence[SourceProvenance],
        copyright_checker: ContentChecker,
        rewrite_checker: ContentChecker,
        upstream_quality_digest: str | None = None,
    ) -> FinalReleaseReview:
        if kind not in {"code", "game", "creative"}:
            raise FinalReviewError("invalid review kind")
        source = dict(sources)
        source_digest = _digest_sources(source)
        measured = tuple(metrics)
        inventory = tuple(provenance)
        if not callable(copyright_checker) or not callable(rewrite_checker):
            raise FinalReviewError("both final rights/originality verifiers are required")
        if copyright_checker is rewrite_checker:
            raise FinalReviewError("final verifiers must be separate host callbacks")
        # Perform deterministically checkable preliminary assessments *before*
        # calling the final two external analyzers.
        if not measured or len({m.axis for m in measured}) != len(measured):
            raise FinalReviewError("comparative assessment requires unique sourced metrics")
        required = _CORE_AXES if kind in {"code", "game"} else ("originality", "coherence")
        if not set(required).issubset({m.axis for m in measured}):
            raise FinalReviewError("missing objective coverage")
        if kind in {"code", "game"} and not (
            isinstance(upstream_quality_digest, str) and _SHA_PATTERN.fullmatch(upstream_quality_digest)
        ):
            raise FinalReviewError("mandatory upstream quality receipt missing")
        if len(inventory) != len(source) or {p.path for p in inventory} != set(source):
            raise FinalReviewError("rights provenance coverage incomplete")
        if any(p.content_digest != stable_fingerprint(source[p.path]) for p in inventory):
            raise FinalReviewError("rights provenance stale")
        # These two calls are deliberately last. Host callbacks must return
        # independently gathered legal/source comparison and rewrite evidence.
        copyright = copyright_checker(dict(source), inventory)
        if not isinstance(copyright, ContentReviewResult):
            raise FinalReviewError("copyright checker did not return typed evidence")
        rewrite = rewrite_checker(dict(source), inventory)
        if not isinstance(rewrite, ContentReviewResult):
            raise FinalReviewError("creative rewrite verifier did not return typed evidence")
        failures = _review_findings(
            kind, source, measured, inventory, copyright, rewrite,
            upstream_quality_digest,
        )
        subjects = (
            stable_fingerprint([m.fingerprint for m in measured if m.comparison_ok]),
            stable_fingerprint([m.fingerprint for m in measured if m.objective_ok]),
            stable_fingerprint({
                "rights": [p.fingerprint for p in inventory],
                "copyright": copyright.fingerprint,
            }),
            rewrite.fingerprint,
        )
        receipts: list[FinalStageReceipt] = []
        previous = "0" * 64
        for index, (stage, subject) in enumerate(zip(_STAGES, subjects), 1):
            receipt = FinalStageReceipt.create(index, stage, subject, previous)
            receipts.append(receipt)
            previous = receipt.digest
        review = FinalReleaseReview(
            kind=kind, source_digest=source_digest,
            upstream_quality_digest=upstream_quality_digest,
            measurements=measured, provenance=inventory,
            copyright=copyright, creative_rewrite=rewrite,
            receipts=tuple(receipts), passed=not failures, findings=failures,
        )
        verify_final_release(review, source, upstream_quality_digest=upstream_quality_digest)
        return review


class FinalReviewAdversary:
    """Try to bypass the release checker with stale rights and counterfeit scores."""

    @staticmethod
    def challenge(review: FinalReleaseReview, sources: Mapping[str, str],
                  *, upstream_quality_digest: str | None) -> str:
        verify_final_release(review, sources, upstream_quality_digest=upstream_quality_digest)
        if not review.passed:
            raise FinalReviewError("cannot attest a blocked final delivery")
        if not sources:
            raise FinalReviewError("missing reviewed sources")
        first = next(iter(sources))
        attacks = (
            ("removed_provenance", replace(review, provenance=review.provenance[1:]), sources),
            ("changed_source", review, {**sources, first: sources[first] + "\nnew unreviewed content"}),
            ("forged_copyright", replace(review, copyright=replace(
                review.copyright, source_digest="0" * 64,
            )), sources),
            ("lost_rewrite", replace(review, creative_rewrite=replace(
                review.creative_rewrite, passed=False,
            )), sources),
            ("tampered_objective", replace(review, measurements=(
                replace(review.measurements[0], observed=(
                    review.measurements[0].target - 1_000_000.0
                    if review.measurements[0].direction == "higher"
                    else review.measurements[0].target + 1_000_000.0
                )), *review.measurements[1:]
            )), sources),
            ("reordered_checks", replace(review, receipts=tuple(reversed(review.receipts))), sources),
            ("changed_upstream", replace(review, upstream_quality_digest="0" * 64), sources),
        )
        rejected = []
        for name, mutated, different_sources in attacks:
            try:
                verify_final_release(
                    mutated, different_sources,
                    upstream_quality_digest=upstream_quality_digest,
                )
            except (FinalReviewError, ValueError):
                rejected.append(name)
            else:
                raise FinalReviewError(f"final verifier accepted adversarial case {name}")
        return stable_fingerprint({
            "verifier": "final-review-adversary",
            "release": review.fingerprint,
            "rejected_mutations": rejected,
        })
