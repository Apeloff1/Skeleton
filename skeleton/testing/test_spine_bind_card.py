from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from skeleton.persistence.spine_bind_card import SpineBindCard, SpineBindCardError
from skeleton.persistence.spine_bind_chain import SpineBindChain, SpineBindChainError
from skeleton.persistence.spine_bind_journal import SpineBindJournal, SpineBindJournalError
from skeleton.persistence.spine_bind_read import SpineBindRead, SpineBindReadError
from skeleton.persistence.spine_dark import SpineDark
from skeleton.persistence.spine_epoch_witness import SpineEpochWitness
from skeleton.persistence.spine_quiet import SpineQuiet
from skeleton.persistence.spine_quiet_witness import SpineQuietWitness


def _quiet(tmp_path: Path, tenant: str = "house-a") -> dict:
    path = tmp_path / "quiet.sqlite"
    dark = SpineDark().card(
        {"live_motor": False, "driver_imports": 0},
        {"called": False, "dispatcher_running": False},
        {"merged": False, "ci_green": False},
    )
    journal = SpineQuiet(path)
    journal.append(tenant, dark)
    journal.close()
    witness = SpineQuietWitness(path)
    card = witness.card(tenant)
    witness.close()
    return card


def _dark() -> dict:
    return SpineDark().card(
        {"live_motor": False, "driver_imports": 0},
        {"called": False, "dispatcher_running": False},
        {"merged": False, "ci_green": False},
    )


def _epoch(side: dict, epoch: int = 4) -> dict:
    return SpineEpochWitness().card(epoch_before=epoch, epoch_after=epoch, side=side)


def test_bind_card_joins_dark_proofs_and_refuses_green(tmp_path: Path) -> None:
    quiet = _quiet(tmp_path)
    dark = _dark()
    epoch = _epoch(dark)
    card = SpineBindCard().card(tenant_id="house-a", quiet=quiet, dark=dark, epoch=epoch)
    assert card["kind"] == "spine_bind_card"
    assert card["hit"] is False
    assert card["moved"] is False
    assert card["live_motor"] is False
    assert card["merged"] is False
    assert card["apply_landed"] is False
    assert card["epoch_before"] == 4
    assert len(card["digest"]) == 64
    lit = dict(dark)
    lit["merged"] = True
    with pytest.raises(SpineBindCardError):
        SpineBindCard().card(tenant_id="house-a", quiet=quiet, dark=lit, epoch=epoch)
    moved = dict(epoch)
    moved["epoch_after"] = 5
    with pytest.raises(SpineBindCardError):
        SpineBindCard().card(tenant_id="house-a", quiet=quiet, dark=dark, epoch=moved)


def test_journal_refuses_rewrite_and_hides_foreign(tmp_path: Path) -> None:
    quiet = _quiet(tmp_path)
    dark = _dark()
    card = SpineBindCard().card(
        tenant_id="house-a",
        quiet=quiet,
        dark=dark,
        epoch=_epoch(dark),
    )
    path = tmp_path / "bind.sqlite"
    journal = SpineBindJournal(path)
    sealed = journal.append("house-a", card)
    assert sealed["rewritten"] is False
    again = journal.append("house-a", card)
    assert again["digest"] == sealed["digest"]
    assert journal.read("house-b")["seen"] is False
    other = dict(card)
    other["digest"] = "a" * 64
    with pytest.raises(SpineBindJournalError):
        journal.append("house-a", other)
    journal.close()


def test_read_fails_closed_on_a_lit_row(tmp_path: Path) -> None:
    quiet = _quiet(tmp_path)
    dark = _dark()
    card = SpineBindCard().card(
        tenant_id="house-a",
        quiet=quiet,
        dark=dark,
        epoch=_epoch(dark),
    )
    path = tmp_path / "bind.sqlite"
    journal = SpineBindJournal(path)
    journal.append("house-a", card)
    journal.close()
    reader = SpineBindRead(path)
    seen = reader.card("house-a")
    assert seen["seen"] is True
    assert seen["hit"] is False
    assert seen["ci_green"] is False
    assert reader.card("house-b")["seen"] is False
    reader.close()
    conn = sqlite3.connect(path)
    conn.execute("UPDATE spine_bind_card SET merged = 1 WHERE tenant_id = ?", ("house-a",))
    conn.commit()
    conn.close()
    reader = SpineBindRead(path)
    with pytest.raises(SpineBindReadError):
        reader.card("house-a")
    reader.close()


def test_chain_seals_dark_row_and_refuses_rewrite(tmp_path: Path) -> None:
    quiet = _quiet(tmp_path)
    dark = _dark()
    card = SpineBindCard().card(
        tenant_id="house-a",
        quiet=quiet,
        dark=dark,
        epoch=_epoch(dark),
    )
    path = tmp_path / "bind.sqlite"
    journal = SpineBindJournal(path)
    journal.append("house-a", card)
    journal.close()
    chain = SpineBindChain(path)
    sealed = chain.seal("house-a")
    assert sealed["rows"] == 1
    assert sealed["rewritten"] is False
    assert len(sealed["digest"]) == 64
    with pytest.raises(SpineBindChainError):
        chain.seal("house-b")
    chain.close()
    conn = sqlite3.connect(path)
    conn.execute("UPDATE spine_bind_card SET ci_green = 1 WHERE tenant_id = ?", ("house-a",))
    conn.commit()
    conn.close()
    chain = SpineBindChain(path)
    with pytest.raises(SpineBindChainError):
        chain.seal("house-a")
    chain.close()
