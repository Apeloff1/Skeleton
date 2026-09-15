"""Fail-closed policy gate for the repository CodeQL security contract."""
from __future__ import annotations

from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / ".github" / "codeql" / "codeql-config.yml"
DEFAULT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "codeql.yml"

REQUIRED_LANGUAGES = ("python", "javascript-typescript")
REQUIRED_SOURCE_GLOBS = (
    "**/*.py",
    "**/*.pyi",
    "**/*.js",
    "**/*.jsx",
    "**/*.mjs",
    "**/*.cjs",
    "**/*.ts",
    "**/*.tsx",
)
REQUIRED_CONTROL_PATHS = (
    ".github/workflows/codeql.yml",
    ".github/codeql/**",
)


def _read(path: Path, label: str) -> tuple[str | None, list[str]]:
    try:
        if not path.is_file():
            return None, [f"{label}: required file is missing or not a regular file: {path}"]
        return path.read_text(encoding="utf-8"), []
    except (OSError, UnicodeError) as exc:
        return None, [f"{label}: read failure: {exc}"]


def _contains_scalar(text: str, value: str) -> bool:
    return re.search(
        rf"(?m)^\s*-\s*(?:uses\s*:\s*)?[\"']?{re.escape(value)}[\"']?\s*(?:#.*)?$",
        text,
    ) is not None


def violations(
    config_path: Path = DEFAULT_CONFIG,
    workflow_path: Path = DEFAULT_WORKFLOW,
) -> list[str]:
    findings: list[str] = []

    config_text, config_findings = _read(config_path, "CodeQL config")
    workflow_text, workflow_findings = _read(workflow_path, "CodeQL workflow")
    findings.extend(config_findings)
    findings.extend(workflow_findings)
    if config_text is None or workflow_text is None:
        return findings

    if not re.search(r"(?m)^\s*queries\s*:\s*(?:#.*)?$", config_text):
        findings.append("CodeQL config: queries mapping is required")
    if not _contains_scalar(config_text, "security-extended"):
        findings.append(
            "CodeQL config: security-extended query suite is required for high-confidence SAST"
        )

    for language in REQUIRED_LANGUAGES:
        if not re.search(
            rf"(?m)^\s*language\s*:\s*\[[^\]]*\b{re.escape(language)}\b[^\]]*\]\s*(?:#.*)?$",
            workflow_text,
        ) and not _contains_scalar(workflow_text, language):
            findings.append(f"CodeQL workflow: required language is missing: {language}")

    if not re.search(
        r"(?m)^\s*config-file\s*:\s*[\"']?\./\.github/codeql/codeql-config\.yml[\"']?\s*(?:#.*)?$",
        workflow_text,
    ):
        findings.append(
            "CodeQL workflow: init must load ./.github/codeql/codeql-config.yml"
        )

    for source_glob in REQUIRED_SOURCE_GLOBS:
        if source_glob not in workflow_text:
            findings.append(
                f"CodeQL workflow: source trigger coverage is missing: {source_glob}"
            )

    for control_path in REQUIRED_CONTROL_PATHS:
        if control_path not in workflow_text:
            findings.append(
                f"CodeQL workflow: security-control trigger coverage is missing: {control_path}"
            )

    for event in ("push", "pull_request", "schedule"):
        if not re.search(rf"(?m)^\s{{0,2}}{re.escape(event)}\s*:", workflow_text):
            findings.append(f"CodeQL workflow: required trigger is missing: {event}")

    return findings


def main() -> int:
    findings = violations()
    if findings:
        print("CodeQL security policy violations:", file=sys.stderr)
        for finding in findings:
            print(f" - {finding}", file=sys.stderr)
        return 1
    print("CodeQL security policy gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
