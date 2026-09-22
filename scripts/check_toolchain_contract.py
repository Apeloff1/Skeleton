#!/usr/bin/env python3
"""Verify runtime/toolchain and canonical quality/security gates stay aligned."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
FULL_DEPLOY_NEEDS = "needs: [skeleton-test, java-accelerators, assembly-accelerators, school-jeeves-test, cockpit-smoke, backend-test, backend-import-smoke, frontend]"
PYTHON_VERSION = "3.11.16"
NODE_VERSION = "24.20.0"
UV_REQUIRED_VERSION = "==0.12.15"
RUFF_CI_VERSION = "0.9.10"
RUFF_DEV_REQUIREMENT = "ruff>=0.9,<0.17"

PROCESS_TESTS = (
    "test_process_safety_gate.py",
    "test_process_safety_destructuring.py",
    "test_process_safety_partial.py",
    "test_process_safety_namespace_get.py",
    "test_process_safety_getattribute.py",
    "test_process_safety_helper_aliases.py",
)
SECURITY_SCRIPTS = (
    "check_process_safety.py",
    "check_deserialization_safety.py",
    "check_sast_security.py",
    "check_js_process_alias_safety.py",
    "check_workflow_security.py",
    "check_secret_hygiene.py",
    "check_malware_iocs.py",
)
SECURITY_TESTS = (
    "test_exec_guard.py",
    *PROCESS_TESTS,
    "test_deserialization_safety_gate.py",
    "test_sast_security_gate.py",
    "test_js_process_alias_safety.py",
    "test_workflow_security_gate.py",
    "test_secret_hygiene_gate.py",
    "test_malware_ioc_gate.py",
)
SECURITY_HOOKS = (
    "backend-process-safety",
    "backend-deserialization-safety",
    "repository-sast-safety",
    "javascript-process-alias-safety",
    "workflow-security",
    "repository-secret-hygiene",
    "repository-malware-ioc",
    "backend-security-regressions",
)
DEPENDENCY_SECURITY_MARKERS = (
    '"pip-audit==2.10.1"',
    "--strict",
    "--format cyclonedx-json",
    "python-sbom.cdx.json",
    "Enforce Python vulnerability policy",
    "yarn audit --groups dependencies --level high --json",
    "anchore/sbom-action@3ad7283483fc7af8ff2b4ea19663c2d5ca935e26",
    "format: cyclonedx-json",
    "frontend-sbom.cdx.json",
    "Enforce JavaScript vulnerability policy",
)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(ok: bool, message: str, failures: list[str]) -> None:
    if not ok:
        failures.append(message)


def require_all(text: str, needles: tuple[str, ...], message: str, failures: list[str]) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        failures.append(f"{message}: missing {', '.join(missing)}")


def cancel_false(workflow: str) -> bool:
    return re.search(
        r"^\s*cancel-in-progress:\s*false\s*(?:#.*)?$",
        workflow,
        re.MULTILINE,
    ) is not None


def cancel_true(workflow: str) -> bool:
    return re.search(
        r"^\s*cancel-in-progress:\s*true\s*(?:#.*)?$",
        workflow,
        re.MULTILINE,
    ) is not None


def sha_scoped_cancellation(workflow: str) -> bool:
    """Return true when cancellation cannot cross commit SHA boundaries."""
    group = re.search(r"^\s*group:\s*(.+)$", workflow, re.MULTILINE)
    return bool(
        group
        and "${{ github.sha }}" in group.group(1)
        and cancel_true(workflow)
    )


def ref_scoped_cancellation(workflow: str) -> bool:
    """Return true when superseding cancellation is isolated to one PR/ref."""
    group = re.search(r"^\s*group:\s*(.+)$", workflow, re.MULTILINE)
    return bool(
        group
        and "${{ github.event.pull_request.number || github.ref }}" in group.group(1)
        and cancel_true(workflow)
    )


def pinned_action_count(workflow: str, action: str, generation: str) -> int:
    """Count immutable action pins carrying the expected human-readable generation."""
    pattern = re.compile(
        rf"{re.escape(action)}@[0-9a-fA-F]{{40}}\s+#\s*{re.escape(generation)}\b"
    )
    return len(pattern.findall(workflow))


def main() -> int:
    failures: list[str] = []

    root_project = tomllib.loads(read("pyproject.toml"))
    require(
        root_project.get("tool", {}).get("uv", {}).get("required-version")
        == UV_REQUIRED_VERSION,
        f"repository uv must be pinned to {UV_REQUIRED_VERSION}",
        failures,
    )

    backend = tomllib.loads(read("backend/pyproject.toml"))
    project = backend.get("project", {})
    tool = backend.get("tool", {})
    dev = project.get("optional-dependencies", {}).get("dev", [])
    uv_dev = backend.get("dependency-groups", {}).get("dev", [])
    test_deps = project.get("optional-dependencies", {}).get("test", [])
    runtime_deps = project.get("dependencies", [])
    requirements = read("backend/requirements.txt")
    pytest_cfg = tool.get("pytest", {}).get("ini_options", {})
    pytest_markers = pytest_cfg.get("markers", [])
    conftest = read("backend/tests/conftest.py")

    require(
        project.get("requires-python") == ">=3.11",
        "backend requires Python >=3.11",
        failures,
    )
    require(
        tool.get("ruff", {}).get("target-version") == "py311",
        "Ruff target must be py311",
        failures,
    )
    require(
        str(tool.get("mypy", {}).get("python_version")) == "3.11",
        "mypy target must be 3.11",
        failures,
    )
    require(
        RUFF_DEV_REQUIREMENT in dev,
        "backend dev Ruff compatibility range drifted",
        failures,
    )
    require(
        RUFF_DEV_REQUIREMENT in uv_dev,
        "uv dev Ruff compatibility range drifted",
        failures,
    )
    require(
        any(str(item).startswith("pytest-timeout>=") for item in dev)
        and any(str(item).startswith("pytest-timeout>=") for item in test_deps),
        "backend dev/test dependencies must include pytest-timeout",
        failures,
    )
    require(
        any(str(marker).startswith("timeout(") for marker in pytest_markers),
        "pytest strict-marker contract must register timeout(seconds)",
        failures,
    )
    require(
        "pytest_ignore_collect" in conftest
        and "EXPO_PUBLIC_BACKEND_URL" in conftest
        and "EXPO_BACKEND_URL" in conftest
        and "/app/frontend/.env" in conftest,
        "backend hermetic collection boundary for live Expo suites drifted",
        failures,
    )
    require(
        not any(
            str(item).lower().startswith("emergentintegrations")
            for item in runtime_deps
        ),
        "retired emergentintegrations SDK must not be a project dependency",
        failures,
    )
    require(
        re.search(
            r"^\s*emergentintegrations(?:[<>=!~].*)?$",
            requirements,
            re.MULTILINE | re.IGNORECASE,
        )
        is None,
        "retired emergentintegrations SDK must not be installed from requirements.txt",
        failures,
    )
    require(
        (ROOT / "backend/emergentintegrations/llm/chat.py").is_file(),
        "local emergentintegrations compatibility boundary missing",
        failures,
    )

    frontend = json.loads(read("frontend/package.json"))
    require(
        frontend.get("engines", {}).get("node") == ">=24",
        "frontend must require Node >=24",
        failures,
    )
    for script in ("lint:ci", "typecheck", "export:web"):
        require(
            script in frontend.get("scripts", {}),
            f"missing frontend script {script}",
            failures,
        )
    require(
        re.search(
            r"^ARG NODE_VERSION=24$",
            read("frontend/Dockerfile"),
            re.MULTILINE,
        )
        is not None,
        "frontend Docker Node must be 24",
        failures,
    )
    require(
        "ghcr.io/astral-sh/uv:latest" not in read("backend/Dockerfile"),
        "backend Docker must not use uv:latest",
        failures,
    )

    ci = read(".github/workflows/ci.yml")
    require(
        re.search(
            rf'^\s*PYTHON_VERSION:\s*"{re.escape(PYTHON_VERSION)}"\s*$',
            ci,
            re.MULTILINE,
        )
        is not None,
        f"CI Python must be pinned to {PYTHON_VERSION}",
        failures,
    )
    require(
        re.search(
            rf'^\s*NODE_VERSION:\s*"{re.escape(NODE_VERSION)}"\s*$',
            ci,
            re.MULTILINE,
        )
        is not None,
        f"CI Node must be pinned to {NODE_VERSION}",
        failures,
    )
    require(
        ci.count('python-version: "${{ env.PYTHON_VERSION }}"') >= 6,
        "CI Python jobs must consume the canonical pinned Python version",
        failures,
    )
    require(
        'node-version: "${{ env.NODE_VERSION }}"' in ci,
        "CI frontend must consume the canonical pinned Node version",
        failures,
    )
    require_all(
        ci,
        ("yarn lint:ci", "yarn typecheck", "yarn export:web"),
        "CI frontend scripts drifted",
        failures,
    )
    require(
        "python ../scripts/check_toolchain_contract.py" in ci,
        "CI backend lint must execute the repository toolchain contract",
        failures,
    )
    require(
        cancel_false(ci) or sha_scoped_cancellation(ci) or ref_scoped_cancellation(ci),
        "CI concurrency must preserve runs or scope cancellation to one commit/PR/ref",
        failures,
    )
    require(
        pinned_action_count(ci, "actions/checkout", "v7.0.1") > 0
        and pinned_action_count(ci, "actions/setup-python", "v7.0.0") > 0
        and pinned_action_count(ci, "actions/setup-node", "v7.0.0") > 0,
        "CI must use immutable proven core action generations",
        failures,
    )
    require(
        pinned_action_count(ci, "astral-sh/setup-uv", "v10.1.0") == 3,
        "CI must use exactly three immutable setup-uv v10.1.0 sites backed by the repository uv pin",
        failures,
    )
    ruff_command = f'uvx --from "ruff=={RUFF_CI_VERSION}" ruff check . --output-format=github'
    require(
        ci.count(ruff_command) == 1,
        f"CI backend lint must execute Ruff {RUFF_CI_VERSION} exactly once",
        failures,
    )
    require(
        "ruff==0.9.*" not in ci,
        "CI must not use wildcard Ruff execution",
        failures,
    )
    require(
        pinned_action_count(ci, "docker/setup-buildx-action", "v4.4.1") == 1,
        "Buildx version/count drifted",
        failures,
    )
    require(
        pinned_action_count(ci, "docker/build-push-action", "v7.4.0") == 3,
        "build-push version/count drifted",
        failures,
    )
    require(
        ci.count('"pydantic>=2.5,<3"') >= 3,
        "Skeleton/Jeeves/Cockpit CI jobs must install pydantic runtime slice",
        failures,
    )
    require(
        ci.count('"pydantic-settings>=2.1,<3"') >= 3,
        "Skeleton/Jeeves/Cockpit CI jobs must install pydantic-settings runtime slice",
        failures,
    )
    for required_job in (
        "skeleton-test",
        "school-jeeves-test",
        "cockpit-smoke",
        "backend-test",
        "backend-import-smoke",
        "frontend",
    ):
        require(f"  {required_job}:" in ci, f"CI job missing {required_job}", failures)
    require(
        FULL_DEPLOY_NEEDS in ci,
        "Docker publishing must fail closed on every critical test/smoke gate",
        failures,
    )

    # Frontend lint/type/export are canonical CI jobs now. A second standalone
    # lint workflow duplicates expensive work and used to amplify the Actions queue.
    require(
        not (ROOT / ".github/workflows/lint.yml").exists(),
        "legacy standalone lint workflow must stay retired; canonical CI owns frontend lint",
        failures,
    )

    backend_quality = read(".github/workflows/backend-quality.yml")
    require(
        f'python-version: "{PYTHON_VERSION}"' in backend_quality
        and f'"ruff=={RUFF_CI_VERSION}"' in backend_quality,
        f"Backend Quality must use Python {PYTHON_VERSION} and Ruff {RUFF_CI_VERSION}",
        failures,
    )
    require(
        "ruff==0.9.*" not in backend_quality,
        "Backend Quality must not use wildcard Ruff execution",
        failures,
    )
    require_all(
        backend_quality,
        SECURITY_SCRIPTS,
        "Backend Quality scanner coverage drifted",
        failures,
    )
    require_all(
        backend_quality,
        SECURITY_TESTS,
        "Backend Quality security regression coverage drifted",
        failures,
    )
    require(
        "--noconftest" in backend_quality
        and 'PYTEST_DISABLE_PLUGIN_AUTOLOAD: "1"' in backend_quality,
        "Backend Quality security isolation drifted",
        failures,
    )
    require(
        cancel_false(backend_quality)
        or sha_scoped_cancellation(backend_quality)
        or ref_scoped_cancellation(backend_quality),
        "Backend Quality concurrency must preserve runs or scope cancellation to one commit/PR/ref",
        failures,
    )

    dependency_security = read(".github/workflows/dependency-security.yml")
    require_all(
        dependency_security,
        DEPENDENCY_SECURITY_MARKERS,
        "dependency audit/SBOM contract drifted",
        failures,
    )
    require(
        cancel_true(dependency_security),
        "Dependency Security must cancel superseded same-ref dependency audits",
        failures,
    )
    require(
        "pip-audit" in dependency_security and "yarn audit" in dependency_security,
        "Dependency Security must audit both ecosystems",
        failures,
    )
    require(
        dependency_security.count("persist-credentials: false") >= 2,
        "Dependency Security checkouts must not persist credentials",
        failures,
    )
    require(
        "if: steps.python-audit.outputs.status != '0'" in dependency_security
        and "if: steps.yarn-audit.outputs.status != '0'" in dependency_security,
        "Dependency Security audits must fail closed after artifact capture",
        failures,
    )

    quality = read("scripts/quality-gates.sh")
    require_all(
        quality,
        SECURITY_SCRIPTS,
        "local scanner coverage drifted",
        failures,
    )
    require_all(
        quality,
        SECURITY_TESTS,
        "local security regression coverage drifted",
        failures,
    )
    require(
        "--noconftest" in quality and "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1" in quality,
        "local security isolation drifted",
        failures,
    )

    precommit = read(".pre-commit-config.yaml")
    require_all(
        precommit,
        SECURITY_SCRIPTS,
        "pre-commit scanner coverage drifted",
        failures,
    )
    require_all(
        precommit,
        SECURITY_TESTS,
        "pre-commit security regression coverage drifted",
        failures,
    )
    require_all(
        precommit,
        SECURITY_HOOKS,
        "pre-commit security hook coverage drifted",
        failures,
    )
    require(
        "repo-toolchain-contract" in precommit,
        "pre-commit toolchain self-enforcement missing",
        failures,
    )
    require(
        "dependency-security" in precommit,
        "pre-commit toolchain hook must watch dependency-security workflow",
        failures,
    )
    require(
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1" in precommit and "--noconftest" in precommit,
        "pre-commit security isolation drifted",
        failures,
    )
    require(
        "tests/test_process_safety.py" not in precommit,
        "superseded process test referenced",
        failures,
    )

    for script_name in SECURITY_SCRIPTS:
        require(
            (ROOT / "backend/scripts" / script_name).is_file(),
            f"security scanner missing: {script_name}",
            failures,
        )
    for test_name in SECURITY_TESTS:
        require(
            (ROOT / "backend/tests" / test_name).is_file(),
            f"security regression test missing: {test_name}",
            failures,
        )

    if failures:
        print("Toolchain contract violations:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(
        "Toolchain contract passed: immutable CI actions, runtime/tooling, hermetic test boundaries, "
        "canonical frontend validation, local/CI/pre-commit security parity, dependency audits/SBOMs, "
        "scoped workflow concurrency, regression isolation, self-enforcement, and fail-closed deployment gates aligned."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
