from __future__ import annotations

import json
import os
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import pytest

from skeleton.pr_automation import runner
from skeleton.pr_automation.safety import (
    OperatorSafetyError,
    load_operator_safety,
)


def test_operator_safety_defaults_active() -> None:
    state = load_operator_safety({})
    assert state.blocked is False
    assert state.status == "active"
    assert state.reason == ""


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", " TRUE "])
def test_pause_truthy_values_are_explicit(value: str) -> None:
    state = load_operator_safety({"SKELETON_AUTOMATION_PAUSED": value})
    assert state.blocked
    assert state.status == "paused"


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", " FALSE "])
def test_pause_false_values_are_explicit(value: str) -> None:
    state = load_operator_safety({"SKELETON_AUTOMATION_PAUSED": value})
    assert not state.blocked


@pytest.mark.parametrize("value", ["maybe", "enabled", "disabled", "2", "-1"])
def test_ambiguous_pause_values_fail_closed(value: str) -> None:
    with pytest.raises(OperatorSafetyError):
        load_operator_safety({"SKELETON_AUTOMATION_PAUSED": value})


def test_quarantine_dominates_pause_status() -> None:
    state = load_operator_safety(
        {
            "SKELETON_AUTOMATION_PAUSED": "true",
            "SKELETON_AUTOMATION_QUARANTINED": "true",
        }
    )
    assert state.blocked
    assert state.status == "quarantined"


def test_reason_is_bounded_and_control_character_free() -> None:
    with pytest.raises(OperatorSafetyError, match="too long"):
        load_operator_safety(
            {"SKELETON_AUTOMATION_HOLD_REASON": "x" * 501}
        )
    with pytest.raises(OperatorSafetyError, match="control"):
        load_operator_safety(
            {"SKELETON_AUTOMATION_HOLD_REASON": "incident\x00secret"}
        )


def test_public_payload_contains_no_environment_snapshot() -> None:
    state = load_operator_safety(
        {
            "SKELETON_AUTOMATION_PAUSED": "true",
            "SKELETON_AUTOMATION_HOLD_REASON": "incident containment",
            "SOME_OTHER_VALUE": "must-not-leak",
        }
    )
    assert state.public_payload() == {
        "status": "paused",
        "blocked": True,
        "reason": "incident containment",
    }


@pytest.mark.parametrize(
    ("env_key", "env_value", "expected_status"),
    [
        ("SKELETON_AUTOMATION_PAUSED", "true", "paused"),
        ("SKELETON_AUTOMATION_QUARANTINED", "true", "quarantined"),
    ],
)
def test_runner_hold_returns_before_token_or_network_client_construction(
    env_key: str,
    env_value: str,
    expected_status: str,
) -> None:
    output = StringIO()
    environment = {
        env_key: env_value,
        "SKELETON_AUTOMATION_HOLD_REASON": "security response",
        "GITHUB_TOKEN": "",
        "PR_AUTOMATION_MODE": "apply",
    }

    with patch.dict(os.environ, environment, clear=False), patch.object(
        runner.GitHubClient,
        "__init__",
        side_effect=AssertionError("GitHubClient must not be constructed during hold"),
    ), redirect_stdout(output):
        assert runner.main(["--repo", "Apeloff1/Skeleton", "--limit", "1"]) == 0

    payload = json.loads(output.getvalue())
    assert payload["kind"] == "pr-automation-operator-hold"
    assert payload["status"] == expected_status
    assert payload["blocked"] is True
    assert payload["reason"] == "security response"


def test_malformed_hold_fails_before_token_or_network_client_construction() -> None:
    with patch.dict(
        os.environ,
        {
            "SKELETON_AUTOMATION_PAUSED": "ambiguous",
            "GITHUB_TOKEN": "should-not-be-consumed",
        },
        clear=False,
    ), patch.object(
        runner.GitHubClient,
        "__init__",
        side_effect=AssertionError("GitHubClient must not be constructed"),
    ):
        with pytest.raises(OperatorSafetyError):
            runner.main(["--repo", "Apeloff1/Skeleton", "--limit", "1"])


def test_workflow_exposes_all_operator_hold_variables() -> None:
    from pathlib import Path

    text = Path(".github/workflows/pr-automation-index.yml").read_text(
        encoding="utf-8"
    )
    assert (
        "SKELETON_AUTOMATION_PAUSED: "
        "${{ vars.SKELETON_AUTOMATION_PAUSED }}"
    ).replace("\\", "") in text
    assert (
        "SKELETON_AUTOMATION_QUARANTINED: "
        "${{ vars.SKELETON_AUTOMATION_QUARANTINED }}"
    ).replace("\\", "") in text
    assert (
        "SKELETON_AUTOMATION_HOLD_REASON: "
        "${{ vars.SKELETON_AUTOMATION_HOLD_REASON }}"
    ).replace("\\", "") in text


def test_isolated_staging_includes_safety_module_implicitly() -> None:
    from pathlib import Path

    text = Path(".github/workflows/pr-automation-index.yml").read_text(
        encoding="utf-8"
    )
    assert 'cp -R skeleton/pr_automation "$trusted_root/pr_automation"' in text
    assert "from pr_automation.runner import main" in text
