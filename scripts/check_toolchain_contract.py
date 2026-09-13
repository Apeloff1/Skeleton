#!/usr/bin/env python3
"""Verify runtime/toolchain and canonical quality gates stay aligned.

Dependency-free on Python 3.11+: stdlib TOML/JSON plus textual contract checks.
CI fails when package metadata, containers, workflows, or local quality gates
silently drift apart.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PROCESS_SAFETY_TEST = "test_process_safety_gate.py"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def workflow_cancel_in_progress_is_false(workflow: str) -> bool:
    return re.search(r"^\s*cancel-in-progress:\s*false\s*(?:#.*)?$", workflow, re.MULTILINE) is not None


def require_node24_actions(workflow: str, label: str, failures: list[str]) -> None:
    require("actions/checkout@v4" not in workflow and "actions/checkout@v5" not in workflow and "actions/checkout@v6" not in workflow, f"{label} must not use pre-v7 checkout actions", failures)
    require("actions/setup-python@v5" not in workflow and "actions/setup-python@v6" not in workflow, f"{label} must not use pre-v7 setup-python actions", failures)
    require("actions/setup-node@v4" not in workflow and "actions/setup-node@v5" not in workflow and "actions/setup-node@v6" not in workflow, f"{label} must not use pre-v7 setup-node actions", failures)


def main() -> int:
    failures: list[str] = []

    backend_toml = tomllib.loads(read("backend/pyproject.toml"))
    project = backend_toml.get("project", {})
    ruff = backend_toml.get("tool", {}).get("ruff", {})
    mypy = backend_toml.get("tool", {}).get("mypy", {})
    dev = project.get("optional-dependencies", {}).get("dev", [])
    require(project.get("requires-python") == ">=3.11", "backend/pyproject.toml must require Python >=3.11", failures)
    require(ruff.get("target-version") == "py311", "backend Ruff target-version must be py311", failures)
    require(str(mypy.get("python_version")) == "3.11", "backend mypy python_version must be 3.11", failures)
    require(any(re.fullmatch(r"ruff>=0\.9,<0\.10", item) for item in dev), "backend dev dependencies must constrain Ruff to 0.9.x", failures)

    frontend = json.loads(read("frontend/package.json"))
    require(frontend.get("engines", {}).get("node") == ">=24", "frontend package engine must require Node >=24", failures)
    for script in ("lint:ci", "typecheck", "export:web"):
        require(script in frontend.get("scripts", {}), f"frontend package.json missing canonical script {script}", failures)

    frontend_docker = read("frontend/Dockerfile")
    require(re.search(r"^ARG NODE_VERSION=24$", frontend_docker, re.MULTILINE) is not None, "frontend Dockerfile must default NODE_VERSION to 24", failures)

    backend_docker = read("backend/Dockerfile")
    require("ghcr.io/astral-sh/uv:latest" not in backend_docker, "backend Dockerfile must not consume floating uv:latest", failures)

    ci = read(".github/workflows/ci.yml")
    require(re.search(r'^\s*PYTHON_VERSION:\s*"3\.11"\s*$', ci, re.MULTILINE) is not None, "CI workflow PYTHON_VERSION must be 3.11", failures)
    require(re.search(r'^\s*NODE_VERSION:\s*"24"\s*$', ci, re.MULTILINE) is not None, "CI workflow NODE_VERSION must be 24", failures)
    require(ci.count('python-version: "${{ env.PYTHON_VERSION }}"') >= 6, "All CI Python jobs must consume the canonical PYTHON_VERSION", failures)
    require('node-version: "${{ env.NODE_VERSION }}"' in ci, "CI frontend job must consume the canonical NODE_VERSION", failures)
    require("yarn lint:ci" in ci and "yarn typecheck" in ci and "yarn export:web" in ci, "CI frontend job must use canonical package scripts", failures)
    require("python ../scripts/check_toolchain_contract.py" in ci, "CI backend-lint job must enforce this toolchain contract", failures)
    require(workflow_cancel_in_progress_is_false(ci), "CI/CD must keep the active validation alive during rapid pushes", failures)
    require_node24_actions(ci, "CI/CD", failures)
    require("astral-sh/setup-uv@v10.1.0" in ci, "CI/CD must use setup-uv 10.1.0", failures)
    require('version: "latest-known"' in ci, "CI/CD setup-uv must use checksum-known uv releases", failures)
    require("docker/setup-buildx-action@v4.1.0" in ci, "CI/CD must use setup-buildx 4.1.0", failures)
    require(ci.count("docker/build-push-action@v7.2.0") == 3, "CI/CD must use build-push 7.2.0 for all release images", failures)
    require(ci.count("${{ github.sha }}") >= 3, "Every release image must publish an immutable commit-SHA tag", failures)
    for deploy_gate in ("skeleton-test", "school-jeeves-test", "cockpit-smoke", "backend-test", "backend-import-smoke", "frontend"):
        require(re.search(rf"^\s*-\s*{re.escape(deploy_gate)}\s*$", ci, re.MULTILINE) is not None, f"Docker deployment must depend on {deploy_gate}", failures)

    backend_quality = read(".github/workflows/backend-quality.yml")
    require('python-version: "3.11"' in backend_quality, "Backend Quality workflow must provision Python 3.11", failures)
    require('"ruff==0.9.*"' in backend_quality, "Backend Quality workflow must pin Ruff to 0.9.x", failures)
    require(PROCESS_SAFETY_TEST in backend_quality and "test_exec_guard.py" in backend_quality, "Backend Quality must run both execution-boundary security tests", failures)
    require("--noconftest" in backend_quality, "Focused Backend Quality security tests must isolate global conftest", failures)
    require('PYTEST_DISABLE_PLUGIN_AUTOLOAD: "1"' in backend_quality, "Backend Quality must disable external pytest plugin autoload", failures)
    require(workflow_cancel_in_progress_is_false(backend_quality), "Backend Quality must keep the active validation alive during rapid pushes", failures)
    require_node24_actions(backend_quality, "Backend Quality", failures)

    lint = read(".github/workflows/lint.yml")
    require(re.search(r"^\s*node-version:\s*24\s*$", lint, re.MULTILINE) is not None, "Lint workflow must provision Node 24", failures)
    require("yarn lint:ci" in lint, "Lint workflow must use the zero-warning canonical lint script", failures)
    require(workflow_cancel_in_progress_is_false(lint), "Lint must keep the active validation alive during rapid pushes", failures)
    require_node24_actions(lint, "Lint", failures)

    quality_gates = read("scripts/quality-gates.sh")
    require(PROCESS_SAFETY_TEST in quality_gates and "test_exec_guard.py" in quality_gates, "Local quality gates must run the canonical security regression tests", failures)
    require("--noconftest" in quality_gates, "Local focused security tests must isolate global conftest", failures)

    precommit = read(".pre-commit-config.yaml")
    require(PROCESS_SAFETY_TEST in precommit and "test_exec_guard.py" in precommit, "Pre-commit execution-boundary hook must use canonical security tests", failures)
    require("tests/test_process_safety.py" not in precommit, "Pre-commit must not reference the superseded process-safety test name", failures)
    require("repo-toolchain-contract" in precommit, "Pre-commit must enforce the repository toolchain contract", failures)
    require((ROOT / "backend/tests" / PROCESS_SAFETY_TEST).is_file(), f"Canonical process-safety test missing: {PROCESS_SAFETY_TEST}", failures)

    if failures:
        print("Toolchain contract violations:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("Toolchain contract passed: Python 3.11 / Node 24, Ruff 0.9, modern actions, pinned container tooling, immutable release tags, security gates, deployment gates, and anti-starvation concurrency aligned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
