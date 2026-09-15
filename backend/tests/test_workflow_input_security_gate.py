from __future__ import annotations

from pathlib import Path

from scripts.check_workflow_input_security import violations


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "workflow.yml"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_rejects_direct_inputs_interpolation_in_inline_run(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non:\n  workflow_dispatch:\n    inputs:\n      ref:\n        required: true\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: git checkout '${{ inputs.ref }}'\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_rejects_direct_event_inputs_interpolation_in_block_run(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non:\n  workflow_dispatch:\n    inputs:\n      payload:\n        required: true\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n          printf '%s\\n' '${{ github.event.inputs.payload }}'\n          echo done\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_rejects_bracket_notation_input_interpolation(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo \"${{ inputs['payload'] }}\"\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_rejects_single_quoted_run_key_bypass(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - 'run': echo \"${{ inputs.payload }}\"\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_rejects_double_quoted_run_key_bypass(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - \"run\": |\n          printf '%s\\n' '${{ github.event.inputs.payload }}'\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_rejects_indented_literal_block_scalar_bypass(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |2-\n          printf '%s\\n' '${{ inputs.payload }}'\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_rejects_chomped_folded_block_scalar_bypass(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: >+2\n          printf '%s\\n' '${{ github.event.inputs.payload }}'\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_allows_input_through_environment_boundary(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - env:\n          REQUESTED_REF: ${{ inputs.ref }}\n        run: printf '%s\\n' \"$REQUESTED_REF\"\n",
    )
    assert findings == []


def test_allows_trusted_expression_in_run(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo '${{ github.repository }}'\n",
    )
    assert findings == []
