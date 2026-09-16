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
REQUIRED_NEEDS = ("quarantine_policy", "unit", "integration_smoke", "quality_security")
CONCURRENCY_GROUP = "group: merge-readiness-${{ github.event.pull_request.number || github.sha }}"
CANCEL_POLICY = "cancel-in-progress: ${{ github.event_name == 'pull_request' }}"
READINESS_GUARD = (
    "if: ${{ always() && (github.event_name != 'pull_request' || "
    "(!github.event.pull_request.draft && github.event.action != 'converted_to_draft' "
    "&& github.event.action != 'closed')) }}"
)
REPO_INTEL_CHECK = "python scripts/repo_intel.py check"
REPO_INTEL_SNAPSHOT = "python scripts/repo_intel.py snapshot --out .cache/repo-intel"
REPO_INTEL_GATE = 'python scripts/repo_intel.py gate --base "$REPO_INTEL_BASE"'
REPO_INTEL_BASE = "REPO_INTEL_BASE: ${{ github.event.pull_request.base.sha }}"
JOB_HEADER_RE = re.compile(r"^  (?P<name>[A-Za-z0-9_-]+):\s*$", re.MULTILINE)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def job_block(text: str, job_name: str) -> str:
    """Return one top-level workflow job block without leaking into later jobs."""
    target = re.search(rf"^  {re.escape(job_name)}:\s*$", text, re.MULTILINE)
    if target is None:
        return ""

    next_job = JOB_HEADER_RE.search(text, target.end())
    end = next_job.start() if next_job is not None else len(text)
    return text[target.start() : end]


def main() -> int:
    failures: list[str] = []
    try:
        text = WORKFLOW.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SystemExit(f"merge-readiness contract: cannot read workflow: {exc}")

    require("concurrency:" in text, "merge-readiness concurrency policy missing", failures)
    require(
        CONCURRENCY_GROUP in text,
        "merge-readiness concurrency must deduplicate PRs while preserving each main head SHA",
        failures,
    )
    require(
        CANCEL_POLICY in text,
        "only superseded pull-request merge-readiness runs may be cancelled",
        failures,
    )
    require(
        "cancel-in-progress: true" not in text,
        "unconditional merge-readiness cancellation can erase canonical main verification evidence",
        failures,
    )
    require(
        "github.event.pull_request.number || github.ref" not in text,
        "branch-ref merge-readiness grouping can starve main verification during rapid merges",
        failures,
    )
    require(
        re.search(r'^\s*PYTHON_VERSION:\s*"3\.11\.16"\s*$', text, re.MULTILINE) is not None,
        f"Python must be pinned to {PYTHON_VERSION}",
        failures,
    )
    require(
        re.search(r'^\s*NODE_VERSION:\s*"24\.20\.0"\s*$', text, re.MULTILINE) is not None,
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
    require('ports:\n          - "27017:27017"' in text, "Mongo service port must use explicit quoted list syntax", failures)

    quality_security = job_block(text, "quality_security")
    require(bool(quality_security), "quality_security job missing", failures)
    require(
        REPO_INTEL_CHECK in quality_security,
        "quality_security must validate the repository-intelligence contract",
        failures,
    )
    require(
        REPO_INTEL_SNAPSHOT in quality_security,
        "quality_security must materialize the current build/gap/security snapshot",
        failures,
    )
    require(
        REPO_INTEL_BASE in quality_security,
        "repo-intelligence PR gate must compare against the immutable pull-request base SHA",
        failures,
    )
    require(
        REPO_INTEL_GATE in quality_security,
        "quality_security must enforce augmentation notes for build-affecting pull requests",
        failures,
    )

    readiness = job_block(text, "readiness")
    require(bool(readiness), "readiness job missing", failures)
    require("name: Merge Readiness" in readiness, "stable Merge Readiness job name missing", failures)
    require(
        READINESS_GUARD in readiness,
        "Merge Readiness must aggregate active validation runs while preserving draft/close cancellation barriers",
        failures,
    )
    require('result != "success"' in readiness, "Merge Readiness must fail on every non-success result", failures)
    for job in REQUIRED_NEEDS:
        require(
            re.search(rf"^\s+-\s+{re.escape(job)}\s*$", readiness, re.MULTILINE) is not None,
            f"Merge Readiness missing required dependency {job}",
            failures,
        )
        require(
            f"needs.{job}.result" in readiness,
            f"Merge Readiness missing explicit result binding for {job}",
            failures,
        )

    require((ROOT / ".github/ci/flaky-quarantine.json").is_file(), "flaky quarantine registry missing", failures)
    require((ROOT / "scripts/check_flaky_quarantine.py").is_file(), "flaky quarantine checker missing", failures)
    require((ROOT / "scripts/repo_intel.py").is_file(), "repository intelligence scanner missing", failures)
    require((ROOT / "repo-intel/batches.json").is_file(), "100-batch repository intelligence plan missing", failures)
    require((ROOT / "repo-intel/game-capabilities.json").is_file(), "game-creation capability envelope missing", failures)

    if failures:
        print("Merge-readiness contract violations:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        "Merge-readiness contract passed: stable aggregate, exact toolchain, PR-safe supersession, "
        "non-cancelling main verification, repo-intelligence/augmentation-note enforcement, "
        "quarantine/security/secret gates, and explicit fail-closed result aggregation are aligned."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
