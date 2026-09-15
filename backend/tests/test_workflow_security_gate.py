from __future__ import annotations

from pathlib import Path

from scripts.check_workflow_security import violations


PIN = "11d5960a326750d5838078e36cf38b85af677262"
DOCKER_DIGEST = "a" * 64


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "workflow.yml"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_accepts_sha_pinned_action_and_read_permissions(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@{PIN}\n        with:\n          persist-credentials: false\n",
    )
    assert findings == []


def test_rejects_checkout_default_persisted_credentials(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@{PIN}\n",
    )
    assert any("persist-credentials: false" in finding for finding in findings)


def test_rejects_checkout_explicit_persisted_credentials(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@{PIN}\n        with: {{persist-credentials: true}}\n",
    )
    assert any("persist-credentials: false" in finding for finding in findings)


def test_accepts_inline_checkout_credential_hardening(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@{PIN}\n        with: {{persist-credentials: false}}\n",
    )
    assert findings == []


def test_rejects_tag_pinned_action(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n        with: {persist-credentials: false}\n",
    )
    assert any("not pinned to a 40-character commit SHA" in finding for finding in findings)


def test_rejects_unversioned_action(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - uses: vendor/action\n",
    )
    assert any("must be pinned" in finding for finding in findings)


def test_rejects_tag_pinned_job_level_reusable_workflow(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  reusable:\n    uses: vendor/repo/.github/workflows/reuse.yml@v1\n",
    )
    assert any("not pinned to a 40-character commit SHA" in finding for finding in findings)


def test_accepts_sha_pinned_job_level_reusable_workflow(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  reusable:\n    uses: vendor/repo/.github/workflows/reuse.yml@{PIN}\n",
    )
    assert findings == []


def test_rejects_inline_mapping_tag_pin(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - {uses: actions/checkout@v4}\n",
    )
    assert any("not pinned to a 40-character commit SHA" in finding for finding in findings)


def test_rejects_mutable_docker_action_tag(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - uses: docker://alpine:3.20\n",
    )
    assert any("container action must be pinned" in finding for finding in findings)


def test_accepts_digest_pinned_docker_action(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - uses: docker://alpine@sha256:{DOCKER_DIGEST}\n",
    )
    assert findings == []


def test_allows_local_actions(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - uses: ./.github/actions/local\n",
    )
    assert findings == []


def test_rejects_missing_top_level_permissions(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@{PIN}\n        with: {{persist-credentials: false}}\n",
    )
    assert any("missing explicit top-level permissions" in finding for finding in findings)


def test_accepts_empty_top_level_permissions(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions: {}\njobs:\n  test:\n    steps:\n      - run: echo safe\n",
    )
    assert findings == []


def test_rejects_pull_request_target(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non:\n  pull_request_target:\npermissions:\n  contents: read\njobs: {}\n",
    )
    assert any("pull_request_target is forbidden" in finding for finding in findings)


def test_rejects_write_all_permissions(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions: write-all\njobs: {}\n",
    )
    assert any("write permissions are forbidden" in finding or "write-all" in finding for finding in findings)


def test_rejects_workflow_wide_individual_write_scope(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\n  id-token: write\njobs:\n  release:\n    steps:\n      - run: echo release\n",
    )
    assert any("workflow-wide id-token: write is forbidden" in finding for finding in findings)


def test_rejects_workflow_wide_read_all(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions: read-all\njobs:\n  test:\n    steps:\n      - run: echo safe\n",
    )
    assert any("workflow-wide read-all is forbidden" in finding for finding in findings)


def test_allows_job_local_write_elevation(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  release:\n    permissions:\n      contents: write\n      id-token: write\n    steps:\n      - run: echo release\n",
    )
    assert findings == []


def test_rejects_direct_pr_title_interpolation_in_inline_run(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [pull_request]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - run: echo '${{ github.event.pull_request.title }}'\n",
    )
    assert any("direct pull request title/body interpolation" in finding for finding in findings)


def test_rejects_direct_comment_interpolation_in_block_run(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [issues]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - name: unsafe\n        run: |\n          printf '%s\\n' '${{ github.event.comment.body }}'\n          echo done\n",
    )
    assert any("direct issue comment body interpolation" in finding for finding in findings)


def test_allows_untrusted_context_via_environment_boundary(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [pull_request]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - name: safe\n        env:\n          PR_TITLE: ${{ github.event.pull_request.title }}\n        run: printf '%s\\n' \"$PR_TITLE\"\n",
    )
    assert findings == []


def test_allows_trusted_expression_in_run(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - run: echo '${{ github.repository }}'\n",
    )
    assert findings == []


def test_composes_direct_dispatch_input_boundary_gate(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - run: echo \"${{ inputs.payload }}\"\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_composes_multiline_dispatch_input_boundary_gate(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - run: >\n          echo \"${{\n            github.event.inputs.payload\n          }}\"\n",
    )
    assert any("direct workflow input interpolation" in finding for finding in findings)


def test_composes_run_alias_boundary_gate(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\npermissions:\n  contents: read\nenv:\n  COMMAND: &command \"echo safe\"\njobs:\n  test:\n    steps:\n      - run: *command\n",
    )
    assert any("aliased run shell is forbidden" in finding for finding in findings)


def test_allows_dispatch_input_through_environment_boundary(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: workflow_dispatch\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - env:\n          PAYLOAD: ${{ inputs.payload }}\n        run: printf '%s\\n' \"$PAYLOAD\"\n",
    )
    assert findings == []
