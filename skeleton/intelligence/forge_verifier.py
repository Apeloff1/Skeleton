"""Forge verification adapter — accept/reject emitted project files."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from skeleton.forge.gdscript_check import check_files
from skeleton.intelligence.quality import QualityIssue, QualityReport, QualitySignal
from skeleton.intelligence.verifier import CodeVerifier

_UNSAFE = re.compile(r"\b(eval|exec)\s*\(|except\s*:|os\.system|subprocess\.", re.M)


@dataclass(frozen=True)
class ForgeFileReport:
    path: str
    score: float
    issues: Tuple[str, ...]
    hard_issues: Tuple[str, ...] = ()
    soft_issues: Tuple[str, ...] = ()
    subscores: Dict[str, float] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "score": round(self.score, 4), "issues": list(self.issues), "hard_issues": list(self.hard_issues), "soft_issues": list(self.soft_issues), "subscores": {k: round(v, 4) for k, v in (self.subscores or {}).items()}}


@dataclass(frozen=True)
class ForgeVerificationReport:
    accepted: bool
    score: float
    reason: str
    project_issues: Tuple[str, ...]
    blocking_issues: Tuple[str, ...]
    weakest_path: str
    thresholds: Dict[str, float]
    summary: Dict[str, int]
    file_reports: Tuple[ForgeFileReport, ...]
    quality: QualityReport

    def to_dict(self) -> Dict[str, Any]:
        return {"accepted": self.accepted, "score": round(self.score, 4), "reason": self.reason, "project_issues": list(self.project_issues), "blocking_issues": list(self.blocking_issues), "weakest_path": self.weakest_path, "thresholds": {k: round(v, 4) for k, v in self.thresholds.items()}, "summary": dict(self.summary), "file_reports": [r.to_dict() for r in self.file_reports], "quality": self.quality.to_dict()}


class ForgeVerifier:
    def __init__(self, *, accept_at: float = 0.7, gd_accept_at: float = 0.7) -> None:
        self.accept_at = accept_at
        self.gd_accept_at = gd_accept_at
        self.code = CodeVerifier(accept_at=accept_at)
        self.runs = 0
        self.accepted = 0

    def verify(self, files: Mapping[str, str], *, request: str = "") -> ForgeVerificationReport:
        self.runs += 1
        project_issues = tuple(check_files(files))
        reports = []
        blocking = list(project_issues)
        for path in sorted(files):
            if not path.endswith(".gd"):
                continue
            report = self._verify_gdscript(path, files[path], request=request)
            reports.append(report)
            if report.score < self.gd_accept_at:
                blocking.append(f"{path}: verifier score {report.score:.4f} below {self.gd_accept_at:.2f}")
            for issue in report.hard_issues:
                blocking.append(f"{path}: {issue}")
        reports = tuple(sorted(reports, key=lambda r: (r.score, r.path)))
        avg = (sum(r.score for r in reports) / len(reports)) if reports else 1.0
        weakest = reports[0].path if reports else ""
        summary = {"files_checked": len(reports), "failed_files": sum(1 for r in reports if r.score < self.gd_accept_at), "warned_files": sum(1 for r in reports if r.soft_issues and r.score >= self.gd_accept_at), "passed_files": sum(1 for r in reports if r.score >= self.gd_accept_at and not r.soft_issues), "project_issues": len(project_issues), "blocking_issues": len(blocking)}
        accepted = (not project_issues) and all(r.score >= self.gd_accept_at for r in reports) and avg >= self.accept_at
        if accepted:
            self.accepted += 1
        reason = self._reason(project_issues, reports, avg)
        quality = self._quality_report(accepted=accepted, reason=reason, score=avg, weakest_path=weakest, project_issues=project_issues, reports=reports, summary=summary)
        return ForgeVerificationReport(accepted=accepted, score=avg, reason=reason, project_issues=project_issues, blocking_issues=tuple(blocking), weakest_path=weakest, thresholds={"project_accept_at": self.accept_at, "gdscript_accept_at": self.gd_accept_at}, summary=summary, file_reports=reports, quality=quality)

    def stats(self) -> Dict[str, Any]:
        return {"runs": self.runs, "accepted": self.accepted, "accept_rate": round(self.accepted / max(1, self.runs), 4)}

    def _reason(self, project_issues: Tuple[str, ...], reports: Tuple[ForgeFileReport, ...], avg: float) -> str:
        if project_issues:
            return "project_closure"
        if any(r.hard_issues for r in reports):
            return "unsafe_code"
        if any(r.score < self.gd_accept_at for r in reports) or avg < self.accept_at:
            return "low_score"
        return "accepted"

    def _quality_report(self, *, accepted: bool, reason: str, score: float, weakest_path: str, project_issues: Tuple[str, ...], reports: Tuple[ForgeFileReport, ...], summary: Dict[str, int]) -> QualityReport:
        issues = []
        for issue in project_issues:
            issues.append(QualityIssue(path="project.godot", message=issue, severity="hard"))
        for report in reports:
            for issue in report.hard_issues:
                issues.append(QualityIssue(path=report.path, message=issue, severity="hard"))
            for issue in report.soft_issues:
                issues.append(QualityIssue(path=report.path, message=issue, severity="soft"))
        signals = tuple(QualitySignal(path=r.path, score=r.score, subscores=dict(r.subscores or {})) for r in reports)
        return QualityReport(accepted=accepted, reason=reason, score=score, weakest_path=weakest_path, thresholds={"project_accept_at": self.accept_at, "gdscript_accept_at": self.gd_accept_at}, summary=summary, issues=tuple(issues), signals=signals, metadata={"kind": "forge", "files_checked": len(reports)})

    def _verify_gdscript(self, path: str, text: str, *, request: str = "") -> ForgeFileReport:
        base = self.code.verify(text, request=request or path)
        issues = list(base.issues)
        hard = []
        soft = []
        has_extends = "extends " in text
        has_func = "func " in text
        has_class = "class_name " in text
        unsafe = bool(_UNSAFE.search(text))
        structure = 0.0
        if has_extends:
            structure += 0.35
        else:
            soft.append("missing extends")
        if has_func:
            structure += 0.45
        else:
            soft.append("no func definition")
        if has_class:
            structure += 0.20
        grounded = 1.0
        stem = path.rsplit("/", 1)[-1].replace(".gd", "")
        anchors = [p for p in re.split(r"[_\-]", stem) if len(p) >= 3]
        if anchors:
            hits = sum(1 for a in anchors if a.lower() in text.lower())
            grounded = hits / len(anchors)
            if grounded < 0.34:
                soft.append("file body weakly reflects its role")
        if path.endswith("player_controller.gd"):
            if "move_and_slide" not in text:
                soft.append("player controller never moves")
            if "HeatSystem" not in text:
                soft.append("player controller never talks to HeatSystem")
        elif path.endswith("heat_system.gd"):
            if "current_heat" not in text or "heat_critical" not in text:
                soft.append("heat system misses thermal flow")
        elif path.endswith("world_map.gd"):
            if "room" not in text.lower() and "door" not in text.lower():
                soft.append("world map misses room or door semantics")
        syntax = 1.0 if not any("unbalanced" in i for i in base.issues) else 0.0
        safety = 0.0 if unsafe else 1.0
        if any("unbalanced" in i for i in base.issues):
            hard.append("unbalanced delimiters")
        if unsafe:
            hard.append("unsafe constructs detected")
        lines = [l for l in text.splitlines() if l.strip()]
        size = 1.0 if 2 <= len(lines) <= 500 else (0.5 if lines else 0.0)
        score = round(0.25 * syntax + 0.25 * safety + 0.25 * structure + 0.15 * grounded + 0.10 * size, 4)
        issues.extend(hard)
        issues.extend(soft)
        issues = tuple(dict.fromkeys(issues))
        return ForgeFileReport(path=path, score=score, issues=issues, hard_issues=tuple(dict.fromkeys(hard)), soft_issues=tuple(dict.fromkeys(soft)), subscores={"syntax": syntax, "safety": safety, "structure": structure, "grounding": grounded, "size": size})
