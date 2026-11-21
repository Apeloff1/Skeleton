"""Character arc outline contract and AIFT-JEEVES mirror parity."""

from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.ai.agents.jeeves import character_arc as mirror
from skeleton.jeeves.character_arc import MAX_NAME_LENGTH, character_arc

ROOT = Path(__file__).resolve().parents[2]


def test_want_need_flaw_ghost_change_in_order() -> None:
    arc = character_arc("  Mara  ")
    assert arc["character"] == "Mara"
    assert list(arc["elements"]) == ["want", "need", "flaw", "ghost", "change"]
    assert "Change is earned through events" in arc["rules"]


def test_each_call_returns_independent_containers() -> None:
    first = character_arc("Mara")
    first["rules"].clear()
    first["elements"]["want"] = "mutated"
    second = character_arc("Mara")
    assert second["rules"]
    assert second["elements"]["want"] == "External goal"


@pytest.mark.parametrize(
    ("name", "error"),
    [
        (None, TypeError),
        (["Mara"], TypeError),
        ("", ValueError),
        ("\t ", ValueError),
        ("x" * (MAX_NAME_LENGTH + 1), ValueError),
        ("Ma\x00ra", ValueError),
    ],
)
def test_rejects_invalid_names(name: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        character_arc(name)  # type: ignore[arg-type]


def test_agent_mirror_is_byte_identical() -> None:
    canonical = ROOT / "skeleton" / "jeeves" / "character_arc.py"
    mirrored = ROOT / "skeleton" / "ai" / "agents" / "jeeves" / "character_arc.py"
    assert canonical.read_bytes() == mirrored.read_bytes()
    assert mirror.character_arc("Mara") == character_arc("Mara")
