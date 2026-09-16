from skeleton.automation.bot_manager import COOLDOWN_SECONDS, DEFAULT_BOTS, BotHealth, record_result, select_due


def test_manager_has_advanced_bot_roster():
    assert {"dependency", "test", "review", "docs", "performance", "release"} <= set(DEFAULT_BOTS)


def test_manager_limits_due_bots_and_honors_cooldown():
    state = {name: BotHealth(name=name, last_run=0). __dict__ for name in DEFAULT_BOTS}
    assert len(select_due(state, now=COOLDOWN_SECONDS + 1)) <= 3
    state["triage"]["last_run"] = COOLDOWN_SECONDS + 1
    assert "triage" not in select_due(state, now=COOLDOWN_SECONDS + 1)


def test_manager_opens_circuit_after_three_failures():
    state = {}
    for _ in range(3):
        record_result(state, "security", success=False, now=100)
    assert state["security"]["circuit_open"] is True
    assert "security" not in select_due(state, now=100 + COOLDOWN_SECONDS + 1)
