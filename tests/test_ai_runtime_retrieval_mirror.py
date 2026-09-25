"""Canonical runtime and AI-runtime mirrors must not drift."""

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "relative",
    (
        "feedback.py",
        "freshness.py",
        "fusion.py",
        "index.py",
        "pipeline.py",
        "plane_weights.py",
        "quad.py",
        "receipts.py",
        "reranker_contract.py",
        "scope.py",
    ),
)
def test_retrieval_runtime_mirror_is_exact(relative: str) -> None:
    root = Path(__file__).resolve().parents[1]
    canonical = (root / "skeleton" / "retrieval" / relative).read_text(encoding="utf-8")
    mirror = (
        root / "skeleton" / "ai" / "runtime" / "retrieval" / relative
    ).read_text(encoding="utf-8")
    assert mirror == canonical, relative


@pytest.mark.parametrize("relative", ("rag.py", "cag.py", "mag.py"))
def test_scoped_memory_runtime_mirror_is_exact(relative: str) -> None:
    root = Path(__file__).resolve().parents[1]
    canonical = (root / "skeleton" / "memory" / relative).read_text(encoding="utf-8")
    mirror = (
        root / "skeleton" / "ai" / "runtime" / "memory" / relative
    ).read_text(encoding="utf-8")
    assert mirror == canonical, relative
