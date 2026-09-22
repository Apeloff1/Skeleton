from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.automation import bot_manager
from skeleton.automation.bot_manager import (
    BASE_BOTS,
    COOLDOWN_SECONDS,
    MAX_FAILURES,
    normalise_state,
    record_result,
    save_state,
    select_base_due,
)


def test_normalise_state_drops_unknown_and_sanitizes_values() -> None:
    state = normalise_state(
        {
            "triage": {
                "enabled": "yes",
                "failures": 999,
                "last_run": float("nan"),
                "circuit_open": "no",
            },
            "unknown-bot": {"enabled": True},
        }
    )

    assert "unknown-bot" not in state
    assert state["triage"]["enabled"] is True
    assert state["triage"]["failures"] == MAX_FAILURES
    assert state["triage"]["last_run"] == 0.0


def test_select_base_due_never_dispatches_specialists() -> None:
    state = normalise_state({})
    due = select_base_due(state, now=COOLDOWN_SECONDS + 1)

    assert due
    assert set(due) <= set(BASE_BOTS)
    assert len(due) <= bot_manager.MAX_CONCURRENT


def test_record_result_rejects_unknown_identity() -> None:
    with pytest.raises(ValueError, match="unknown bot"):
        record_result({}, "not-registered", success=False, now=1.0)


def test_save_state_uses_unique_atomic_temp_and_leaves_no_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / ".skeleton-bot-state.json"
    monkeypatch.setattr(bot_manager, "STATE", state_path)
    legacy_tmp = tmp_path / ".skeleton-bot-state.tmp"
    legacy_tmp.write_text("sentinel", encoding="utf-8")

    state = normalise_state({})
    record_result(state, "triage", success=False, now=123.0)
    save_state(state)

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["triage"]["failures"] == 1
    assert legacy_tmp.read_text(encoding="utf-8") == "sentinel"
    assert list(tmp_path.glob("..skeleton-bot-state.json.*.tmp")) == []
