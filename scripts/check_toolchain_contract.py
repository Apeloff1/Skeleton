#!/usr/bin/env python3
"""Verify runtime/toolchain versions stay aligned across repo surfaces.

This is intentionally dependency-free on Python 3.11+: stdlib TOML/JSON plus
small textual checks for workflow and Docker configuration. CI should fail when
package metadata, containers, or workflows drift to incompatible runtimes.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []

    backend_toml = tomllib.loads(read("backend/pyproject.toml"))
    project = backend_toml.get("project", {})
    ruff = backend_toml.get("tool", {}).get("ruff", {})
    mypy = backend_toml.get("tool", {}).get("mypy", {})
    dev = project.get("optional-dependencies", {}).get("dev", [])

    require(
        project.get("requires-python") == ">=3.11",
        "backend/pyproject.toml must require Python >=3.11",
        failures,
    )
    require(
        ruff.get("target-version") == "py311",
        "backend Ruff target-version must be py311",
        failures,
    )
    require(
        str(mypy.get("python_version")) == "3.11",
        "backend mypy python_version must be 3.11",
        failures,
    )
    require(
        any(re.fullmatch(r"ruff>=0\.9,<0\.10", item) for item in dev),
        "backend dev dependencies must constrain Ruff to 0.9.x",
        failures,
    )

    frontend = json.loads(read("frontend/package.json"))
    require(
        frontend.get("engines", {}).get("node") == ">=24",
        "frontend package engine must require Node >=24",
        failures,
    )
    for script in ("lint:ci", "typecheck", "export:web"):
        require(
            script in frontend.get("scripts", {}),
            f"frontend package.json missing canonical script {script}",
            failures,
        )

    frontend_docker = read("frontend/Dockerfile")
    require(
        re.search(r"^ARG NODE_VERSION=24$", frontend_docker, re.MULTILINE) is not None,
        "frontend Dockerfile must default NODE_VERSION to 24",
        failures,
    )

    ci = read(".github/workflows/ci.yml")
    require(
        re.search(r'^\s*NODE_VERSION:\s*"24"\s*$', ci, re.MULTILINE) is not None,
        "CI workflow NODE_VERSION must be 24",
        failures,
    )
    require(
        'python-version: "3.11"' in ci,
        "CI workflow must provision Python 3.11",
        failures,
    )
    require(
        "yarn lint:ci" in ci and "yarn typecheck" in ci and "yarn export:web" in ci,
        "CI frontend job must use canonical package scripts",
        failures,
    )

    backend_quality = read(".github/workflows/backend-quality.yml")
    require(
        'python-version: "3.11"' in backend_quality,
        "Backend Quality workflow must provision Python 3.11",
        failures,
    )
    require(
        '"ruff==0.9.*"' in backend_quality,
        "Backend Quality workflow must pin Ruff to 0.9.x",
        failures,
    )

    if failures:
        print("Toolchain contract violations:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("Toolchain contract passed: Python 3.11 / Ruff 0.9 / Node 24 aligned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
