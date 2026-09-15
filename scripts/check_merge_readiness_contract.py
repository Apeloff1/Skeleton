#!/usr/bin/env python3
"""Fail closed if the canonical merge-readiness workflow drifts from policy."""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/merge-readiness.yml"
PYTHON_VERSION = "3.11.16"
NODE_VERSION = "24.20.0"
RUFF_VERSION = "0.9.10"
GITLEAKS_PIN = "gitleaks/gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e"
REQUIRED_NEEDS = ("quarantine-policy", "unit", "integration-smoke", "quality-security")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    try:
        text = WORKFLOW.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SystemExit(f"merge-readiness contract: cannot read workflow: {exc}")

    require(
        re.search(
            r"^\s*cancel-in-progress:\s*\$\{\{\s*github\.event_name\s*==\s*'pull_request'\s*\}\}\s*$",
            text,
            re.MULTILINE,
        )
        is not None,
        "concurrency must cancel only superseded pull-request runs",
        failures,
    )
    require(
        re.search(
            r"group:\s*merge-readiness-\$\{\{\s*github\.event\.pull_request\.number\s*\|\|\s*github\.sha\s*\}\}",
            text,
        )
        is not None,
        "concurrency group must isolate pull requests by number and pushes by SHA",
        failures,
    )
    require(
        re.search(rf'^\s*PYTHON_VERSION:\s*"{re.escape(PYTHON_VERSION)}"\s*$', text, re.MULTILINE)
        is not None,
        f"Python must be pinned to {PYTHON_VERSION}",
        failures,
    )
    require(
        re.search(rf'^\s*NODE_VERSION:\s*"{re.escape(NODE_VERSION)}"\s*$', text, re.MULTILINE)
        is not None,
        f"Node must be pinned to {NODE_VERSION}",
        failures,
    )
    require(
        text.count('python-version: "${{ env.PYTHON_VERSION }}"') == 4,
        "all four Python setup sites must consume PYTHON_VERSION",
        failures,
    )
    require(
        'node-version: "${{ env.NODE_VERSION }}"' in text,
        "Node setup must consume NODE_VERSION",
        failures,
    )
    require(f'"ruff=={RUFF_VERSION}"' in text, f"Ruff must be pinned to {RUFF_VERSION}", failures)
    require("ruff==0.9.*" not in text, "wildcard Ruff execution is forbidden", failures)
    require("--frozen-lockfile --non-interactive" in text, "frontend install must be frozen and non-interactive", failures)
    require("python scripts/check_flaky_quarantine.py" in text, "quarantine policy checker must run", failures)
    require("bash scripts/quality-gates.sh" in text, "canonical quality/security gates must run", failures)
    require(GITLEAKS_PIN in text, "full-history Gitleaks action pin drifted", failures)
    require("continue-on-error: true" not in text, "required merge gates must not hide failures", failures)

    readiness_start = text.find("  readiness:")
    require(readiness_start >= 0, "readiness job missing", failures)
    readiness = text[readiness_start:] if readiness_start >= 0 else ""
    require("name: Merge Readiness" in readiness, "stable Merge Readiness job name missing", failures)
    require("if: ${{ always() }}" in readiness, "Merge Readiness must always emit a result", failures)
    require("toJSON(needs)" in readiness, "Merge Readiness must summarize prerequisite results", failures)
    require('result != "success"' in readiness, "Merge Readiness must fail on every non-success result", failures)
    for job in REQUIRED_NEEDS:
        require(re.search(rf"^\s+-\s+{re.escape(job)}\s*$", readiness, re.MULTILINE) is not None, f"Merge Readiness missing required dependency {job}", failures)

    require((ROOT / ".github/ci/flaky-quarantine.json").is_file(), "flaky quarantine registry missing", failures)
    require((ROOT / "scripts/check_flaky_quarantine.py").is_file(), "flaky quarantine checker missing", failures)

    if failures:
        print("Merge-readiness contract violations:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("Merge-readiness contract passed: stable aggregate, exact toolchain, PR-only cancellation, SHA-isolated main pushes, quarantine/security/secret gates, and fail-closed result aggregation are aligned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
