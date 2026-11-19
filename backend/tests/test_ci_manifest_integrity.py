"""Guard focused CI suites against stale explicit test paths.

The focused workflows intentionally enumerate test files so they can install a small
runtime dependency set. A renamed/deleted test must not make pytest abort at CLI
parsing time with only the first missing path. This check reports every stale backend
test reference across the focused trust/convergence workflows before those suites run.
"""
from __future__ import annotations

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    REPO_ROOT / ".github" / "workflows" / "product-convergence.yml",
    REPO_ROOT / ".github" / "workflows" / "deployment-trust.yml",
)
_TEST_REF = re.compile(r"(?<![A-Za-z0-9_.-])(?:backend/)?tests/[A-Za-z0-9_./-]+\.py")


def _references(workflow: Path) -> set[str]:
    return set(_TEST_REF.findall(workflow.read_text(encoding="utf-8")))


def _resolve(reference: str) -> Path:
    if reference.startswith("backend/"):
        return REPO_ROOT / reference
    return REPO_ROOT / "backend" / reference


def test_explicit_backend_test_references_exist():
    missing: list[str] = []
    for workflow in WORKFLOWS:
        references = _references(workflow)
        assert references, f"{workflow.relative_to(REPO_ROOT)} contains no explicit backend test references"
        for reference in sorted(references):
            if not _resolve(reference).is_file():
                missing.append(f"{workflow.relative_to(REPO_ROOT)} -> {reference}")

    assert not missing, "missing workflow test references:\n" + "\n".join(missing)
