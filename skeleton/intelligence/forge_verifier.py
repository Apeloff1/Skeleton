"""Forge verification adapter — accept/reject emitted project files.

Bridges the generic code rubric and the Godot project closure checker into
one forge-facing gate. The forge emits artefacts; this adapter decides
whether the emitted set is strong enough to accept.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from skeleton.forge.gdscript_check import check_files
from skeleton.intelligence.verifier import CodeVerifier

_UNSAFE = re.compile(r"\b(eval|exec)\s*\(|except\s*:|os\.system|subprocess\.", re.M)


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
            report = self._verify_gdscript(path, files[path], request=request)
            file_reports.append(report)
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

    def _verify_gdscript(self, path: str, text: str, *, request: str = "") -> ForgeFileReport:
        base = self.code.verify(text, request=request or path)
        issues = list(base.issues)
        score = base.score

        has_extends = "extends " in text
        has_func = "func " in text
        has_class = "class_name " in text
        unsafe = bool(_UNSAFE.search(text))

        structure = 0.0
        if has_extends:
            structure += 0.35
        else:
            issues.append("missing extends")
        if has_func:
            structure += 0.45
        else:
            issues.append("no func definition")
        if has_class:
            structure += 0.20

        grounded = 1.0
        stem = path.rsplit("/", 1)[-1].replace(".gd", "")
        anchors = [p for p in re.split(r"[_\-]", stem) if len(p) >= 3]
        if anchors:
            hits = sum(1 for a in anchors if a.lower() in text.lower())
            grounded = hits / len(anchors)
            if grounded < 0.34:
                issues.append("file body weakly reflects its role")

        if path.endswith("player_controller.gd"):
            if "move_and_slide" not in text:
                issues.append("player controller never moves")
            if "HeatSystem" not in text:
                issues.append("player controller never talks to HeatSystem")
        elif path.endswith("heat_system.gd"):
            if "current_heat" not in text or "heat_critical" not in text:
                issues.append("heat system misses thermal flow")
        elif path.endswith("world_map.gd"):
            if "room" not in text.lower() and "door" not in text.lower():
                issues.append("world map misses room or door semantics")

        syntax = 1.0 if not any("unbalanced" in i for i in issues) else 0.0
        safety = 0.0 if unsafe else 1.0
        if unsafe and not any("unsafe" in i for i in issues):
            issues.append("unsafe constructs detected")

        lines = [l for l in text.splitlines() if l.strip()]
        size = 1.0 if 2 <= len(lines) <= 500 else (0.5 if lines else 0.0)
        score = round(0.25 * syntax + 0.25 * safety + 0.25 * structure + 0.15 * grounded + 0.10 * size, 4)
        return ForgeFileReport(path=path, score=score, issues=tuple(dict.fromkeys(issues)))
