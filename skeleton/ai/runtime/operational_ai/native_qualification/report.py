"""Immutable model/corpus/quality report with release hold explicit."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import hex64, identity, encode, sha256
from .contracts import ModelIdentity
from .metrics import aggregate
from .policy import Threshold
from .results import CaseResult
from .errors import deny

REPORT_SCHEMA = "skeleton.native-qualification.report.v1"


@dataclass(frozen=True, slots=True)
class QualificationReport:
    run_id: str
    model: ModelIdentity
    corpus_sha256: str
    cases: tuple[CaseResult, ...]
    started_utc: str
    finished_utc: str
    checkpoint_verified: bool
    real_native_execution: bool
    complete_corpus: bool
    threshold: Threshold

    def __post_init__(self) -> None:
        identity(self.run_id, "run")
        hex64(self.corpus_sha256, "corpus")
        if type(self.model) is not ModelIdentity:
            deny("report-model")
        if type(self.cases) is not tuple or len(self.cases) > 480:
            deny("report-cases")
        ids = [c.case_id for c in self.cases]
        if len(ids) != len(set(ids)):
            deny("report-duplicate-case")
        if type(self.threshold) is not Threshold:
            deny("report-policy")
        if not all(type(v) is bool for v in (
            self.checkpoint_verified, self.real_native_execution, self.complete_corpus
        )):
            deny("report-boolean")

    def record(self) -> dict:
        from .corpus import iter_cases, TOTAL_CASES
        # The report independently rechecks original source identities.  A
        # caller-set complete_corpus flag is not itself trustworthy evidence.
        source_expected = {c.case_id: c.content_sha256 for c in iter_cases()}
        source_seen = {c.case_id: c.source_sha256 for c in self.cases}
        original_corpus_proven = (
            self.complete_corpus and len(self.cases) == TOTAL_CASES
            and source_seen == source_expected
        )
        domains = aggregate(self.cases)
        checks = {
            "cases_total": len(self.cases),
            "cases_passed": sum(r.passed for r in self.cases),
            "failed_calls": sum(r.error_code is not None for r in self.cases),
            "critical_failed": sum(r.severity == "critical" and not r.passed for r in self.cases),
            "domain_summary": {k: v.record() for k, v in domains.items()},
        }
        qualified = bool(
            self.checkpoint_verified and self.real_native_execution and original_corpus_proven
            and self.cases and self.threshold.decide(
                total=len(self.cases), passed=checks["cases_passed"],
                failed_calls=checks["failed_calls"],
                critical_failed=checks["critical_failed"],
                domains={k: (v.passed, v.total) for k, v in domains.items()},
                evidence_complete=True,
            )
        )
        return {
            "schema": REPORT_SCHEMA, "run_id": self.run_id,
            "model": self.model.record(), "corpus_sha256": self.corpus_sha256,
            "started_utc": self.started_utc, "finished_utc": self.finished_utc,
            "checkpoint_verified": self.checkpoint_verified,
            "real_native_execution": self.real_native_execution,
            "complete_corpus": original_corpus_proven,
            "policy_threshold_met": qualified,
            "release_certified": False,
            "merge_certified": False,
            "hardware_qualified": False,
            "ci_qualified": False,
            "metrics": checks, "cases": [c.record() for c in self.cases],
        }

    @property
    def sha256(self) -> str:
        return sha256(encode(self.record()))
