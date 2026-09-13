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
def read(path: str) -> str: return (ROOT / path).read_text(encoding="utf-8")
def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition: failures.append(message)
def workflow_cancel_in_progress_is_false(workflow: str) -> bool:
    return re.search(r"^\s*cancel-in-progress:\s*false\s*(?:#.*)?$", workflow, re.MULTILINE) is not None
def require_node24_actions(workflow: str, label: str, failures: list[str]) -> None:
    require(all(x not in workflow for x in ("actions/checkout@v4","actions/checkout@v5","actions/checkout@v6")), f"{label} must not use pre-v7 checkout actions", failures)
    require(all(x not in workflow for x in ("actions/setup-python@v5","actions/setup-python@v6")), f"{label} must not use pre-v7 setup-python actions", failures)
    require(all(x not in workflow for x in ("actions/setup-node@v4","actions/setup-node@v5","actions/setup-node@v6")), f"{label} must not use pre-v7 setup-node actions", failures)

def main() -> int:
    failures: list[str] = []
    backend_toml = tomllib.loads(read("backend/pyproject.toml")); project=backend_toml.get("project",{}); ruff=backend_toml.get("tool",{}).get("ruff",{}); mypy=backend_toml.get("tool",{}).get("mypy",{}); dev=project.get("optional-dependencies",{}).get("dev",[])
    require(project.get("requires-python")==">=3.11","backend/pyproject.toml must require Python >=3.11",failures)
    require(ruff.get("target-version")=="py311","backend Ruff target-version must be py311",failures)
    require(str(mypy.get("python_version"))=="3.11","backend mypy python_version must be 3.11",failures)
    require(any(re.fullmatch(r"ruff>=0\.9,<0\.10",x) for x in dev),"backend dev dependencies must constrain Ruff to 0.9.x",failures)
    frontend=json.loads(read("frontend/package.json")); require(frontend.get("engines",{}).get("node")==">=24","frontend package engine must require Node >=24",failures)
    for script in ("lint:ci","typecheck","export:web"): require(script in frontend.get("scripts",{}),f"frontend package.json missing canonical script {script}",failures)
    require(re.search(r"^ARG NODE_VERSION=24$",read("frontend/Dockerfile"),re.MULTILINE) is not None,"frontend Dockerfile must default NODE_VERSION to 24",failures)
    require("ghcr.io/astral-sh/uv:latest" not in read("backend/Dockerfile"),"backend Dockerfile must not consume floating uv:latest",failures)
    ci=read(".github/workflows/ci.yml")
    require(re.search(r'^\s*PYTHON_VERSION:\s*"3\.11"\s*$',ci,re.MULTILINE) is not None,"CI workflow PYTHON_VERSION must be 3.11",failures)
    require(re.search(r'^\s*NODE_VERSION:\s*"24"\s*$',ci,re.MULTILINE) is not None,"CI workflow NODE_VERSION must be 24",failures)
    require(ci.count('python-version: "${{ env.PYTHON_VERSION }}"')>=6,"All CI Python jobs must consume the canonical PYTHON_VERSION",failures)
    require('node-version: "${{ env.NODE_VERSION }}"' in ci,"CI frontend job must consume the canonical NODE_VERSION",failures)
    require(all(x in ci for x in ("yarn lint:ci","yarn typecheck","yarn export:web")),"CI frontend job must use canonical package scripts",failures)
    require("python ../scripts/check_toolchain_contract.py" in ci,"CI backend-lint job must enforce this toolchain contract",failures)
    require(workflow_cancel_in_progress_is_false(ci),"CI/CD must keep the active validation alive during rapid pushes",failures); require_node24_actions(ci,"CI/CD",failures)
    require("astral-sh/setup-uv@v10.1.0" in ci,"CI/CD must use setup-uv 10.1.0",failures); require('version: "latest-known"' in ci,"CI/CD setup-uv must use checksum-known uv releases",failures)
    require("docker/setup-buildx-action@v4.1.0" in ci,"CI/CD must use setup-buildx 4.1.0",failures); require(ci.count("docker/build-push-action@v7.2.0")==3,"CI/CD must use build-push 7.2.0 for all release images",failures)
    require(ci.count("${{ github.sha }}")>=3,"Every release image must publish an immutable commit-SHA tag",failures)
    require(ci.count("provenance: mode=max")==3,"Every release image must emit maximum BuildKit provenance",failures)
    require(ci.count("sbom: true")==3,"Every release image must emit an SBOM",failures)
    require(ci.count("org.opencontainers.image.revision=${{ github.sha }}")==3,"Every release image must carry its commit revision OCI label",failures)
    require("attestations: write" in ci and "id-token: write" in ci,"Docker release job must grant attestation identity permissions",failures)
    for scope in ("scope=root","scope=backend","scope=frontend"): require(ci.count(scope)>=2,f"Docker release cache must isolate {scope}",failures)
    for gate in ("skeleton-test","school-jeeves-test","cockpit-smoke","backend-test","backend-import-smoke","frontend"): require(re.search(rf"^\s*-\s*{re.escape(gate)}\s*$",ci,re.MULTILINE) is not None,f"Docker deployment must depend on {gate}",failures)
    bq=read(".github/workflows/backend-quality.yml"); require('python-version: "3.11"' in bq,"Backend Quality workflow must provision Python 3.11",failures); require('"ruff==0.9.*"' in bq,"Backend Quality workflow must pin Ruff to 0.9.x",failures); require(PROCESS_SAFETY_TEST in bq and "test_exec_guard.py" in bq,"Backend Quality must run both execution-boundary security tests",failures); require("--noconftest" in bq,"Focused Backend Quality security tests must isolate global conftest",failures); require('PYTEST_DISABLE_PLUGIN_AUTOLOAD: "1"' in bq,"Backend Quality must disable external pytest plugin autoload",failures); require(workflow_cancel_in_progress_is_false(bq),"Backend Quality must keep the active validation alive during rapid pushes",failures); require_node24_actions(bq,"Backend Quality",failures)
    lint=read(".github/workflows/lint.yml"); require(re.search(r"^\s*node-version:\s*24\s*$",lint,re.MULTILINE) is not None,"Lint workflow must provision Node 24",failures); require("yarn lint:ci" in lint,"Lint workflow must use the zero-warning canonical lint script",failures); require(workflow_cancel_in_progress_is_false(lint),"Lint must keep the active validation alive during rapid pushes",failures); require_node24_actions(lint,"Lint",failures)
    q=read("scripts/quality-gates.sh"); require(PROCESS_SAFETY_TEST in q and "test_exec_guard.py" in q,"Local quality gates must run canonical security regression tests",failures); require("--noconftest" in q,"Local focused security tests must isolate global conftest",failures)
    pc=read(".pre-commit-config.yaml"); require(PROCESS_SAFETY_TEST in pc and "test_exec_guard.py" in pc,"Pre-commit execution-boundary hook must use canonical security tests",failures); require("tests/test_process_safety.py" not in pc,"Pre-commit must not reference superseded process-safety test name",failures); require("repo-toolchain-contract" in pc,"Pre-commit must enforce repository toolchain contract",failures); require((ROOT/"backend/tests"/PROCESS_SAFETY_TEST).is_file(),f"Canonical process-safety test missing: {PROCESS_SAFETY_TEST}",failures)
    if failures:
        print("Toolchain contract violations:",file=sys.stderr)
        for failure in failures: print(f"  - {failure}",file=sys.stderr)
        return 1
    print("Toolchain contract passed: runtime, quality, security, immutable release, provenance, SBOM, and isolated container cache invariants aligned."); return 0
if __name__=="__main__": raise SystemExit(main())
