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


def test_accepts_reviewed_docker_qemu_action(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\\non: [push]\\npermissions: {{}}\\njobs:\\n  test:\\n    steps:\\n      - uses: docker/setup-qemu-action@{PIN}\\n",
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


GODOT_PIN = "f166999204a4f2722c6fe042fbaa3b3ea0d9c789"


def test_accepts_only_reviewed_godot_exact_release(tmp_path: Path) -> None:
    source = (
        "name: godot\non: [push]\npermissions: {}\njobs:\n"
        "  build:\n    steps:\n"
        f"      - uses: chickensoft-games/setup-godot@{GODOT_PIN}\n"
    )
    assert _scan(tmp_path, source) == []


def test_godot_different_sha_still_requires_review(tmp_path: Path) -> None:
    source = (
        "jobs:\n  build:\n    steps:\n"
        f"      - uses: chickensoft-games/setup-godot@{PIN}\n"
    )
    assert any("not allowlisted" in problem for problem in _scan(tmp_path, source))


def test_godot_mutable_release_tag_is_not_approved(tmp_path: Path) -> None:
    source = (
        "jobs:\n  build:\n    steps:\n"
        "      - uses: chickensoft-games/setup-godot@v2.4.1\n"
    )
    assert any("not allowlisted" in problem for problem in _scan(tmp_path, source))


def test_godot_approval_does_not_extend_to_sibling_or_reusable_workflow(
    tmp_path: Path,
) -> None:
    for reference in (
        f"chickensoft-games/other-action@{GODOT_PIN}",
        f"chickensoft-games/setup-godot/.github/workflows/run.yml@{GODOT_PIN}",
        f"chickensoft-games/setup-godot/another@{GODOT_PIN}",
    ):
        source = f"jobs:\n  job:\n    uses: {reference}\n"
        assert any("not allowlisted" in problem for problem in _scan(tmp_path, source))
