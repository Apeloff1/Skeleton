from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_workflow_secret_output.py"
spec = importlib.util.spec_from_file_location("workflow_secret_output", MODULE_PATH)
assert spec is not None and spec.loader is not None
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


@pytest.mark.parametrize(
    "command",
    [
        "echo '${{ secrets.API_TOKEN }}'",
        'printf "%s\\n" "$API_TOKEN"',
        "printenv DB_PASSWORD",
        "printenv -0",
        "env",
        "env -0",
        "set",
        "export -p",
        "declare -x",
        "typeset -xp",
        "set -x",
        "set -euxo pipefail",
        "bash -x ./script.sh",
        'cat <<< "$WEBHOOK_SECRET"',
        'Write-Host $env:API_TOKEN',
        'Write-Output "${{ secrets.SIGNING_KEY }}"',
        "Get-ChildItem Env:",
        "gci Env:",
    ],
)
def test_dangerous_output_commands_are_rejected(command: str) -> None:
    assert scanner.command_violation(command)


@pytest.mark.parametrize(
    "command",
    [
        'curl -H "Authorization: Bearer $API_TOKEN" https://example.test',
        'echo "$BUILD_ID"',
        'printf "%s\\n" "$GITHUB_SHA"',
        "env MODE=ci python -m pytest",
        "set -euo pipefail",
        "tee report.txt < result.txt",
        "cat report.txt",
        "export MODE=ci",
        "Write-Host $env:GITHUB_SHA",
    ],
)
def test_secret_consumption_and_benign_output_remain_allowed(command: str) -> None:
    assert scanner.command_violation(command) is None


def test_inline_run_is_scanned() -> None:
    text = "steps:\n  - run: echo '${{ secrets.DEPLOY_KEY }}'\n"
    assert scanner.workflow_violations_text(text) == [
        "line 2: workflow output command exposes GitHub secret context"
    ]


def test_block_run_is_scanned_and_stops_at_next_step() -> None:
    text = """steps:
  - run: |
      echo "$BUILD_ID"
      printf '%s\\n' "$SIGNING_KEY"
  - name: next
    run: true
"""
    assert scanner.workflow_violations_text(text) == [
        "line 4: workflow output command exposes secret-like variable SIGNING_KEY"
    ]


def test_powershell_pipeline_secret_is_scanned() -> None:
    text = """steps:
  - shell: pwsh
    run: |
      $env:API_TOKEN | Write-Host
"""
    assert scanner.workflow_violations_text(text) == [
        "line 4: workflow output command exposes secret-like variable API_TOKEN"
    ]


def test_comments_are_not_treated_as_commands() -> None:
    text = """steps:
  - run: |
      # echo "$API_TOKEN"
      echo done
"""
    assert scanner.workflow_violations_text(text) == []


def test_empty_workflow_root_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(scanner.WorkflowSecretOutputScanError, match="no workflow"):
        list(scanner.workflow_files(tmp_path))


def test_workflow_root_symlink_fails_closed(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "workflows"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(scanner.WorkflowSecretOutputScanError, match="symlink"):
        list(scanner.workflow_files(link))
