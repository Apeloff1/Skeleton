from __future__ import annotations

from pathlib import Path

from scripts.check_workflow_security import violations


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "workflow.yml"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_rejects_pr_title_through_quoted_run_key(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        'name: test\non: [pull_request]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - "run": echo "${{ github.event.pull_request.title }}"\n',
    )
    assert any("direct pull request title/body interpolation" in finding for finding in findings)


def test_rejects_folded_multiline_comment_expression(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [issue_comment]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - run: >\n          echo \"${{\n            github.event.comment.body\n          }}\"\n",
    )
    assert any("direct issue comment body interpolation" in finding for finding in findings)


def test_rejects_head_ref_through_anchored_run_block(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [pull_request]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - run: &unsafe >-\n          printf '%s\\n' '${{ github.head_ref }}'\n",
    )
    assert any("direct head ref interpolation" in finding for finding in findings)


def test_allows_pr_title_through_environment_boundary(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [pull_request]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - env:\n          PR_TITLE: ${{ github.event.pull_request.title }}\n        run: printf '%s\\n' \"$PR_TITLE\"\n",
    )
    assert findings == []
