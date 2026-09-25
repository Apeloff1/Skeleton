"""Canonical retrieval runtime and AI runtime mirror must not drift."""

from pathlib import Path


def test_adaptive_retrieval_runtime_mirror_is_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in ("plane_weights.py", "feedback.py", "quad.py"):
        canonical = (root / "skeleton" / "retrieval" / relative).read_text(encoding="utf-8")
        mirror = (root / "skeleton" / "ai" / "runtime" / "retrieval" / relative).read_text(encoding="utf-8")
        assert mirror == canonical, relative
