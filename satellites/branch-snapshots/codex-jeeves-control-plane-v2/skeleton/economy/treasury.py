"""Treasury — the zaibatsu's double-entry ledger.

Port of gameforge-rs ``economy.rs`` Treasury. Double-entry by construction:
every transfer debits one account and credits another under one lock, and
the books must always balance against the mint. There is no eraser —
corrections are counter-entries, never edits. Unknown accounts fail closed.

Minting is a court act: new scrip enters only with a quorum-decided
provenance event id. An empire that prints without its court is an empire
already falling.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from skeleton.kernel.errors import SkeletonError

LEDGER_CAP = 65536


class TreasuryError(SkeletonError):
    """Treasury refuse — unknown account, frozen, insufficient funds, bad mint."""

    code = "ECO.TREASURY"
    http_status = 400


@dataclass
class Entry:
    """One immutable ledger line. Money is never a float (satoshi-scale int)."""

    account: str
    delta: int
    counterparty: str
    memo: str
    provenance: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "account": self.account,
            "delta": self.delta,
            "counterparty": self.counterparty,
            "memo": self.memo,
            "at": self.at,
            "provenance": self.provenance,
        }


@dataclass
class Account:
    name: str
    balance: int = 0
    entries: int = 0
    frozen: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "balance": self.balance,
            "entries": self.entries,
            "frozen": self.frozen,
        }


class Treasury:
    """In-process double-entry treasury.

    Thread-safe via a single RLock covering account mutation + paired
    transfer legs (mirrors the RS write lock that keeps the books from
    being observed half-written).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._accounts: dict[str, Account] = {}
        self._ledger: list[Entry] = []

    def open_account(self, name: str) -> Account:
        with self._lock:
            acc = self._accounts.get(name)
            if acc is None:
                acc = Account(name=name)
                self._accounts[name] = acc
            return Account(
                name=acc.name,
                balance=acc.balance,
                entries=acc.entries,
                frozen=acc.frozen,
            )

    def mint(
        self,
        account: str,
        amount: int,
        provenance_event: str,
        memo: str = "",
    ) -> Entry:
        """Mint scrip into an account. Requires a quorum provenance event id."""
        if amount <= 0:
            raise TreasuryError("mint amount must be positive")
        if not provenance_event:
            raise TreasuryError("mint requires quorum provenance event id")
        with self._lock:
            acc = self._accounts.get(account)
            if acc is None:
                raise TreasuryError("no such account")
            if acc.frozen:
                raise TreasuryError("account frozen")
            acc.balance += amount
            acc.entries += 1
            entry = Entry(
                account=account,
                delta=amount,
                counterparty="mint",
                memo=memo,
                provenance=provenance_event,
            )
            self._record(entry)
            return entry

    def transfer(
        self,
        from_account: str,
        to_account: str,
        amount: int,
        memo: str = "",
    ) -> tuple[Entry, Entry]:
        """Transfer between accounts. Both legs land under one lock."""
        if amount <= 0:
            raise TreasuryError("transfer amount must be positive")
        if from_account == to_account:
            raise TreasuryError("self-transfer is not a transfer")
        with self._lock:
            src = self._accounts.get(from_account)
            if src is None:
                raise TreasuryError("no such source account")
            if src.frozen:
                raise TreasuryError("source account frozen")
            if src.balance < amount:
                raise TreasuryError(
                    "insufficient funds — the treasury extends no credit"
                )
            dst = self._accounts.get(to_account)
            if dst is None:
                raise TreasuryError("no such destination account")
            if dst.frozen:
                raise TreasuryError("destination account frozen")
            pair = str(uuid.uuid4())
            debit = Entry(
                account=from_account,
                delta=-amount,
                counterparty=to_account,
                memo=memo,
                provenance=pair,
            )
            credit = Entry(
                account=to_account,
                delta=amount,
                counterparty=from_account,
                memo=memo,
                provenance=pair,
            )
            src.balance -= amount
            src.entries += 1
            dst.balance += amount
            dst.entries += 1
            self._record(debit)
            self._record(credit)
            return debit, credit

    def freeze(self, account: str, frozen: bool = True) -> bool:
        """Freeze (or unfreeze) an account. Frozen accounts can be read, never moved."""
        with self._lock:
            acc = self._accounts.get(account)
            if acc is None:
                return False
            acc.frozen = frozen
            return True

    def _record(self, entry: Entry) -> None:
        # Caller holds ``_lock``. Append-only; at capacity spill oldest half.
        if len(self._ledger) >= LEDGER_CAP:
            drain = LEDGER_CAP // 2
            del self._ledger[:drain]
        self._ledger.append(entry)

    def audit(self) -> dict[str, Any]:
        """Audit: balance sum vs ledger window sum must agree (or window spilled)."""
        with self._lock:
            balance_sum = sum(a.balance for a in self._accounts.values())
            ledger_sum = sum(e.delta for e in self._ledger)
            n = len(self._ledger)
            return {
                "accounts": len(self._accounts),
                "balance_sum": balance_sum,
                "ledger_window_sum": ledger_sum,
                "ledger_entries": n,
                "window_balanced": balance_sum == ledger_sum or n >= LEDGER_CAP // 2,
            }

    def account(self, name: str) -> Account | None:
        with self._lock:
            acc = self._accounts.get(name)
            if acc is None:
                return None
            return Account(
                name=acc.name,
                balance=acc.balance,
                entries=acc.entries,
                frozen=acc.frozen,
            )

    def accounts(self) -> list[Account]:
        with self._lock:
            return [
                Account(
                    name=a.name,
                    balance=a.balance,
                    entries=a.entries,
                    frozen=a.frozen,
                )
                for a in self._accounts.values()
            ]
