"""Deterministic economy simulation with journaled ledger."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from skeleton.game.mechanics_depth.tick_clock import SeededEntropy, TickClock

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


def fee_curve_0(amount: int, rate_bps: int = 10) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_0(income: int) -> int:
    brackets = [(0, 0.0), (500, 0.1), (2000, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_1(amount: int, rate_bps: int = 11) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_1(income: int) -> int:
    brackets = [(100, 0.0), (600, 0.1), (2100, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_2(amount: int, rate_bps: int = 12) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_2(income: int) -> int:
    brackets = [(200, 0.0), (700, 0.1), (2200, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_3(amount: int, rate_bps: int = 13) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_3(income: int) -> int:
    brackets = [(300, 0.0), (800, 0.1), (2300, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_4(amount: int, rate_bps: int = 14) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_4(income: int) -> int:
    brackets = [(400, 0.0), (900, 0.1), (2400, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_5(amount: int, rate_bps: int = 15) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_5(income: int) -> int:
    brackets = [(500, 0.0), (1000, 0.1), (2500, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_6(amount: int, rate_bps: int = 16) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_6(income: int) -> int:
    brackets = [(600, 0.0), (1100, 0.1), (2600, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_7(amount: int, rate_bps: int = 17) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_7(income: int) -> int:
    brackets = [(700, 0.0), (1200, 0.1), (2700, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_8(amount: int, rate_bps: int = 18) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_8(income: int) -> int:
    brackets = [(800, 0.0), (1300, 0.1), (2800, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_9(amount: int, rate_bps: int = 19) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_9(income: int) -> int:
    brackets = [(900, 0.0), (1400, 0.1), (2900, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_10(amount: int, rate_bps: int = 20) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_10(income: int) -> int:
    brackets = [(1000, 0.0), (1500, 0.1), (3000, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_11(amount: int, rate_bps: int = 21) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_11(income: int) -> int:
    brackets = [(1100, 0.0), (1600, 0.1), (3100, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_12(amount: int, rate_bps: int = 22) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_12(income: int) -> int:
    brackets = [(1200, 0.0), (1700, 0.1), (3200, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_13(amount: int, rate_bps: int = 23) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_13(income: int) -> int:
    brackets = [(1300, 0.0), (1800, 0.1), (3300, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_14(amount: int, rate_bps: int = 24) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_14(income: int) -> int:
    brackets = [(1400, 0.0), (1900, 0.1), (3400, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_15(amount: int, rate_bps: int = 25) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_15(income: int) -> int:
    brackets = [(1500, 0.0), (2000, 0.1), (3500, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_16(amount: int, rate_bps: int = 26) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_16(income: int) -> int:
    brackets = [(1600, 0.0), (2100, 0.1), (3600, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_17(amount: int, rate_bps: int = 27) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_17(income: int) -> int:
    brackets = [(1700, 0.0), (2200, 0.1), (3700, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_18(amount: int, rate_bps: int = 28) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_18(income: int) -> int:
    brackets = [(1800, 0.0), (2300, 0.1), (3800, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_19(amount: int, rate_bps: int = 29) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_19(income: int) -> int:
    brackets = [(1900, 0.0), (2400, 0.1), (3900, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_20(amount: int, rate_bps: int = 30) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_20(income: int) -> int:
    brackets = [(2000, 0.0), (2500, 0.1), (4000, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_21(amount: int, rate_bps: int = 31) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_21(income: int) -> int:
    brackets = [(2100, 0.0), (2600, 0.1), (4100, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_22(amount: int, rate_bps: int = 32) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_22(income: int) -> int:
    brackets = [(2200, 0.0), (2700, 0.1), (4200, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_23(amount: int, rate_bps: int = 33) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_23(income: int) -> int:
    brackets = [(2300, 0.0), (2800, 0.1), (4300, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_24(amount: int, rate_bps: int = 34) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_24(income: int) -> int:
    brackets = [(2400, 0.0), (2900, 0.1), (4400, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_25(amount: int, rate_bps: int = 35) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_25(income: int) -> int:
    brackets = [(2500, 0.0), (3000, 0.1), (4500, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_26(amount: int, rate_bps: int = 36) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_26(income: int) -> int:
    brackets = [(2600, 0.0), (3100, 0.1), (4600, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_27(amount: int, rate_bps: int = 37) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_27(income: int) -> int:
    brackets = [(2700, 0.0), (3200, 0.1), (4700, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_28(amount: int, rate_bps: int = 38) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_28(income: int) -> int:
    brackets = [(2800, 0.0), (3300, 0.1), (4800, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_29(amount: int, rate_bps: int = 39) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_29(income: int) -> int:
    brackets = [(2900, 0.0), (3400, 0.1), (4900, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_30(amount: int, rate_bps: int = 40) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_30(income: int) -> int:
    brackets = [(3000, 0.0), (3500, 0.1), (5000, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_31(amount: int, rate_bps: int = 41) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_31(income: int) -> int:
    brackets = [(3100, 0.0), (3600, 0.1), (5100, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_32(amount: int, rate_bps: int = 42) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_32(income: int) -> int:
    brackets = [(3200, 0.0), (3700, 0.1), (5200, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_33(amount: int, rate_bps: int = 43) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_33(income: int) -> int:
    brackets = [(3300, 0.0), (3800, 0.1), (5300, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_34(amount: int, rate_bps: int = 44) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_34(income: int) -> int:
    brackets = [(3400, 0.0), (3900, 0.1), (5400, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_35(amount: int, rate_bps: int = 45) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_35(income: int) -> int:
    brackets = [(3500, 0.0), (4000, 0.1), (5500, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_36(amount: int, rate_bps: int = 46) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_36(income: int) -> int:
    brackets = [(3600, 0.0), (4100, 0.1), (5600, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_37(amount: int, rate_bps: int = 47) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_37(income: int) -> int:
    brackets = [(3700, 0.0), (4200, 0.1), (5700, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_38(amount: int, rate_bps: int = 48) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_38(income: int) -> int:
    brackets = [(3800, 0.0), (4300, 0.1), (5800, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_39(amount: int, rate_bps: int = 49) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_39(income: int) -> int:
    brackets = [(3900, 0.0), (4400, 0.1), (5900, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_40(amount: int, rate_bps: int = 50) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_40(income: int) -> int:
    brackets = [(4000, 0.0), (4500, 0.1), (6000, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_41(amount: int, rate_bps: int = 51) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_41(income: int) -> int:
    brackets = [(4100, 0.0), (4600, 0.1), (6100, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_42(amount: int, rate_bps: int = 52) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_42(income: int) -> int:
    brackets = [(4200, 0.0), (4700, 0.1), (6200, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_43(amount: int, rate_bps: int = 53) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_43(income: int) -> int:
    brackets = [(4300, 0.0), (4800, 0.1), (6300, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_44(amount: int, rate_bps: int = 54) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_44(income: int) -> int:
    brackets = [(4400, 0.0), (4900, 0.1), (6400, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_45(amount: int, rate_bps: int = 55) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_45(income: int) -> int:
    brackets = [(4500, 0.0), (5000, 0.1), (6500, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_46(amount: int, rate_bps: int = 56) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_46(income: int) -> int:
    brackets = [(4600, 0.0), (5100, 0.1), (6600, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_47(amount: int, rate_bps: int = 57) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_47(income: int) -> int:
    brackets = [(4700, 0.0), (5200, 0.1), (6700, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_48(amount: int, rate_bps: int = 58) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_48(income: int) -> int:
    brackets = [(4800, 0.0), (5300, 0.1), (6800, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)


def fee_curve_49(amount: int, rate_bps: int = 59) -> int:
    if amount < 0 or not 0 <= rate_bps <= 10_000:
        raise ValueError("fee bounds")
    return (amount * rate_bps) // 10_000


def tax_bracket_49(income: int) -> int:
    brackets = [(4900, 0.0), (5400, 0.1), (6900, 0.2), (10**9, 0.3)]
    prev = 0
    tax = 0.0
    rem = income
    for cap, rate in brackets:
        span = min(rem, cap - prev)
        if span <= 0:
            break
        tax += span * rate
        rem -= span
        prev = cap
    return int(tax)
