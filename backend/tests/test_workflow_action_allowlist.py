from __future__ import annotations

from pathlib import Path

from scripts.check_workflow_action_allowlist import violations


PIN = "11d5960a326750d5838078e36cf38b85af677262"
DOCKER_DIGEST = "a" * 64


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "workflow.yml"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_accepts_github_owned_actions(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{}}\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@{PIN}\n      - uses: github/codeql-action/analyze@{PIN}\n",
    )
    assert findings == []


def test_accepts_reviewed_third_party_action(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{}}\njobs:\n  test:\n    steps:\n      - uses: gacts/gitleaks@{PIN}\n",
    )
    assert findings == []


def test_rejects_unreviewed_third_party_action_even_when_sha_pinned(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{}}\njobs:\n  test:\n    steps:\n      - uses: unreviewed/example-action@{PIN}\n",
    )
    assert any("third-party action repository is not allowlisted" in finding for finding in findings)
    assert any("unreviewed/example-action" in finding for finding in findings)


def test_rejects_unreviewed_reusable_workflow(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{}}\njobs:\n  reusable:\n    uses: vendor/repo/.github/workflows/reuse.yml@{PIN}\n",
    )
    assert any("vendor/repo" in finding for finding in findings)


def test_rejects_unreviewed_action_in_flow_style_step(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{}}\njobs:\n  test:\n    steps:\n      - {{uses: vendor/action@{PIN}, name: unsafe}}\n",
    )
    assert any("vendor/action" in finding for finding in findings)


def test_allows_local_actions_and_digest_pinned_container_actions(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{}}\njobs:\n  test:\n    steps:\n      - uses: ./.github/actions/local\n      - uses: docker://alpine@sha256:{DOCKER_DIGEST}\n",
    )
    assert findings == []
