from __future__ import annotations

from typing import Iterable, Mapping

from .evidence import Evidence
from .gates import evaluate
from .schema import QualCase
from .verdict import CaseResult, Verdict


def run_case(case: QualCase, evidence: Evidence | None, head_sha: str) -> CaseResult:
    if evidence is None:
        why = "requires real hardware evidence" if case.requires_hardware else "no evidence recorded"
        return CaseResult(case.id, case.gate, Verdict.BLOCKED, (why,))
    if not evidence.bound_to(head_sha):
        return CaseResult(case.id, case.gate, Verdict.BLOCKED,
                          (f"evidence is for {evidence.head_sha[:12]}, not head {head_sha[:12]}",))
    if case.requires_hardware and evidence.source == "ci":
        return CaseResult(case.id, case.gate, Verdict.BLOCKED,
                          ("hardware case cannot be qualified from CI-sourced evidence",))
    reasons, metrics = evaluate(case.gate, case.params, evidence.data)
    verdict = Verdict.FAIL if reasons else Verdict.PASS
    return CaseResult(case.id, case.gate, verdict, tuple(reasons), metrics)


def run_cases(cases: Iterable[QualCase], evidence: Mapping[str, Evidence], head_sha: str) -> list[CaseResult]:
    return [run_case(c, evidence.get(c.id), head_sha) for c in cases]
