"""Expanded tests for local_model_console_capability_v2."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.ai.agents.jeeves.local_model_console_capability_v2 import make_capability_v2, CAPABILITY_SCHEMA


@pytest.fixture
def cap():
    db = Path(__file__).parent.parent / "ai/agents/jeeves/fleet_database_v2.json"
    return make_capability_v2(db)


def test_fleet_size_at_least_70(cap):
    assert len(cap.list_cores()) >= 70
    assert len(cap.list_cores()) == 83


def test_summary_schema(cap):
    s = cap.fleet_summary()
    assert s["schema"] == CAPABILITY_SCHEMA
    assert s["total_declared_cores"] == 83
    assert "by_era" in s
    assert "by_category" in s
    assert s["bios_required_count"] > 0


def test_filter_handheld(cap):
    handheld = cap.filter(category="handheld")
    assert len(handheld) >= 10
    assert any(r.name == "mgba" for r in handheld)
    assert any(r.name == "gambatte" for r in handheld)


def test_filter_bios(cap):
    needs_bios = cap.filter(bios_required=True)
    assert len(needs_bios) >= 10
    assert all(r.bios_required for r in needs_bios)


def test_search(cap):
    results = cap.search("snes")
    assert any("snes" in r.name for r in results)
    assert any("SNES" in " ".join(r.hardware) for r in results)


def test_recommend_handheld(cap):
    rec = cap.recommend_for_learning("handheld")
    assert "mgba" in rec or "gambatte" in rec


def test_recommend_accuracy(cap):
    rec = cap.recommend_for_learning("accuracy")
    assert "bsnes" in rec or "mesen" in rec


def test_plan_session_bounds(cap):
    plan = cap.plan_session(hardware="snes", max_steps=99999)
    assert plan["max_steps"] <= 10000
    assert plan["schema"] == CAPABILITY_SCHEMA
    assert len(plan["constraints"]) >= 4


def test_curriculum(cap):
    cur = cap.curriculum(3)
    assert len(cur) == 3
    assert cur[0]["stage"] == 1


def test_exports(cap):
    choices = cap.emulator_console_choices()
    assert len(choices) == 83
    assert all(c["choice"].startswith("emulator:") for c in choices)
    csv_text = cap.to_csv()
    assert "core,hardware" in csv_text
    md = cap.to_markdown_table()
    assert "| Core |" in md


def test_model_card_and_inject(cap):
    card = cap.model_card("detailed")
    assert "83" in card or "declared" in card
    injected = cap.inject_into_prompt("hello world", "compact")
    assert "CONSOLE_EMULATOR_CAPABILITY" in injected
    assert len(injected) < 20000


def test_dispatch(cap):
    result = cap.dispatch("fleet_summary")
    assert result["total_declared_cores"] == 83
    unknown = cap.dispatch("nonexistent")
    assert "error" in unknown


def test_validate(cap):
    v = cap.validate_fleet()
    assert v["healthy"] is True
    assert v["total"] == 83
