from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.persistence.spine_dark import SpineDark
from skeleton.persistence.spine_quiet import SpineQuiet
from skeleton.persistence.spine_quiet_witness import SpineQuietWitness, SpineQuietWitnessError


def test_witness_reads_dark_and_hides_foreign(tmp_path: Path) -> None:
    path = tmp_path / "quiet.sqlite"
    dark = SpineDark().card(
        {"live_motor": False, "driver_imports": 0},
        {"called": False, "dispatcher_running": False},
        {"merged": False, "ci_green": False},
    )
    quiet = SpineQuiet(path)
    quiet.append("house-a", dark)
    quiet.close()
    witness = SpineQuietWitness(path)
    card = witness.card("house-a")
    assert card["seen"] is True
    assert card["live_motor"] is False
    assert card["merged"] is False
    assert witness.card("house-b")["seen"] is False
    witness.close()


def test_witness_refuses_a_lit_row(tmp_path: Path) -> None:
    path = tmp_path / "quiet.sqlite"
    dark = SpineDark().card(
        {"live_motor": False, "driver_imports": 0},
        {"called": False, "dispatcher_running": False},
        {"merged": False, "ci_green": False},
    )
    quiet = SpineQuiet(path)
    quiet.append("house-a", dark)
    quiet.close()
    import sqlite3
    conn = sqlite3.connect(path)
    conn.execute("UPDATE spine_quiet SET merged = 1 WHERE tenant_id = ?", ("house-a",))
    conn.commit()
    conn.close()
    witness = SpineQuietWitness(path)
    with pytest.raises(SpineQuietWitnessError):
        witness.card("house-a")
    witness.close()
