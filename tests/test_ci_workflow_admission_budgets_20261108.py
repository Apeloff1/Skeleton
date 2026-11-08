"""Regression for fail-closed workflow admissions and bounded recovery policy.

The repository's hard twenty-admission ceiling is preserved for every
non-recovery workflow. Exactly three explicitly named, narrowly scoped
scheduled maintenance lanes are accounted for separately; no PR or security
gate is exempt. This test must stay aligned with the actual tier policy.
"""
from pathlib import Path

import pytest

from scripts.check_ci_workflow_tiers import (
    RECOVERY_PUSH_CONTRACTS,
    ROOT,
    SCHEDULED_RECOVERY,
    events,
    independently_triggered,
)


def test_non_independent_workflows_do_not_consume_automatic_admissions():
    assert not independently_triggered({"workflow_dispatch"})
    assert not independently_triggered({"workflow_call", "workflow_dispatch"})
    for trigger in ("pull_request", "pull_request_target", "merge_group",
                    "push", "schedule", "issue_comment", "workflow_run"):
        assert independently_triggered({trigger})


def test_exempted_operational_workflows_have_fixed_identity_and_triggers():
    expected = {
        "actions-housekeeping-cli.yml",
        "queue-drain.yml",
        "three-hour-actions-queue-expiry.yml",
    }
    assert SCHEDULED_RECOVERY == expected
    assert set(RECOVERY_PUSH_CONTRACTS) == expected
    for filename in expected:
        source = (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8")
        assert events(source) == {"workflow_dispatch", "schedule", "push"}
        assert "  pull_request:" not in source
        assert RECOVERY_PUSH_CONTRACTS[filename] in source
        assert "permissions: {}" in source


def test_duplicate_or_inline_event_map_is_fail_closed():
    for source in (
        "on:\n  pull_request: [opened]\njobs:\n",
        "on:\n  push:\n  push:\njobs:\n",
        "on:\n  workflow_dispatch:\non:\n  pull_request:\n",
        "on:\n  # only comments\njobs:\n",
    ):
        with pytest.raises(ValueError):
            events(source)


def test_explicit_triggers_are_preserved():
    assert events("name: gate\non:\n  pull_request:\n  workflow_dispatch:\n") == {
        "pull_request", "workflow_dispatch"
    }
