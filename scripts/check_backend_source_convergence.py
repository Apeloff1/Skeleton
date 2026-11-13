#!/usr/bin/env python3
"""Fail-closed contract for the review-only exact-head backend regression lane.

Source qualification does not certify live deployments, native device behavior,
the entire backend quality job, merge readiness or release.
"""
from __future__ import annotations

from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/backend-quality.yml"
REF = "$" + "{{ github.event.pull_request.head.sha || github.sha }}"
TESTS = (
    "backend/tests/test_live_service_test_boundaries.py",
    "backend/tests/test_queue_drain_workflow.py",
    "backend/tests/test_workflow_concurrency_gate.py",
    "backend/tests/test_free_api_dns_pin.py",
    "backend/tests/test_galaxy_file_budget.py",
    "backend/tests/test_storage_lazy_registry.py",
    "backend/tests/test_discourse_judge_admission.py",
    "backend/tests/test_code_intelligence_engine_boundary.py",
    "backend/tests/test_engine_text_route_cutovers.py",
)

def validate_text(source: str) -> list[str]:
    """Reject missing/elevated/silent-skipped qualification by exact source."""
    if not 0 < len(source.encode("utf-8")) <= 200_000:
        return ["backend source workflow missing or oversized"]
    try:
        payload = yaml.load(source, Loader=yaml.BaseLoader)
        if type(payload) is not dict or type(payload.get("jobs")) is not dict:
            return ["backend workflow not a jobs mapping"]
        job = payload["jobs"]["backend_source_convergence"]
    except (yaml.YAMLError, KeyError, TypeError):
        return ["backend source convergence job missing or invalid YAML"]
    errors: list[str] = []
    if type(job) is not dict:
        return ["backend qualification is not a job mapping"]
    if job.get("if") != (
        "github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch'"
    ):
        errors.append("review-only source lane must execute on draft PRs")
    if not 1 <= int(job.get("timeout-minutes", "0") or 0) <= 30:
        errors.append("unbounded backend source runner")
    if job.get("permissions") != {"contents": "read"}:
        errors.append("backend source admission must use read-only token")
    env = job.get("env")
    if type(env) is not dict or env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") != "1":
        errors.append("pytest plugin autoload must remain disabled")
    steps = job.get("steps")
    if type(steps) is not list or any(type(s) is not dict for s in steps):
        return errors + ["backend qualification steps invalid"]
    names = [s.get("name") for s in steps]
    if len(set(names)) != len(names):
        errors.append("duplicate backend source step names")

    def named(name: str) -> dict:
        matches = [s for s in steps if s.get("name") == name]
        if len(matches) != 1:
            errors.append("missing or duplicate backend step: " + name)
            return {}
        return matches[0]

    checkout = named("Checkout immutable backend source without credentials")
    if not re.fullmatch(r"actions/checkout@[0-9a-f]{40}",
                        checkout.get("uses", "").split(" #", 1)[0]):
        errors.append("backend checkout not action-SHA pinned")
    options = checkout.get("with")
    if (type(options) is not dict or options.get("persist-credentials") != "false"
            or options.get("ref") != REF):
        errors.append("backend checkout not immutable head with no credentials")
    identity = named("Prove exact test source revision")
    if (identity.get("env", {}).get("EXPECTED_HEAD") != REF
            or 'test "$(git rev-parse HEAD)" = "$EXPECTED_HEAD"'
            not in identity.get("run", "")):
        errors.append("backend source identity not checked fail-closed")
    install = named("Install reviewed isolated backend test dependencies")
    deps = install.get("run", "")
    for package in ("pytest-asyncio", "PyJWT==2.15.1",
                    "zstandard==0.25.0", "PyYAML"):
        if package not in deps:
            errors.append(f"missing reviewed backend test import: {package}")
    boundary = named("Verify explicit live-service boundary (not a live service test)")
    if ("python backend/scripts/check_live_service_test_boundaries.py"
            not in boundary.get("run", "")):
        errors.append("live-service manifest boundary is not checked")
    run = named("Exercise true backend source, replay and security regressions")
    cmd = run.get("run", "")
    for token in ("-p pytest_asyncio.plugin", "--noconftest", "--import-mode=importlib",
                  *TESTS):
        if token not in cmd:
            errors.append("backend qualification drops required source test: " + token)
    for step in steps:
        shell = step.get("run", "")
        if "continue-on-error" in step or "|| true" in shell or "exit 0" in shell:
            errors.append("backend source step bypasses failure: " + str(step.get("name")))
    if "ruff" not in payload["jobs"]:
        errors.append("canonical Backend Quality ruff job removed")
    return errors

def validate(root: Path = ROOT) -> list[str]:
    try:
        source = (root / WORKFLOW).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ["backend workflow not readable"]
    return validate_text(source)

def main() -> int:
    findings = validate()
    for finding in findings:
        print("Backend source convergence contract:", finding)
    if findings:
        return 1
    print("Backend source convergence contract passed (source-only; full CI held)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
