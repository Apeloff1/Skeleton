from __future__ import annotations

from pathlib import Path

from scripts.check_workflow_input_security import violations


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "workflow.yml"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_rejects_pull_request_title_in_run_shell(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: pull_request\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: printf '%s\\n' '${{ github.event.pull_request.title }}'\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_rejects_issue_comment_body_in_run_shell(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: issue_comment\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n          printf '%s\\n' '${{ github.event.comment.body }}'\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_rejects_whole_event_transform_in_run_shell(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: issues\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo '${{ toJSON(github.event) }}'\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_allows_event_payload_through_environment_boundary(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: pull_request\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - env:\n          PR_TITLE: ${{ github.event.pull_request.title }}\n        run: printf '%s\\n' \"$PR_TITLE\"\n",
    )
    assert findings == []


def test_ignores_event_words_inside_expression_string_literals(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo \"${{ contains('github.event.pull_request.title', 'title') }}\"\n",
    )
    assert findings == []
