"""Certification results and JSON / Markdown rendering."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .cases import Severity, get


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    detail: Any = None
    subject: str = ""

    @property
    def severity(self) -> Severity:
        return get(self.case_id).severity

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["sev"] = int(self.severity)
        d["title"] = get(self.case_id).title
        return d


@dataclass
class CertificationReport:
    subject: str
    results: list[CaseResult] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def add(self, case_id: str, passed: bool, detail: Any = None, subject: str = "") -> CaseResult:
        get(case_id)  # validate id
        r = CaseResult(case_id, passed, detail, subject)
        self.results.append(r)
        return r

    def extend(self, results: list[CaseResult]) -> None:
        for r in results:
            get(r.case_id)
            self.results.append(r)

    @property
    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed]

    @property
    def blocking(self) -> list[CaseResult]:
        return [r for r in self.failures if r.severity.blocking]

    @property
    def ship(self) -> bool:
        return bool(self.results) and not self.blocking

    def exit_code(self) -> int:
        return 0 if self.ship else 1

    def summary(self) -> dict[str, int]:
        out = {"total": len(self.results), "passed": 0, "failed": 0}
        for r in self.results:
            out["passed" if r.passed else "failed"] += 1
        for sev in Severity:
            out[f"sev{int(sev)}_failed"] = sum(1 for r in self.failures if r.severity == sev)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "ship": self.ship, "summary": self.summary(),
                "meta": self.meta, "results": [r.to_dict() for r in self.results]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=1, sort_keys=True, default=str)

    def to_markdown(self) -> str:
        lines = [f"# Godot certification: {self.subject}", "",
                 f"**Verdict:** {'SHIP' if self.ship else 'NO-SHIP'}", "",
                 "| Case | Sev | Result | Subject | Detail |", "|---|---|---|---|---|"]
        for r in self.results:
            detail = "" if r.detail is None else str(r.detail).replace("|", "\\|").replace("\n", " ")[:160]
            lines.append(f"| {r.case_id} | {int(r.severity)} | {'PASS' if r.passed else 'FAIL'} | {r.subject} | {detail} |")
        return "\n".join(lines) + "\n"


def merge(subject: str, reports: list[CertificationReport]) -> CertificationReport:
    out = CertificationReport(subject)
    for rep in reports:
        for r in rep.results:
            out.results.append(CaseResult(r.case_id, r.passed, r.detail, r.subject or rep.subject))
    return out
