"""Forge verification adapter — accept/reject emitted project files.

Bridges the generic code rubric and the Godot project closure checker into
one forge-facing gate. The forge emits artefacts; this adapter decides
whether the emitted set is strong enough to accept.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from skeleton.forge.gdscript_check import check_files
from skeleton.intelligence.verifier import CodeVerifier


@dataclass(frozen=True)
class ForgeFileReport:
    path: str
    score: float
    issues: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "score": round(self.score, 4),
            "issues": list(self.issues),
        }


@dataclass(frozen=True)
class ForgeVerificationReport:
    accepted: bool
    score: float
    project_issues: Tuple[str, ...]
    blocking_issues: Tuple[str, ...]
    file_reports: Tuple[ForgeFileReport, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "score": round(self.score, 4),
            "project_issues": list(self.project_issues),
            "blocking_issues": list(self.blocking_issues),
            "file_reports": [r.to_dict() for r in self.file_reports],
        }


class ForgeVerifier:
    """Project-level verifier for emitted forge artefacts."""

    def __init__(self, *, accept_at: float = 0.7, gd_accept_at: float = 0.7) -> None:
        self.accept_at = accept_at
        self.gd_accept_at = gd_accept_at
        self.code = CodeVerifier(accept_at=accept_at)

    def verify(self, files: Mapping[str, str], *, request: str = "") -> ForgeVerificationReport:
        project_issues = tuple(check_files(files))
        file_reports = []
        blocking = list(project_issues)

        for path in sorted(files):
            if not path.endswith(".gd"):
                continue
            report = self.code.verify(files[path], request=request or path)
            file_reports.append(ForgeFileReport(path=path, score=report.score, issues=report.issues))
            if report.score < self.gd_accept_at:
                blocking.append(f"{path}: verifier score {report.score:.4f} below {self.gd_accept_at:.2f}")
            for issue in report.issues:
                if "unsafe" in issue or "unbalanced" in issue:
                    blocking.append(f"{path}: {issue}")

        avg = (sum(r.score for r in file_reports) / len(file_reports)) if file_reports else 1.0
        accepted = (not project_issues) and all(r.score >= self.gd_accept_at for r in file_reports) and avg >= self.accept_at
        return ForgeVerificationReport(
            accepted=accepted,
            score=avg,
            project_issues=project_issues,
            blocking_issues=tuple(blocking),
            file_reports=tuple(file_reports),
        )
