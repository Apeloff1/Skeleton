"""Tests for local-model console emulator capability bridge.

Ensures the bridge stays read-only, fail-closed, and useful for offline models.
"""

from __future__ import annotations

import pytest

from skeleton.ai.agents.jeeves.local_model_console_capability import (
    LocalModelConsoleCapability,
    make_capability,
    CAPABILITY_SCHEMA,
)


def test_list_cores_returns_seventy_plus():
    cap = LocalModelConsoleCapability()
    cores = cap.list_cores()
    assert len(cores) >= 70
    assert "snes9x" in cores
    assert "gambatte" in cores
    assert "mgba" in cores


def test_fleet_summary_schema():
    cap = make_capability()
    summary = cap.fleet_summary()
    assert summary["schema"] == CAPABILITY_SCHEMA
    assert summary["total_declared_cores"] >= 70
    assert "coverage_percent" in summary
    assert summary["installed_count"] >= 0


def test_get_status_unknown_is_safe():
    cap = LocalModelConsoleCapability()
    status = cap.get_status("nonexistent_core_xyz")
    assert status.name == "nonexistent_core_xyz"
    assert status.installed is False
    assert "declared" in status.notes or "requires" in status.notes


def test_plan_session_respects_bounds():
    cap = LocalModelConsoleCapability()
    plan = cap.plan_session(hardware="snes", max_steps=50000)
    assert plan["max_steps"] <= 10000
    assert plan["schema"] == CAPABILITY_SCHEMA
    assert len(plan["constraints"]) >= 3
    assert "no BIOS" in " ".join(plan["constraints"])


def test_tool_schema_is_valid_json_shape():
    cap = LocalModelConsoleCapability()
    schema = cap.build_model_tool_schema()
    assert schema["name"] == "console_emulator_capability"
    assert "action" in schema["parameters"]["properties"]
    assert "list_cores" in schema["parameters"]["properties"]["action"]["enum"]


def test_prompt_injection_is_bounded():
    cap = LocalModelConsoleCapability()
    long_prompt = "user question " * 2000
    injected = cap.inject_into_prompt(long_prompt)
    assert len(injected) <= 8192 + 200  # small overhead
    assert "CONSOLE_EMULATOR_CAPABILITY" in injected
    assert CAPABILITY_SCHEMA in injected


def test_qualification_matrix_length():
    cap = LocalModelConsoleCapability()
    matrix = cap.qualification_matrix()
    assert len(matrix) >= 70
    assert all("capability_level" in row for row in matrix)
    assert all(row["capability_level"] in ("orchestrate-only", "native-isolated") for row in matrix)


def test_recommend_for_learning():
    cap = LocalModelConsoleCapability()
    rec = cap.recommend_for_learning("handheld")
    assert "gambatte" in rec or "mgba" in rec
    rec2 = cap.recommend_for_learning("arcade")
    assert any(c in rec2 for c in ("fbneo", "mame2003"))
    # Should not crash even if env and path are absent
    cap = make_capability("/nonexistent/path/that/does/not/exist.json")
    assert isinstance(cap, LocalModelConsoleCapability)
    # list still works via fallback
    assert len(cap.list_cores()) >= 70
