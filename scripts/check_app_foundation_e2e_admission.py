#!/usr/bin/env python3
"""Source-only guard against falsely successful App Foundation live E2E.

This is not an integration test, a security audit, or live readiness evidence.
It rejects wrong-source checkout and silent omission of mandatory Tier 2 work.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/app-foundation-e2e.yml"
SUITE = "frontend/scripts/test-app-foundation-flows.mjs"
EXACT_REF = "$" + "{{ github.event.pull_request.head.sha || github.sha }}"
OPERATOR_REQUIRED = 'test -n "' + "$" + '{SKELETON_E2E_OPERATOR_TOKEN_FILE:-}"'


def validate_text(workflow: str, suite: str) -> list[str]:
    if not (0 < len(workflow.encode("utf-8")) <= 100_000):
        return ["E2E workflow missing or exceeds bounded source budget"]
    if not (0 < len(suite.encode("utf-8")) <= 200_000):
        return ["E2E test suite missing or exceeds bounded source budget"]
    try:
        data = yaml.load(workflow, Loader=yaml.BaseLoader)
        steps = data["jobs"]["stack-e2e"]["steps"]
    except (yaml.YAMLError, TypeError, KeyError):
        return ["E2E source workflow is invalid"]
    if type(steps) is not list or any(type(step) is not dict for step in steps):
        return ["E2E source workflow contains malformed steps"]
    issues: list[str] = []

    def step(name: str) -> dict:
        matches = [item for item in steps if item.get("name") == name]
        if len(matches) != 1:
            issues.append("missing or duplicated step: " + name)
            return {}
        return matches[0]

    checkout = step("Checkout exact source")
    with_values = checkout.get("with")
    action = checkout.get("uses", "").split(" #", 1)[0]
    if not re.fullmatch(r"actions/checkout@[a-f0-9]{40}", action):
        issues.append("checkout action must be pinned to an immutable SHA")
    if (type(with_values) is not dict
            or with_values.get("ref") != EXACT_REF
            or with_values.get("persist-credentials") != "false"):
        issues.append("checkout must bind exact source SHA with credentials disabled")

    identity = step("Verify immutable exact tested source")
    if (identity.get("env", {}).get("EXPECTED_HEAD") != EXACT_REF
            or "set -euo pipefail" not in identity.get("run", "")
            or 'test "$(git rev-parse HEAD)" = "$EXPECTED_HEAD"' not in identity.get("run", "")):
        issues.append("no fail-closed exact-head checkout proof")

    credentials = step("Generate ephemeral stack credentials")
    credentials_run = credentials.get("run", "")
    if any(
        part not in credentials_run for part in (
            'operator_email="qa-e2e-operator-',
            'operator_password="$(gen)"',
            'GAMEFORGE_SEED_ADMIN_EMAIL=${operator_email}',
            'GAMEFORGE_SEED_ADMIN_PASSWORD=${operator_password}',
            '::add-mask::${operator_password}',
        )
    ):
        issues.append("isolated CI operator credentials are not minted and masked")

    proof = step("Test isolated operator provisioning contracts")
    if (
        "python -m unittest discover -s tests -p test_ci_e2e_operator_provision.py -q"
        not in proof.get("run", "")
        or str(proof.get("continue-on-error", "false")) == "true"
    ):
        issues.append("operator provisioning security regressions are not required")
    admission = step("Provision authenticated ephemeral E2E operator")
    if (
        admission.get("run", "").strip() != "python scripts/provision_e2e_operator.py"
        or str(admission.get("continue-on-error", "false")) == "true"
    ):
        issues.append("live operator must be authenticated by strict provisioning")
    cleanup = step("Remove ephemeral operator token")
    if (
        cleanup.get("if") != "always()"
        or 'rm -f -- "$SKELETON_E2E_OPERATOR_TOKEN_FILE"' not in cleanup.get("run", "")
    ):
        issues.append("ephemeral operator token must be removed on every exit")

    names = [item.get("name") for item in steps]
    sequence = (
        "Generate ephemeral stack credentials",
        "Test isolated operator provisioning contracts",
        "Provision authenticated ephemeral E2E operator",
        "Tier 2 live app-foundation flow (#4098)",
        "Remove ephemeral operator token",
    )
    if any(name not in names for name in sequence) or any(
        names.index(left) >= names.index(right)
        for left, right in zip(sequence, sequence[1:])
        if left in names and right in names
    ):
        issues.append("ephemeral operator bootstrap and cleanup order is invalid")

    live = step("Tier 2 live app-foundation flow (#4098)")
    env = live.get("env")
    if type(env) is not dict or env.get("SKELETON_E2E_REQUIRE_FULL_LIVE") != "1":
        issues.append("full-live E2E enforcement not enabled")
    shell = live.get("run", "")
    required = (
        "set -euo pipefail",
        'test -s "$suite"',
        OPERATOR_REQUIRED,
        'test -s "$SKELETON_E2E_OPERATOR_TOKEN_FILE"',
        'node --test --test-reporter=spec "$suite"',
    )
    if any(token not in shell for token in required):
        issues.append("missing suite or operator token may be treated as success")
    if ("exit 0" in shell or "|| true" in shell
            or str(live.get("continue-on-error", "false")) == "true"):
        issues.append("full-live step permits an evidence bypass")
    node_guards = (
        "process.env.SKELETON_E2E_REQUIRE_FULL_LIVE === '1'",
        "assert.ok(BASE, 'full live E2E requires SKELETON_E2E_BASE_URL')",
        "assert.ok(operatorToken, 'full live E2E requires authorized operator token')",
    )
    if any(token not in suite for token in node_guards):
        issues.append("Node Tier 2 lacks hard authorization/URL preconditions")
    return issues


def validate(root: Path = ROOT) -> list[str]:
    try:
        return validate_text(
            (root / WORKFLOW).read_text(encoding="utf-8"),
            (root / SUITE).read_text(encoding="utf-8"),
        )
    except (OSError, UnicodeError):
        return ["E2E source files are missing or unreadable"]


def main() -> int:
    issues = validate()
    for issue in issues:
        print("App Foundation E2E source admission:", issue)
    if issues:
        return 1
    print("App Foundation source admission passed; real live/device proof remains required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
