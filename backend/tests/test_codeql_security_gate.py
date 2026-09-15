from __future__ import annotations

from pathlib import Path

from scripts.check_codeql_security import violations


CONFIG = """\
name: test
queries:
  - uses: security-extended
"""

WORKFLOW = """\
name: CodeQL
on:
  push:
    paths:
      - '**/*.py'
      - '**/*.pyi'
      - '**/*.js'
      - '**/*.jsx'
      - '**/*.mjs'
      - '**/*.cjs'
      - '**/*.ts'
      - '**/*.tsx'
      - '.github/workflows/codeql.yml'
      - '.github/codeql/**'
  pull_request:
    paths:
      - '**/*.py'
  schedule:
    - cron: "17 4 * * 1"
permissions: {}
jobs:
  analyze:
    strategy:
      matrix:
        language: [python, javascript-typescript]
    steps:
      - uses: github/codeql-action/init@1111111111111111111111111111111111111111
        with:
          languages: ${{ matrix.language }}
          config-file: ./.github/codeql/codeql-config.yml
"""


def _scan(tmp_path: Path, *, config: str = CONFIG, workflow: str = WORKFLOW) -> list[str]:
    config_path = tmp_path / "codeql-config.yml"
    workflow_path = tmp_path / "codeql.yml"
    config_path.write_text(config, encoding="utf-8")
    workflow_path.write_text(workflow, encoding="utf-8")
    return violations(config_path, workflow_path)


def test_accepts_complete_codeql_security_contract(tmp_path: Path) -> None:
    assert _scan(tmp_path) == []


def test_rejects_default_only_query_configuration(tmp_path: Path) -> None:
    findings = _scan(tmp_path, config="name: test\nqueries:\n  - uses: default\n")
    assert any("security-extended" in finding for finding in findings)


def test_rejects_missing_python_analysis(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        workflow=WORKFLOW.replace(
            "language: [python, javascript-typescript]",
            "language: [javascript-typescript]",
        ),
    )
    assert any("required language is missing: python" in finding for finding in findings)


def test_rejects_missing_javascript_typescript_analysis(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        workflow=WORKFLOW.replace(
            "language: [python, javascript-typescript]",
            "language: [python]",
        ),
    )
    assert any(
        "required language is missing: javascript-typescript" in finding
        for finding in findings
    )


def test_rejects_detached_codeql_config(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        workflow=WORKFLOW.replace(
            "config-file: ./.github/codeql/codeql-config.yml",
            "config-file: ./.github/codeql/weaker-config.yml",
        ),
    )
    assert any("init must load" in finding for finding in findings)


def test_rejects_source_trigger_regression(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        workflow=WORKFLOW.replace("      - '**/*.tsx'\n", ""),
    )
    assert any("source trigger coverage is missing: **/*.tsx" in finding for finding in findings)


def test_rejects_control_path_trigger_regression(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        workflow=WORKFLOW.replace("      - '.github/codeql/**'\n", ""),
    )
    assert any(
        "security-control trigger coverage is missing: .github/codeql/**" in finding
        for finding in findings
    )


def test_fails_closed_when_config_is_missing(tmp_path: Path) -> None:
    workflow_path = tmp_path / "codeql.yml"
    workflow_path.write_text(WORKFLOW, encoding="utf-8")
    findings = violations(tmp_path / "missing.yml", workflow_path)
    assert any("required file is missing" in finding for finding in findings)
