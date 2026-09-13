#!/usr/bin/env python3
"""Verify runtime/toolchain and canonical quality gates stay aligned."""
from __future__ import annotations
import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PROCESS_SAFETY_TEST = "test_process_safety_gate.py"
PROCESS_DESTRUCTURING_TEST = "test_process_safety_destructuring.py"
PROCESS_PARTIAL_TEST = "test_process_safety_partial.py"
FULL_DEPLOY_NEEDS = "needs: [skeleton-test, school-jeeves-test, cockpit-smoke, backend-test, backend-import-smoke, frontend]"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(ok: bool, message: str, failures: list[str]) -> None:
    if not ok:
        failures.append(message)


def cancel_false(workflow: str) -> bool:
    return re.search(r"^\s*cancel-in-progress:\s*false\s*(?:#.*)?$", workflow, re.MULTILINE) is not None


def main() -> int:
    failures: list[str] = []
    backend = tomllib.loads(read("backend/pyproject.toml"))
    project = backend.get("project", {})
    tool = backend.get("tool", {})
    dev = project.get("optional-dependencies", {}).get("dev", [])
    require(project.get("requires-python") == ">=3.11", "backend requires Python >=3.11", failures)
    require(tool.get("ruff", {}).get("target-version") == "py311", "Ruff target must be py311", failures)
    require(str(tool.get("mypy", {}).get("python_version")) == "3.11", "mypy target must be 3.11", failures)
    require(any(re.fullmatch(r"ruff>=0\.9,<0\.10", item) for item in dev), "dev Ruff must be 0.9.x", failures)

    frontend = json.loads(read("frontend/package.json"))
    require(frontend.get("engines", {}).get("node") == ">=24", "frontend must require Node >=24", failures)
    for script in ("lint:ci", "typecheck", "export:web"):
        require(script in frontend.get("scripts", {}), f"missing frontend script {script}", failures)
    require(re.search(r"^ARG NODE_VERSION=24$", read("frontend/Dockerfile"), re.MULTILINE) is not None, "frontend Docker Node must be 24", failures)
    require("ghcr.io/astral-sh/uv:latest" not in read("backend/Dockerfile"), "backend Docker must not use uv:latest", failures)

    ci = read(".github/workflows/ci.yml")
    require(re.search(r'^\s*PYTHON_VERSION:\s*"3\.11"\s*$', ci, re.MULTILINE) is not None, "CI Python must be 3.11", failures)
    require(re.search(r'^\s*NODE_VERSION:\s*"24"\s*$', ci, re.MULTILINE) is not None, "CI Node must be 24", failures)
    require(ci.count('python-version: "3.11"') >= 6, "CI Python jobs must provision Python 3.11", failures)
    require('node-version: "24"' in ci, "CI frontend must provision Node 24", failures)
    require(all(item in ci for item in ("yarn lint:ci", "yarn typecheck", "yarn export:web")), "CI frontend scripts drifted", failures)
    require("python ../scripts/check_toolchain_contract.py" in ci, "CI backend lint must execute the repository toolchain contract", failures)
    require(cancel_false(ci), "CI must keep active validation alive", failures)
    require("actions/checkout@v4" in ci and "actions/setup-python@v5" in ci and "actions/setup-node@v4" in ci, "CI must use proven core action generations", failures)
    require("astral-sh/setup-uv@v4" in ci, "CI uv setup drifted", failures)
    require("docker/setup-buildx-action@v3" in ci, "Buildx version drifted", failures)
    require(ci.count("docker/build-push-action@v5") == 3, "build-push version/count drifted", failures)
    for required_job in ("skeleton-test", "school-jeeves-test", "cockpit-smoke", "backend-test", "backend-import-smoke", "frontend"):
        require(f"  {required_job}:" in ci, f"CI job missing {required_job}", failures)
    require(FULL_DEPLOY_NEEDS in ci, "Docker publishing must fail closed on every critical test/smoke gate", failures)

    backend_quality = read(".github/workflows/backend-quality.yml")
    require('python-version: "3.11"' in backend_quality and '"ruff==0.9.*"' in backend_quality, "Backend Quality toolchain drifted", failures)
    require(
        PROCESS_SAFETY_TEST in backend_quality
        and PROCESS_DESTRUCTURING_TEST in backend_quality
        and PROCESS_PARTIAL_TEST in backend_quality
        and "test_exec_guard.py" in backend_quality
        and "--noconftest" in backend_quality
        and 'PYTEST_DISABLE_PLUGIN_AUTOLOAD: "1"' in backend_quality,
        "Backend Quality security isolation or regression coverage drifted",
        failures,
    )
    require(cancel_false(backend_quality), "Backend Quality concurrency drifted", failures)

    lint = read(".github/workflows/lint.yml")
    require(re.search(r"^\s*node-version:\s*24\s*$", lint, re.MULTILINE) is not None and "yarn lint:ci" in lint, "Lint toolchain drifted", failures)
    require(cancel_false(lint), "Lint concurrency drifted", failures)

    quality = read("scripts/quality-gates.sh")
    require(
        PROCESS_SAFETY_TEST in quality
        and PROCESS_DESTRUCTURING_TEST in quality
        and PROCESS_PARTIAL_TEST in quality
        and "test_exec_guard.py" in quality
        and "--noconftest" in quality,
        "local security gates drifted",
        failures,
    )
    precommit = read(".pre-commit-config.yaml")
    require(
        PROCESS_SAFETY_TEST in precommit
        and PROCESS_DESTRUCTURING_TEST in precommit
        and PROCESS_PARTIAL_TEST in precommit
        and "test_exec_guard.py" in precommit
        and "repo-toolchain-contract" in precommit,
        "pre-commit security/toolchain gates drifted",
        failures,
    )
    require("tests/test_process_safety.py" not in precommit, "superseded process test referenced", failures)
    require((ROOT / "backend/tests" / PROCESS_SAFETY_TEST).is_file(), "canonical process test missing", failures)
    require((ROOT / "backend/tests" / PROCESS_DESTRUCTURING_TEST).is_file(), "destructuring process-safety regression test missing", failures)
    require((ROOT / "backend/tests" / PROCESS_PARTIAL_TEST).is_file(), "partial process-safety regression test missing", failures)

    if failures:
        print("Toolchain contract violations:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("Toolchain contract passed: proven CI actions, runtime, quality, security, destructuring/partial coverage, self-enforcement, and fail-closed deployment gates aligned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
