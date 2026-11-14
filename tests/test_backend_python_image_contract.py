"""Verify all backend Python image stages use one supported immutable base."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_backend_python_stages_are_supported_and_digest_pinned() -> None:
    dockerfile = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    matches = re.findall(
        r"^FROM (python:(\d+)\.(\d+)\.(\d+)-alpine\d+\.\d+@sha256:[0-9a-f]{64})"
        r" AS (builder|runtime-source|production)$",
        dockerfile,
        flags=re.MULTILINE,
    )
    assert len(matches) == 3, "all three backend Python stages must have immutable digests"
    assert {name for _, _, _, _, name in matches} == {
        "builder", "runtime-source", "production",
    }
    assert len({image for image, *_ in matches}) == 1, "backend stage ABI must be identical"
    major, minor = int(matches[0][1]), int(matches[0][2])
    assert (3, 10) <= (major, minor) < (3, 15), "backend deps reject Python 3.15+"
    assert "FROM production AS development" in dockerfile
    assert "RUN python -c 'import sys; assert (3, 10) <= sys.version_info[:2] < (3, 15)" in dockerfile
