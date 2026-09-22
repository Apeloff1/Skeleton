"""Compute budgets — per-agent resource envelopes with hard cutoffs.

Every agent in the swarm burns the same shared currencies: model tokens,
wall-clock seconds, tool calls, queue slots. Without envelopes, one
runaway agent quietly eats the whole fleet's allowance and the first
signal is the invoice.

- :class:`Budget` — a set of named currency caps with a shared window
  (e.g. per hour, per dream cycle). Spending is atomic per-currency;
  partial grants are refused, never silently clipped.
- :class:`BudgetLedger` — issues budgets, records spend, sweeps expired
  windows, and raises :class:`BudgetExceeded` at the exact call that
  would cross the line — fail-fast, not post-hoc.
- Soft headroom alerts via the ``on_threshold`` hook so the bus can
  publish a WARNING before the hard stop.

Pure accounting; the enforcement is that callers check before acting.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Mapping, Optional, Tuple

from .errors import KernelError


class BudgetError(KernelError):
    code = "KRN.BUDGET"


class BudgetExceeded(BudgetError):
    code = "KRN.BUDGET_EXCEEDED"
    http_status = 429


class UnknownCurrency(BudgetError):
    code = "KRN.BUDGET_CURRENCY"


@dataclass
class Budget:
    owner: str
    caps: Dict[str, float]
    window_s: float
    opened_at: float
    spent: Dict[str, float] = field(default_factory=dict)
    alert_fraction: float = 0.8

    def is_live(self, now: float) -> bool:
        return now < self.opened_at + self.window_s

    def remaining(self, currency: str) -> float:
        return self.caps.get(currency, 0.0) - self.spent.get(currency, 0.0)

    def utilisation(self, currency: str) -> float:
        cap = self.caps.get(currency, 0.0)
        if cap <= 0:
            return 1.0
        return self.spent.get(currency, 0.0) / cap


class BudgetLedger:
    """Issues and polices budgets; one ledger per kernel."""

    def __init__(
        self,
        *,
        clock: Optional[Callable[[], float]] = None,
        on_threshold: Optional[Callable[[str, str, float], None]] = None,
    ) -> None:
        self._now = clock or time.monotonic
        self._on_threshold = on_threshold
        self._budgets: Dict[str, Budget] = {}
        self._alerted: set = set()

    # ------------------------------------------------------------------
    # Issuance
    # ------------------------------------------------------------------

    def issue(self, owner: str, caps: Mapping[str, float],
              *, window_s: float = 3600.0,
              alert_fraction: float = 0.8) -> Budget:
        if window_s <= 0:
            raise BudgetError("budget window must be positive",
                              context={"window_s": window_s})
        for name, cap in caps.items():
            if cap <= 0:
                raise BudgetError(
                    "currency caps must be positive",
                    context={"currency": name, "cap": cap},
                )
        budget = Budget(owner=owner, caps=dict(caps), window_s=window_s,
                        opened_at=self._now(), alert_fraction=alert_fraction)
        self._budgets[owner] = budget
        self._alerted = {k for k in self._alerted if not k.startswith(owner + "|")}
        return budget

    def revoke(self, owner: str) -> bool:
        return self._budgets.pop(owner, None) is not None

    # ------------------------------------------------------------------
    # Spending
    # ------------------------------------------------------------------

    def check(self, owner: str, currency: str, amount: float) -> float:
        """Return remaining allowance; raise if the spend wouldn't fit."""
        budget = self._require(owner)
        self._require_currency(budget, currency)
        if amount <= 0:
            raise BudgetError("spend amount must be positive",
                              context={"amount": amount})
        remaining = budget.remaining(currency)
        if amount > remaining:
            raise BudgetExceeded(
                "spend exceeds remaining budget",
                context={"owner": owner, "currency": currency,
                         "requested": amount, "remaining": remaining},
            )
        return remaining

    def spend(self, owner: str, currency: str, amount: float) -> float:
        """Atomic check-and-debit; returns remaining allowance."""
        budget = self._require(owner)
        self.check(owner, currency, amount)
        budget.spent[currency] = budget.spent.get(currency, 0.0) + amount
        self._maybe_alert(budget, currency)
        return budget.remaining(currency)

    def refund(self, owner: str, currency: str, amount: float) -> None:
        budget = self._require(owner)
        self._require_currency(budget, currency)
        current = budget.spent.get(currency, 0.0)
        budget.spent[currency] = max(0.0, current - amount)

    # ------------------------------------------------------------------
    # Windows and reporting
    # ------------------------------------------------------------------

    def sweep(self) -> Tuple[str, ...]:
        """Expire dead windows; returns owners whose budget lapsed."""
        now = self._now()
        expired = [o for o, b in self._budgets.items() if not b.is_live(now)]
        for o in expired:
            del self._budgets[o]
        self._alerted = {k for k in self._alerted
                         if k.split("|", 1)[0] not in expired}
        return tuple(sorted(expired))

    def status(self, owner: str) -> Dict[str, object]:
        budget = self._require(owner)
        now = self._now()
        return {
            "owner": owner,
            "live": budget.is_live(now),
            "window_expires_in": max(0.0, budget.opened_at + budget.window_s - now),
            "currencies": {
                c: {
                    "cap": budget.caps[c],
                    "spent": budget.spent.get(c, 0.0),
                    "remaining": budget.remaining(c),
                    "utilisation": round(budget.utilisation(c), 4),
                }
                for c in sorted(budget.caps)
            },
        }

    def owners(self) -> Tuple[str, ...]:
        return tuple(sorted(self._budgets))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require(self, owner: str) -> Budget:
        budget = self._budgets.get(owner)
        if budget is None:
            raise BudgetError("no budget issued for owner",
                              context={"owner": owner})
        if not budget.is_live(self._now()):
            raise BudgetError("budget window has expired — reissue",
                              context={"owner": owner})
        return budget

    @staticmethod
    def _require_currency(budget: Budget, currency: str) -> None:
        if currency not in budget.caps:
            raise UnknownCurrency(
                "currency not covered by this budget",
                context={"owner": budget.owner, "currency": currency,
                         "known": tuple(sorted(budget.caps))},
            )

    def _maybe_alert(self, budget: Budget, currency: str) -> None:
        if self._on_threshold is None:
            return
        key = f"{budget.owner}|{currency}"
        if key in self._alerted:
            return
        if budget.utilisation(currency) >= budget.alert_fraction:
            self._alerted.add(key)
            self._on_threshold(budget.owner, currency,
                               budget.utilisation(currency))
