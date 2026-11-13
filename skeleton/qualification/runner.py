from __future__ import annotations

from typing import Callable, Iterable, Mapping

from .evidence import Evidence
from .gates import evaluate
from .schema import QualCase
from .verdict import CaseResult, Verdict


def run_case(case: QualCase, evidence: Evidence | None, head_sha: str,
             *, device_verifier: Callable[[Evidence], bool] | None = None) -> CaseResult:
    if evidence is None:
        why = "requires real hardware evidence" if case.requires_hardware else "no evidence recorded"
        return CaseResult(case.id, case.gate, Verdict.BLOCKED, (why,))
    if not evidence.bound_to(head_sha):
        return CaseResult(case.id, case.gate, Verdict.BLOCKED,
                          (f"evidence is for {evidence.head_sha[:12]}, not head {head_sha[:12]}",))
    if evidence.case_id != case.id:
        return CaseResult(case.id, case.gate, Verdict.BLOCKED,
                          ("evidence case identity mismatches requested gate",))
    if case.requires_hardware:
        if evidence.source != "device":
            return CaseResult(case.id, case.gate, Verdict.BLOCKED,
                              ("hardware case cannot be qualified from CI-sourced or manual evidence",))
        if device_verifier is None:
            return CaseResult(case.id, case.gate, Verdict.BLOCKED,
                              ("independent device attestation unavailable",))
        try:
            attested = device_verifier(evidence) is True
        except Exception:
            attested = False
        if not attested:
            return CaseResult(case.id, case.gate, Verdict.BLOCKED,
                              ("independent device attestation failed",))
    try:
        from .evidence import canonical_digest
        canonical_digest(evidence.data)
        reasons, metrics = evaluate(case.gate, case.params, evidence.data)
    except (ValueError, TypeError, KeyError, ArithmeticError, IndexError, RecursionError):
        return CaseResult(case.id, case.gate, Verdict.BLOCKED,
                          ("malformed or noncanonical evidence metrics",))
    verdict = Verdict.FAIL if reasons else Verdict.PASS
    return CaseResult(case.id, case.gate, verdict, tuple(reasons), metrics)


def run_cases(cases: Iterable[QualCase], evidence: Mapping[str, Evidence], head_sha: str,
              *, device_verifier: Callable[[Evidence], bool] | None = None) -> list[CaseResult]:
    return [run_case(c, evidence.get(c.id), head_sha,
                     device_verifier=device_verifier) for c in cases]
