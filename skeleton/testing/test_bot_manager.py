from dataclasses import asdict

import pytest

from skeleton.automation import bot_manager as bot_manager_module
from skeleton.automation.advanced_bots import ADVANCED_BOTS, AdvancedBot, allowed
from skeleton.automation.bot_manager import (
    COOLDOWN_SECONDS,
    DEFAULT_BOTS,
    BotHealth,
    authorized_builder_available,
    bounded_health_summary,
    record_result,
    record_worker_outcome,
    select_due,
)


def test_manager_has_complete_advanced_bot_roster():
    expected = {bot.name for bot in ADVANCED_BOTS}
    assert expected <= set(DEFAULT_BOTS)
    assert len(expected) == len(ADVANCED_BOTS) == 13


def test_advanced_bot_definition_fails_closed():
    invalid = (
        {"name": "Root_Cause"},
        {"trigger": ""},
        {"trigger": "bad\ntrigger"},
        {"risk": "critical"},
        {"max_files": True},
        {"max_files": 49},
        {"requires_tests": 1},
    )
    base = {
        "name": "unit-test",
        "trigger": "focused test signal",
        "risk": "low",
        "max_files": 2,
        "requires_tests": True,
    }
    for override in invalid:
        with pytest.raises(ValueError):
            AdvancedBot(**{**base, **override})


def test_advanced_bot_path_policy_rejects_ambiguous_and_duplicate_paths():
    bot = AdvancedBot(
        "unit-test",
        "focused test signal",
        "low",
        3,
    )
    assert allowed(bot, ["skeleton/example.py", "tests/test_example.py"])
    for paths in (
        ["skeleton//example.py"],
        ["skeleton/./example.py"],
        ["skeleton/../example.py"],
        ["skeleton/example.py", "skeleton/example.py"],
        ["skeleton/automation/example.py"],
        ["backend/example.py"],
    ):
        assert allowed(bot, paths) is False


def test_manager_limits_due_bots_and_honors_cooldown():
    state = {name: asdict(BotHealth(name=name, last_run=0)) for name in DEFAULT_BOTS}
    assert len(select_due(state, now=COOLDOWN_SECONDS + 1)) <= 3
    state["triage"]["last_run"] = COOLDOWN_SECONDS + 1
    assert "triage" not in select_due(state, now=COOLDOWN_SECONDS + 1)


def test_manager_opens_circuit_after_three_failures():
    state = {}
    for _ in range(3):
        record_result(state, "security-auditor", success=False, now=100)
    assert state["security-auditor"]["circuit_open"] is True
    assert "security-auditor" not in select_due(
        state, now=100 + COOLDOWN_SECONDS + 1
    )


def test_state_write_uses_unique_temp_and_cleans_it(tmp_path, monkeypatch):
    target = tmp_path / "bot-state.json"
    legacy = target.with_suffix(".tmp")
    legacy.write_text("sentinel", encoding="utf-8")
    monkeypatch.setattr(bot_manager_module, "STATE", target)

    bot_manager_module.save_state({"triage": {"enabled": True}})

    assert legacy.read_text(encoding="utf-8") == "sentinel"
    assert target.exists()
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_semantic_no_change_is_successful_worker_outcome():
    state = {}
    record_worker_outcome(
        state,
        {
            "bot": "security-auditor",
            "returncode": 0,
            "evidence": {
                "bot": "security-auditor",
                "status": "no-change",
            },
        },
        now=200,
    )
    item = state["security-auditor"]
    assert item["failures"] == 0
    assert item["circuit_open"] is False
    assert item["last_run"] == 200.0


def test_existing_pr_dedup_is_successful_worker_outcome():
    state = {}
    record_worker_outcome(
        state,
        {
            "bot": "root-cause",
            "returncode": 0,
            "evidence": {
                "bot": "root-cause",
                "status": "existing-pr",
                "pull_request": 42,
            },
        },
        now=300,
    )
    assert state["root-cause"]["failures"] == 0


def test_zero_exit_without_evidence_counts_as_failure():
    state = {}
    for moment in (1, 2, 3):
        record_worker_outcome(
            state,
            {
                "bot": "root-cause",
                "returncode": 0,
                "evidence": None,
            },
            now=moment,
        )
    assert state["root-cause"]["failures"] == 3
    assert state["root-cause"]["circuit_open"] is True


def test_nonzero_exit_with_success_shaped_evidence_still_fails():
    state = {}
    record_worker_outcome(
        state,
        {
            "bot": "root-cause",
            "returncode": 1,
            "evidence": {
                "bot": "root-cause",
                "status": "no-change",
            },
        },
        now=400,
    )
    assert state["root-cause"]["failures"] == 1


def test_worker_outcome_rejects_unregistered_identity():
    with pytest.raises(ValueError):
        record_worker_outcome(
            {},
            {
                "bot": "arbitrary-worker",
                "returncode": 0,
                "evidence": {
                    "bot": "arbitrary-worker",
                    "status": "no-change",
                },
            },
        )


def test_health_summary_is_bounded_non_authoritative_and_deterministic():
    state = {
        "security-auditor": {
            "name": "security-auditor",
            "enabled": True,
            "failures": 2,
            "last_run": 900.0,
            "circuit_open": False,
            "secret": "must-not-propagate",
        },
        "attacker-worker": {
            "name": "attacker-worker",
            "enabled": True,
            "failures": 999,
            "last_run": 999.0,
            "circuit_open": False,
        },
    }
    summary = bounded_health_summary(state, now=1000.0)
    assert summary["non_authoritative"] is True
    assert summary["worker_count"] == len(DEFAULT_BOTS)
    names = [item["name"] for item in summary["workers"]]
    assert names == sorted(DEFAULT_BOTS)
    assert "attacker-worker" not in names
    security = next(
        item for item in summary["workers"]
        if item["name"] == "security-auditor"
    )
    assert security == {
        "name": "security-auditor",
        "enabled": True,
        "failures": 2,
        "circuit_open": False,
        "seconds_since_last_run": 100,
    }
    assert "secret" not in security


def test_health_summary_normalizes_malformed_state():
    summary = bounded_health_summary(
        {
            "root-cause": {
                "enabled": "yes",
                "failures": -5,
                "last_run": float("nan"),
                "circuit_open": "no",
            }
        },
        now=1000.0,
    )
    root = next(
        item for item in summary["workers"]
        if item["name"] == "root-cause"
    )
    assert root["enabled"] is True
    assert root["failures"] == 0
    assert root["circuit_open"] is False
    assert root["seconds_since_last_run"] is None


def test_authorized_builder_bypasses_cooldown_but_not_disable_or_circuit():
    state = {
        "feature-builder": asdict(
            BotHealth(
                name="feature-builder",
                enabled=True,
                last_run=COOLDOWN_SECONDS + 100,
                circuit_open=False,
            )
        )
    }
    assert authorized_builder_available(state) is True

    state["feature-builder"]["enabled"] = False
    assert authorized_builder_available(state) is False

    state["feature-builder"]["enabled"] = True
    state["feature-builder"]["circuit_open"] = True
    assert authorized_builder_available(state) is False
