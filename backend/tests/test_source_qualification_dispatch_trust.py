"""Regression tests for CodeQL alerts #801-#805: untrusted dispatch source."""
from __future__ import annotations

import pytest

from scripts.check_source_qualification_dispatch_trust import violations_from_text


BASE = """name: Trust test
on:
  workflow_dispatch:
permissions:
  contents: read
concurrency:
  group: trusted-${{ github.sha }}
jobs:
  offline-source:
    if: github.repository == 'Apeloff1/Skeleton' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Verify identity
        env:
          CANDIDATE_SHA: ${{ github.sha }}
        run: test -n "$CANDIDATE_SHA"
      - name: Checkout trusted commit
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          persist-credentials: false
          ref: ${{ github.sha }}
      - name: Compile
        run: python -m compileall -q skeleton
"""


def test_trusted_main_dispatch_contract_passes() -> None:
    assert violations_from_text("trusted.yml", BASE) == []


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (
            lambda source: source.replace(
                "  workflow_dispatch:",
                "  workflow_dispatch:\n    inputs:\n      candidate_sha:\n        required: true",
            ),
            "manual candidate inputs",
        ),
        (
            lambda source: source.replace(
                "ref: ${{ github.sha }}", "ref: ${{ inputs.candidate_sha }}"
            ),
            "checkout ref",
        ),
        (
            lambda source: source.replace(
                "ref: ${{ github.sha }}", "ref: ${{ github.event.inputs.sha }}"
            ),
            "checkout ref",
        ),
        (
            lambda source: source.replace(
                "ref: ${{ github.sha }}", "ref: ${{ github.ref }}"
            ),
            "checkout ref",
        ),
        (
            lambda source: source.replace(
                "ref: ${{ github.sha }}", "ref: refs/heads/main"
            ),
            "checkout ref",
        ),
        (
            lambda source: source.replace("          ref: ${{ github.sha }}\n", ""),
            "checkout ref",
        ),
        (
            lambda source: source.replace("persist-credentials: false", "persist-credentials: true"),
            "persist credentials",
        ),
        (
            lambda source: source.replace(
                "    if: github.repository == 'Apeloff1/Skeleton' && github.ref == 'refs/heads/main'\n", ""
            ),
            "default main branch",
        ),
        (
            lambda source: source.replace("  contents: read", "  contents: write"),
            "read-only",
        ),
        (
            lambda source: source.replace("group: trusted-${{ github.sha }}", "group: untrusted"),
            "concurrency",
        ),
        (
            lambda source: source.replace("CANDIDATE_SHA: ${{ github.sha }}", "CANDIDATE_SHA: ${{ inputs.candidate_sha }}"),
            "caller-controlled",
        ),
        (
            lambda source: source.replace("      - name: Compile", "      - name: Duplicate checkout\n        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n      - name: Compile"),
            "exactly one",
        ),
    ],
)
def test_rejects_dispatch_regression(change, expected: str) -> None:
    findings = violations_from_text("regressed.yml", change(BASE))
    assert any(expected in finding for finding in findings), findings
