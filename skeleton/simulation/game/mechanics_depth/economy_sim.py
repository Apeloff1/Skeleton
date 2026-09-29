"""Deterministic economy simulation with journaled ledger."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from skeleton.simulation.game.mechanics_depth.tick_clock import SeededEntropy, TickClock

MAX_BAL = 1_000_000_000
MAX_ENTRIES = 4096


@dataclass(frozen=True)
class LedgerEntry:
    tick: int
    account: str
    delta: int
    reason: str
    balance_after: int

    def digest(self) -> str:
        body = json.dumps(self.__dict__, sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()


@dataclass(frozen=True)
class EconomySnapshot:
    tick: int
    balances: Tuple[Tuple[str, int], ...]
    digest: str


class EconomySim:
    def __init__(self, seed: int, *, clock: Optional[TickClock] = None) -> None:
        self.clock = clock or TickClock()
        self.entropy = SeededEntropy(seed)
        self._bal: Dict[str, int] = {}
        self._ledger: List[LedgerEntry] = []

    def open(self, account: str, opening: int = 0) -> None:
        if account in self._bal:
            raise ValueError("exists")
        if not account or opening < 0 or opening > MAX_BAL:
            raise ValueError("bad open")
        self._bal[account] = opening

    def transact(self, account: str, delta: int, reason: str = "xfer") -> LedgerEntry:
        if account not in self._bal:
            raise KeyError(account)
        if abs(delta) > MAX_BAL:
            raise ValueError("delta")
        nxt = self._bal[account] + delta
        if nxt < 0 or nxt > MAX_BAL:
            raise ValueError("balance bounds")
        tick = self.clock.advance()
        self._bal[account] = nxt
        e = LedgerEntry(tick, account, delta, reason[:64], nxt)
        self._ledger.append(e)
        if len(self._ledger) > MAX_ENTRIES:
            self._ledger = self._ledger[-MAX_ENTRIES:]
        return e

    def transfer(self, src: str, dst: str, amount: int) -> Tuple[LedgerEntry, LedgerEntry]:
        if amount <= 0:
            raise ValueError("amount")
        a = self.transact(src, -amount, "debit")
        b = self.transact(dst, amount, "credit")
        return a, b

    def snapshot(self) -> EconomySnapshot:
        bal = tuple(sorted(self._bal.items()))
        dig = hashlib.sha256(json.dumps(bal).encode()).hexdigest()
        return EconomySnapshot(self.clock.tick, bal, dig)

    def replay_digest(self) -> str:
        return hashlib.sha256("".join(e.digest() for e in self._ledger).encode()).hexdigest()
