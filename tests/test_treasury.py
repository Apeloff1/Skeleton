"""Treasury double-entry — port of gameforge-rs economy.rs."""

from __future__ import annotations

import pytest

from skeleton.economy import Account, Entry, Treasury, TreasuryError
from skeleton.economy.treasury import LEDGER_CAP


@pytest.fixture()
def treasury() -> Treasury:
    return Treasury()


def test_open_account_idempotent(treasury: Treasury):
    a = treasury.open_account("alpha")
    assert a.name == "alpha"
    assert a.balance == 0
    assert a.frozen is False
    b = treasury.open_account("alpha")
    assert b.name == "alpha"
    assert len(treasury.accounts()) == 1


def test_mint_requires_provenance(treasury: Treasury):
    treasury.open_account("vault")
    with pytest.raises(TreasuryError, match="provenance"):
        treasury.mint("vault", 100, "", "no court")


def test_mint_and_balance(treasury: Treasury):
    treasury.open_account("vault")
    entry = treasury.mint("vault", 1_000, "quorum-evt-1", "founding grant")
    assert isinstance(entry, Entry)
    assert entry.delta == 1_000
    assert entry.counterparty == "mint"
    assert entry.provenance == "quorum-evt-1"
    acc = treasury.account("vault")
    assert acc is not None
    assert acc.balance == 1_000
    assert acc.entries == 1


def test_mint_unknown_and_nonpositive(treasury: Treasury):
    with pytest.raises(TreasuryError, match="no such account"):
        treasury.mint("ghost", 10, "evt", "x")
    treasury.open_account("vault")
    with pytest.raises(TreasuryError, match="positive"):
        treasury.mint("vault", 0, "evt", "x")
    with pytest.raises(TreasuryError, match="positive"):
        treasury.mint("vault", -5, "evt", "x")


def test_transfer_double_entry(treasury: Treasury):
    treasury.open_account("alpha")
    treasury.open_account("beta")
    treasury.mint("alpha", 500, "quorum-mint", "seed")
    debit, credit = treasury.transfer("alpha", "beta", 200, "payroll")
    assert debit.delta == -200
    assert credit.delta == 200
    assert debit.provenance == credit.provenance
    assert debit.counterparty == "beta"
    assert credit.counterparty == "alpha"
    assert treasury.account("alpha").balance == 300
    assert treasury.account("beta").balance == 200
    report = treasury.audit()
    assert report["balance_sum"] == 500
    assert report["ledger_window_sum"] == 500  # mint + debit + credit
    assert report["window_balanced"] is True


def test_transfer_fail_closed(treasury: Treasury):
    treasury.open_account("alpha")
    treasury.open_account("beta")
    treasury.mint("alpha", 50, "evt", "seed")
    with pytest.raises(TreasuryError, match="insufficient funds"):
        treasury.transfer("alpha", "beta", 51, "overdraw")
    with pytest.raises(TreasuryError, match="self-transfer"):
        treasury.transfer("alpha", "alpha", 1, "noop")
    with pytest.raises(TreasuryError, match="no such destination"):
        treasury.transfer("alpha", "ghost", 1, "x")
    with pytest.raises(TreasuryError, match="positive"):
        treasury.transfer("alpha", "beta", 0, "x")


def test_freeze_blocks_mint_and_transfer(treasury: Treasury):
    treasury.open_account("alpha")
    treasury.open_account("beta")
    treasury.mint("alpha", 100, "evt", "seed")
    assert treasury.freeze("alpha", True) is True
    assert treasury.account("alpha").frozen is True
    with pytest.raises(TreasuryError, match="frozen"):
        treasury.mint("alpha", 10, "evt2", "blocked")
    with pytest.raises(TreasuryError, match="source account frozen"):
        treasury.transfer("alpha", "beta", 10, "blocked")
    treasury.freeze("beta", True)
    treasury.freeze("alpha", False)
    with pytest.raises(TreasuryError, match="destination account frozen"):
        treasury.transfer("alpha", "beta", 10, "blocked")
    assert treasury.freeze("missing", True) is False


def test_audit_after_mint(treasury: Treasury):
    treasury.open_account("a")
    treasury.open_account("b")
    treasury.mint("a", 10, "e1", "")
    treasury.mint("b", 20, "e2", "")
    report = treasury.audit()
    assert report["accounts"] == 2
    assert report["balance_sum"] == 30
    assert report["ledger_entries"] == 2
    assert report["window_balanced"] is True


def test_ledger_spill_keeps_newest_half(treasury: Treasury):
    """At LEDGER_CAP the hot window drains the oldest half (RS semantics)."""
    treasury.open_account("vault")
    # Cap is large; shrink via monkeypatch of instance ledger fill.
    # Drive spill by temporarily using a tiny cap through internal fill.
    original = LEDGER_CAP
    # Fill just past half of a reduced path by calling _record after stuffing.
    with treasury._lock:
        for i in range(original):
            treasury._ledger.append(
                Entry(
                    account="vault",
                    delta=1,
                    counterparty="mint",
                    memo=str(i),
                    provenance=f"p{i}",
                )
            )
            treasury._accounts["vault"].balance += 1
        assert len(treasury._ledger) == original
        treasury._record(
            Entry(
                account="vault",
                delta=1,
                counterparty="mint",
                memo="spill-trigger",
                provenance="spill",
            )
        )
        treasury._accounts["vault"].balance += 1
        # drain half then push → half + 1
        assert len(treasury._ledger) == original // 2 + 1
        assert treasury._ledger[-1].memo == "spill-trigger"
        assert treasury._ledger[0].memo == str(original // 2)
