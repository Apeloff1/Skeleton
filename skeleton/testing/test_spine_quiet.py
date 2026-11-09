from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.persistence.spine_dark import SpineDark
from skeleton.persistence.spine_quiet import SpineQuiet, SpineQuietError


def test_quiet_journal_refuses_a_rewrite(tmp_path: Path) -> None:
    dark = SpineDark().card(
        {"live_motor": False, "driver_imports": 0},
        {"called": False, "dispatcher_running": False},
        {"merged": False, "ci_green": False},
    )
    quiet = SpineQuiet(tmp_path / "quiet.sqlite")
    first = quiet.append("house-a", dark)
    second = quiet.append("house-a", dark)
    assert first["digest"] == second["digest"]
    assert first["rewritten"] is False
    assert quiet.read("house-b")["seen"] is False
    other = dict(dark)
    other["merged"] = False
    other["extra"] = 1
    with pytest.raises(SpineQuietError):
        quiet.append("house-a", other)
    quiet.close()
