"""Story arc outline contract and AIFT-JEEVES mirror parity."""

from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.ai.agents.jeeves import story_arc as mirror
from skeleton.jeeves.story_arc import MAX_TITLE_LENGTH, story_arc

ROOT = Path(__file__).resolve().parents[2]


def test_three_acts_in_order_with_stakes_rules() -> None:
    arc = story_arc("  Ember Vale  ")
    assert arc["title"] == "Ember Vale"
    assert list(arc["acts"]) == ["1_setup", "2_confrontation", "3_resolution"]
    assert "inciting incident" in arc["acts"]["1_setup"]
    assert "Protagonist changes by the end" in arc["rules"]
    assert arc["era_note"]


def test_each_call_returns_independent_containers() -> None:
    first = story_arc("A")
    first["rules"].append("mutated")
    first["acts"]["1_setup"] = "mutated"
    second = story_arc("A")
    assert "mutated" not in second["rules"]
    assert second["acts"]["1_setup"] != "mutated"


@pytest.mark.parametrize(
    ("title", "error"),
    [
        (None, TypeError),
        (42, TypeError),
        ("", ValueError),
        ("   ", ValueError),
        ("x" * (MAX_TITLE_LENGTH + 1), ValueError),
        ("bad\ntitle", ValueError),
        ("bad\x7ftitle", ValueError),
    ],
)
def test_rejects_invalid_titles(title: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        story_arc(title)  # type: ignore[arg-type]


def test_agent_mirror_is_byte_identical() -> None:
    canonical = ROOT / "skeleton" / "jeeves" / "story_arc.py"
    mirrored = ROOT / "skeleton" / "ai" / "agents" / "jeeves" / "story_arc.py"
    assert canonical.read_bytes() == mirrored.read_bytes()
    assert mirror.story_arc("A") == story_arc("A")
