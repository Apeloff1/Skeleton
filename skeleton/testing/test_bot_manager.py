from dataclasses import asdict

from skeleton.automation import bot_manager as bot_manager_module
from skeleton.automation.advanced_bots import ADVANCED_BOTS
from skeleton.automation.bot_manager import (
    COOLDOWN_SECONDS,
    DEFAULT_BOTS,
    BotHealth,
    record_result,
    record_worker_outcome,
    select_due,
)


def test_manager_has_complete_advanced_bot_roster():
    expected = {bot.name for bot in ADVANCED_BOTS}
    assert expected <= set(DEFAULT_BOTS)
    assert len(expected) == 12


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
    import pytest

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
