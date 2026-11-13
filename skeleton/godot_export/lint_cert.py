"""Fold GDScript lint issues into certification results (GFL-01..04)."""
from __future__ import annotations

from collections import defaultdict

from .gdscript_lint import lint_project
from .project import GodotProject
from .report import CertificationReport

LINT_CASES = ("GFL-01", "GFL-02", "GFL-03", "GFL-04")


def certify(project: GodotProject) -> CertificationReport:
    rep = CertificationReport(f"{project.root}:lint")
    grouped: dict[str, list[dict]] = defaultdict(list)
    for issue in lint_project(project):
        grouped[issue.case_id].append({"path": issue.path, "line": issue.line, "msg": issue.message})
    for case in LINT_CASES:
        items = grouped.get(case, [])
        rep.add(case, not items, items[:20] or None)
    return rep
