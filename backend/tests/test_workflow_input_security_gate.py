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


def test_rejects_whole_inputs_object_transform(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo '${{ toJSON(inputs) }}'\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_rejects_whole_event_inputs_object_transform(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo '${{ toJSON(github.event.inputs) }}'\n",
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


def test_rejects_anchored_block_scalar_input_interpolation(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: &command >-\n          echo \"${{ inputs.payload }}\"\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_rejects_tagged_block_scalar_input_interpolation(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: !!str |\n          echo \"${{ github.event.inputs.payload }}\"\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_rejects_aliased_run_shell(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\nenv:\n  HIDDEN_RUN: &hidden_run \"echo '${{ inputs.payload }}'\"\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: *hidden_run\n",
    )
    assert any("aliased run shell is forbidden" in finding for finding in findings)


def test_allows_safe_anchored_block_scalar(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: &safe_command |\n          echo safe\n",
    )
    assert findings == []


def test_rejects_folded_input_expression_split_across_lines(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: >\n          echo \"${{\n            inputs.payload\n          }}\"\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_rejects_folded_event_input_expression_split_across_lines(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: >-\n          printf '%s\\n' '${{\n            github.event.inputs.payload\n          }}'\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_allows_folded_trusted_expression_split_across_lines(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: >\n          echo \"${{\n            github.repository\n          }}\"\n",
    )
    assert findings == []


def test_rejects_commented_block_scalar_header_bypass(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |2- # explicit indentation and chomp\n          printf '%s\\n' '${{ inputs.payload }}'\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_ignores_input_words_inside_expression_string_literals(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo \"${{ contains('inputs.payload', 'payload') }}\"\n",
    )
    assert findings == []


def test_ignores_escaped_quotes_inside_expression_string_literals(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo \"${{ contains('it''s inputs.payload', 'payload') }}\"\n",
    )
    assert findings == []


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
