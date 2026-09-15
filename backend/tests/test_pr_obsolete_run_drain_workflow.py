from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.check_workflow_security import TRUSTED_PULL_REQUEST_TARGET_SHA256


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-obsolete-run-drain.yml"


def test_privileged_pr_drainer_is_pinned_to_workflow_revision() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request_target:" in text
    assert "ref: ${{ github.workflow_sha }}" in text
    assert "ref: ${{ github.event.pull_request.base.sha }}" not in text
    assert "persist-credentials: false" in text


def test_privileged_pr_drainer_never_checks_out_pr_head() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    checkout_block = text.split("uses: actions/checkout@", 1)[1].split(
        "- name: Cancel obsolete live PR-linked runs", 1
    )[0]
    assert "pull_request.head.sha" not in checkout_block
    assert "pull_request.head.ref" not in checkout_block


def test_security_allowlist_matches_exact_privileged_workflow_bytes() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    actual = hashlib.sha256(text.encode("utf-8")).hexdigest()

    assert TRUSTED_PULL_REQUEST_TARGET_SHA256[WORKFLOW.name] == actual
