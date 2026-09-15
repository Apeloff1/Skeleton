#!/usr/bin/env python3
"""Validate the production security runbook as an executable documentation contract."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "docs" / "PRODUCTION_SECURITY_RUNBOOK.md"

REQUIRED_HEADINGS = (
    "## 3. First 15 minutes",
    "## 4. Safe startup and configuration validation",
    "## 5. Suspected secret or credential exposure",
    "## 6. Rate-limit abuse or identity churn",
    "## 7. Trusted-proxy or ingress misconfiguration",
    "## 8. Dependency or supply-chain alert",
    "## 9. Suspected CI or workflow compromise",
    "## 10. Data/state corruption, backup, and restore",
    "## 11. Deployment rollback",
    "## 12. Required checks before recovery promotion",
    "## 13. Non-production drills",
    "## 14. Post-incident review",
)

REQUIRED_REFERENCES = (
    ".github/workflows/ci.yml",
    ".github/workflows/backend-quality.yml",
    ".github/workflows/dependency-security.yml",
    ".github/workflows/deployment-trust.yml",
    ".github/workflows/secret-scanning.yml",
    "backend/scripts/check_process_safety.py",
    "backend/scripts/check_deserialization_safety.py",
    "backend/scripts/check_sast_security.py",
    "backend/scripts/check_workflow_security.py",
    "backend/scripts/check_secret_hygiene.py",
)

REQUIRED_COMMANDS = (
    "python scripts/check_process_safety.py",
    "python scripts/check_deserialization_safety.py",
    "python scripts/check_sast_security.py",
    "python scripts/check_workflow_security.py",
    "python scripts/check_secret_hygiene.py",
)

MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b", re.IGNORECASE)


def _error(message: str) -> None:
    print(f"ops-runbook: {message}", file=sys.stderr)


def _normalized_repo_target(link: str) -> Path | None:
    if "://" in link or link.startswith("#") or link.startswith("mailto:"):
        return None

    target = (RUNBOOK.parent / link.split("#", 1)[0]).resolve()
    try:
        target.relative_to(REPO_ROOT)
    except ValueError:
        return None
    return target


def validate() -> list[str]:
    errors: list[str] = []
    if not RUNBOOK.is_file():
        return [f"missing {RUNBOOK.relative_to(REPO_ROOT)}"]

    text = RUNBOOK.read_text(encoding="utf-8")

    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"missing required heading: {heading}")

    placeholder = PLACEHOLDER.search(text)
    if placeholder:
        errors.append(f"placeholder token is not allowed: {placeholder.group(0)}")

    for command in REQUIRED_COMMANDS:
        if command not in text:
            errors.append(f"missing required local recovery check: {command}")

    linked_targets: set[str] = set()
    for link in MARKDOWN_LINK.findall(text):
        target = _normalized_repo_target(link)
        if target is None:
            continue
        if not target.exists():
            errors.append(f"broken repository-local link: {link}")
            continue
        linked_targets.add(target.relative_to(REPO_ROOT).as_posix())

    for reference in REQUIRED_REFERENCES:
        target = REPO_ROOT / reference
        if not target.exists():
            errors.append(f"required control path no longer exists: {reference}")
        if reference not in linked_targets:
            errors.append(f"runbook must link to control path: {reference}")

    if "Do not interpret cancellation, skipped jobs, missing required checks" not in text:
        errors.append("missing fail-closed CI-result guidance")

    if "known-good" not in text.lower():
        errors.append("missing known-good rollback/rebuild guidance")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            _error(error)
        return 1

    print("ops-runbook: contract OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
