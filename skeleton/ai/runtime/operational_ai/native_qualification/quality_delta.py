"""Head-to-head qualified evidence comparison, no auto model promotion."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import hex64
from .errors import deny

@dataclass(frozen=True, slots=True)
class QualityDelta:
    baseline_sha256: str
    candidate_sha256: str
    improved: int
    regressed: int
    unchanged: int
    incomplete: int
    promotion_allowed: bool = False

    def record(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


def compare(
    baseline: dict, candidate: dict,
    *, baseline_sha256: str, candidate_sha256: str,
) -> QualityDelta:
    hex64(baseline_sha256)
    hex64(candidate_sha256)
    for report in (baseline, candidate):
        if report.get("schema") != "skeleton.native-qualification.report.v1":
            deny("comparison-schema")
        if report.get("complete_corpus") is not True:
            deny("comparison-partial")
        if report.get("real_native_execution") is not True:
            deny("comparison-not-real")
        if report.get("corpus_sha256") != baseline.get("corpus_sha256"):
            deny("comparison-corpus-drift")
    b = {x["case_id"]: x["passed"] for x in baseline["cases"]}
    c = {x["case_id"]: x["passed"] for x in candidate["cases"]}
    if set(b) != set(c):
        deny("comparison-case-inventory")
    improved = sum(not b[key] and c[key] for key in b)
    regressed = sum(b[key] and not c[key] for key in b)
    unchanged = sum(b[key] == c[key] for key in b)
    return QualityDelta(
        baseline_sha256, candidate_sha256, improved, regressed,
        unchanged, 0, False,
    )
