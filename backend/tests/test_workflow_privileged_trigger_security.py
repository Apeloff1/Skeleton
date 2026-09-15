from __future__ import annotations

from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_workflow_security_policy import violations


PIN = "11d5960a326750d5838078e36cf38b85af677262"


def _scan(tmp_path: Path, name: str, source: str) -> list[str]:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_non_allowlisted_pull_request_target_stays_forbidden(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "workflow.yml",
        "name: test\non:\n  pull_request_target:\npermissions:\n  contents: read\njobs: {}\n",
    )
    assert any("pull_request_target is forbidden" in finding for finding in findings)


def test_allows_metadata_only_pr_hygiene_target(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "pr-hygiene.yml",
        "name: test\non:\n  pull_request_target:\npermissions:\n  contents: read\n  pull-requests: read\njobs:\n  classify:\n    permissions:\n      contents: read\n      pull-requests: read\n      issues: write\n    env:\n      PR: ${{ github.event.pull_request.number }}\n      REPO: ${{ github.repository }}\n    steps:\n      - run: printf '%s %s\\n' \"$REPO\" \"$PR\"\n",
    )
    assert findings == []


def test_allowlisted_target_rejects_any_action_use(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "pr-hygiene.yml",
        f"name: test\non:\n  pull_request_target:\npermissions:\n  contents: read\njobs:\n  classify:\n    steps:\n      - uses: actions/checkout@{PIN}\n        with:\n          persist-credentials: false\n",
    )
    assert any("must not use actions" in finding for finding in findings)


def test_allowlisted_target_rejects_untrusted_pr_fields(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "pr-hygiene.yml",
        "name: test\non:\n  pull_request_target:\npermissions:\n  contents: read\njobs:\n  classify:\n    env:\n      HEAD_SHA: ${{ github.event.pull_request.head.sha }}\n    steps:\n      - run: echo safe\n",
    )
    assert any("found pull request field head.sha" in finding for finding in findings)


def test_allowlisted_target_rejects_non_issue_write_scope(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "pr-hygiene.yml",
        "name: test\non:\n  pull_request_target:\npermissions:\n  contents: read\njobs:\n  classify:\n    permissions:\n      contents: write\n      issues: write\n    steps:\n      - run: echo safe\n",
    )
    assert any("found contents: write" in finding for finding in findings)


def test_allowlisted_target_keeps_base_top_level_write_rejection(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "pr-hygiene.yml",
        "name: test\non:\n  pull_request_target:\npermissions:\n  contents: read\n  issues: write\njobs:\n  classify:\n    steps:\n      - run: echo safe\n",
    )
    assert any("workflow-wide issues: write is forbidden" in finding for finding in findings)
