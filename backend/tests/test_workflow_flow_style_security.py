from __future__ import annotations

from pathlib import Path

from scripts.check_workflow_security import violations


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "workflow.yml"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_rejects_single_line_flow_style_run(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - {run: 'echo ${{ inputs.payload }}', shell: bash}\n",
    )
    assert any("flow-style run step is forbidden" in finding for finding in findings)


def test_rejects_quoted_flow_style_run_key(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        'name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - {"run": "echo safe", shell: bash}\n',
    )
    assert any("flow-style run step is forbidden" in finding for finding in findings)


def test_rejects_multiline_flow_style_run(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - {name: unsafe,\n         run: echo safe,\n         shell: bash}\n",
    )
    assert any("flow-style run step is forbidden" in finding for finding in findings)


def test_allows_nested_run_input_on_flow_style_action(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - {uses: ./.github/actions/local, with: {run: safe}}\n",
    )
    assert findings == []
