"""Plot beat sheet contract and AIFT-JEEVES mirror parity."""

from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.ai.agents.jeeves import plot_beats as mirror
from skeleton.jeeves.plot_beats import MAX_TITLE_LENGTH, plot_beats

ROOT = Path(__file__).resolve().parents[2]


def test_beats_are_ordered_from_inciting_incident_to_resolution() -> None:
    sheet = plot_beats(" Ember Vale ")
    assert sheet["title"] == "Ember Vale"
    beats = sheet["beats"]
    assert beats[0] == "opening image"
    assert beats[-1] == "resolution"
    assert beats.index("inciting incident") < beats.index("midpoint") < beats.index("climax")
    assert len(set(beats)) == len(beats)


def test_each_call_returns_independent_containers() -> None:
    first = plot_beats("A")
    first["beats"].reverse()
    assert plot_beats("A")["beats"][0] == "opening image"


@pytest.mark.parametrize(
    ("title", "error"),
    [(None, TypeError), (3.0, TypeError), ("", ValueError), (" ", ValueError),
     ("x" * (MAX_TITLE_LENGTH + 1), ValueError), ("a\rb", ValueError)],
)
def test_rejects_invalid_titles(title: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        plot_beats(title)  # type: ignore[arg-type]


def test_agent_mirror_is_byte_identical() -> None:
    canonical = ROOT / "skeleton" / "jeeves" / "plot_beats.py"
    mirrored = ROOT / "skeleton" / "ai" / "agents" / "jeeves" / "plot_beats.py"
    assert canonical.read_bytes() == mirrored.read_bytes()
    assert mirror.plot_beats("A") == plot_beats("A")
