from __future__ import annotations

import pytest

from skeleton.pr_automation.ruleset import (
    DEFAULT_GITHUB_ACTIONS_APP_ID,
    DEFAULT_MERGE_READINESS_CONTEXT,
    build_ruleset,
)
from skeleton.pr_automation.runner import GATE_CONTEXT


def test_ruleset_requires_native_readiness_policy_gate_and_strict_up_to_date_checks():
    payload = build_ruleset(branch="main", approvals=1)
    assert payload["enforcement"] == "active"
    assert payload["conditions"]["ref_name"]["include"] == ["refs/heads/main"]

    by_type = {rule["type"]: rule for rule in payload["rules"]}
    assert "deletion" in by_type
    assert "non_fast_forward" in by_type

    pull_request = by_type["pull_request"]["parameters"]
    assert pull_request["dismiss_stale_reviews_on_push"] is True
    assert pull_request["require_last_push_approval"] is True
    assert pull_request["required_review_thread_resolution"] is True
    assert pull_request["required_approving_review_count"] == 1

    checks = by_type["required_status_checks"]["parameters"]
    assert checks["strict_required_status_checks_policy"] is True
    assert checks["required_status_checks"] == [
        {
            "context": DEFAULT_MERGE_READINESS_CONTEXT,
            "integration_id": DEFAULT_GITHUB_ACTIONS_APP_ID,
        },
        {"context": GATE_CONTEXT, "integration_id": DEFAULT_GITHUB_ACTIONS_APP_ID},
    ]


def test_ruleset_rejects_unsafe_or_ambiguous_inputs():
    with pytest.raises(ValueError):
        build_ruleset(branch="refs/heads/main")
    with pytest.raises(ValueError):
        build_ruleset(approvals=-1)
    with pytest.raises(ValueError):
        build_ruleset(approvals=11)
    with pytest.raises(ValueError):
        build_ruleset(gate_context="")
    with pytest.raises(ValueError):
        build_ruleset(merge_readiness_context="")
    with pytest.raises(ValueError):
        build_ruleset(gate_context="same", merge_readiness_context="same")
    with pytest.raises(ValueError):
        build_ruleset(integration_id=0)


def test_ruleset_can_omit_app_binding_when_non_actions_status_providers_are_intended():
    payload = build_ruleset(integration_id=None)
    by_type = {rule["type"]: rule for rule in payload["rules"]}
    checks = by_type["required_status_checks"]["parameters"]["required_status_checks"]
    assert checks == [
        {"context": DEFAULT_MERGE_READINESS_CONTEXT},
        {"context": GATE_CONTEXT},
    ]
