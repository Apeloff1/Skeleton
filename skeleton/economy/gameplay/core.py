"""B026 inventory depth on top of the #807 economy simulation.

:class:`GameplayEconomy` extends :class:`~skeleton.simulation.economy.sim.EconomySim`
without changing it. It adds what gameplay systems need from inventories:

* **Item faucets and sinks.** Items only appear through a named source
  (loot, quest, craft, vendor) and only disappear through a named sink
  (consume, vendor). Per-item ``held == minted - burned`` is audited, the
  same invariant the base class keeps for money.
* **Weight limits** alongside slot/stack limits, enforced on every path that
  adds items, including the inherited vendor and trade paths.
* **Binding.** Bound (soulbound) quantities can be used, consumed and sold
  to NPC vendors but never moved or traded to another owner.
* **Exact-amount sinks** so controllers (see :mod:`.inflation`) can burn a
  computed amount under a declared sink's label and currency.

Every mutation checks all preconditions before it touches any book.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from skeleton.simulation.economy.sim import (
    BURN_ACCOUNT,
    VENDOR_FAUCET,
    VENDOR_SINK,
    CurrencySpec,
    EconomySim,
    EconomySimError,
    FaucetSpec,
    ItemSpec,
    SinkSpec,
    _req_id,
    _req_int,
)

ITEM_VENDOR_SOURCE = "vendor"
_RESERVED_ITEM_FLOWS = frozenset({ITEM_VENDOR_SOURCE, "trade", "move"})


@dataclass
class _ItemFlows:
    minted: int = 0
    burned: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    by_sink: dict[str, int] = field(default_factory=dict)


class GameplayEconomy(EconomySim):
    """EconomySim plus item flows, weight limits and binding."""

    def __init__(
        self,
        currencies: Iterable[CurrencySpec],
        items: Iterable[ItemSpec] = (),
        faucets: Iterable[FaucetSpec] = (),
        sinks: Iterable[SinkSpec] = (),
        *,
        market_tax_bps: int = 0,
        default_slots: int = 32,
        item_weights: Mapping[str, int] | None = None,
        default_max_weight: int | None = None,
    ) -> None:
        super().__init__(
            currencies,
            items,
            faucets,
            sinks,
            market_tax_bps=market_tax_bps,
            default_slots=default_slots,
        )
        weights: dict[str, int] = {}
        for item_id, weight in dict(item_weights or {}).items():
            if item_id not in self.items:
                raise EconomySimError(f"weight for unknown item {item_id!r}")
            weights[item_id] = _req_int(weight, "item weight")
        self.item_weights = weights
        if default_max_weight is not None:
            _req_int(default_max_weight, "default_max_weight", minimum=1)
        self.default_max_weight = default_max_weight
        self._max_weight: dict[str, int | None] = {}
        self._bound: dict[str, dict[str, int]] = {}
        self._item_flows: dict[str, _ItemFlows] = {item_id: _ItemFlows() for item_id in self.items}

    # -- accounts ---------------------------------------------------------
    def open_account(
        self,
        owner: str,
        *,
        slots: int | None = None,
        max_weight: int | None = None,
    ) -> None:
        with self._lock:
            super().open_account(owner, slots=slots)
            if owner not in self._max_weight:
                if max_weight is not None:
                    _req_int(max_weight, "max_weight", minimum=1)
                self._max_weight[owner] = self.default_max_weight if max_weight is None else max_weight
                self._bound[owner] = {}

    def owners(self) -> list[str]:
        with self._lock:
            return sorted(self._inventories)

    def weight(self, owner: str, stacks: Mapping[str, int] | None = None) -> int:
        with self._lock:
            held = self._owner(owner).stacks if stacks is None else stacks
            return sum(qty * self.item_weights.get(item_id, 0) for item_id, qty in held.items())

    def max_weight(self, owner: str) -> int | None:
        with self._lock:
            self._owner(owner)
            return self._max_weight.get(owner, self.default_max_weight)

    def bound_count(self, owner: str, item_id: str) -> int:
        with self._lock:
            self._owner(owner)
            return self._bound.get(owner, {}).get(item_id, 0)

    def free_count(self, owner: str, item_id: str) -> int:
        """Quantity of ``item_id`` that ``owner`` may move or trade away."""
        with self._lock:
            return self._owner(owner).count(item_id) - self.bound_count(owner, item_id)

    # -- capacity -----------------------------------------------------------
    def fits_many(self, owner: str, additions: Mapping[str, int]) -> bool:
        """True when every addition fits by slots *and* weight at once."""
        with self._lock:
            inv = self._owner(owner)
            after = dict(inv.stacks)
            for item_id, qty in additions.items():
                self._item(item_id)
                _req_int(qty, "qty", minimum=1)
                after[item_id] = after.get(item_id, 0) + qty
            if inv.slots_used(self.items, after) > inv.slots:
                return False
            cap = self._max_weight.get(owner, self.default_max_weight)
            return cap is None or self.weight(owner, after) <= cap

    def _require_fit(self, owner: str, additions: Mapping[str, int], label: str = "inventory full") -> None:
        if not self.fits_many(owner, additions):
            raise EconomySimError(label)

    def resize(self, owner: str, slots: int) -> None:
        """Grow or shrink an owner's slot count; shrinking below use is refused."""
        _req_int(slots, "slots", minimum=1)
        with self._lock:
            inv = self._owner(owner)
            if inv.slots_used(self.items) > slots:
                raise EconomySimError("cannot shrink below slots in use")
            inv.slots = slots

    # -- item flows ---------------------------------------------------------
    def _record_mint(self, item_id: str, qty: int, source: str) -> None:
        flows = self._item_flows[item_id]
        flows.minted += qty
        flows.by_source[source] = flows.by_source.get(source, 0) + qty

    def _record_burn(self, item_id: str, qty: int, sink: str) -> None:
        flows = self._item_flows[item_id]
        flows.burned += qty
        flows.by_sink[sink] = flows.by_sink.get(sink, 0) + qty

    def _unbind_for_removal(self, owner: str, item_id: str, qty: int) -> None:
        # Removing items consumes free copies first, bound copies last.
        bound = self._bound[owner].get(item_id, 0)
        remaining = self._inventories[owner].count(item_id) - qty
        if bound > remaining:
            if remaining > 0:
                self._bound[owner][item_id] = remaining
            else:
                self._bound[owner].pop(item_id, None)

    def grant_items(self, source: str, owner: str, item_id: str, qty: int = 1) -> int:
        """Item faucet: ``qty`` of ``item_id`` appears for ``owner`` from ``source``."""
        _req_id(source, "item source")
        if source in _RESERVED_ITEM_FLOWS:
            raise EconomySimError("reserved item source")
        _req_int(qty, "qty", minimum=1)
        with self._lock:
            self._item(item_id)
            inv = self._owner(owner)
            self._require_fit(owner, {item_id: qty})
            inv.stacks[item_id] = inv.count(item_id) + qty
            self._record_mint(item_id, qty, source)
            return qty

    def consume_items(self, sink: str, owner: str, item_id: str, qty: int = 1) -> int:
        """Item sink: ``qty`` of ``item_id`` is destroyed (used, crafted, decayed)."""
        _req_id(sink, "item sink")
        if sink in _RESERVED_ITEM_FLOWS:
            raise EconomySimError("reserved item sink")
        _req_int(qty, "qty", minimum=1)
        with self._lock:
            self._item(item_id)
            inv = self._owner(owner)
            if inv.count(item_id) < qty:
                raise EconomySimError("not enough items")
            self._unbind_for_removal(owner, item_id, qty)
            self._take(inv, item_id, qty)
            self._record_burn(item_id, qty, sink)
            return qty

    def move_items(self, src: str, dst: str, item_id: str, qty: int = 1) -> int:
        """Gift/transfer items between owners. Bound and untradeable items stay put."""
        _req_int(qty, "qty", minimum=1)
        if src == dst:
            raise EconomySimError("move to self refused")
        with self._lock:
            spec = self._item(item_id)
            s_inv = self._owner(src)
            d_inv = self._owner(dst)
            if not spec.tradeable:
                raise EconomySimError("item is not tradeable")
            if self.free_count(src, item_id) < qty:
                raise EconomySimError("not enough unbound items")
            self._require_fit(dst, {item_id: qty}, "destination inventory full")
            self._take(s_inv, item_id, qty)
            d_inv.stacks[item_id] = d_inv.count(item_id) + qty
            return qty

    def bind(self, owner: str, item_id: str, qty: int = 1) -> int:
        """Bind ``qty`` held copies to ``owner``; returns the total bound."""
        _req_int(qty, "qty", minimum=1)
        with self._lock:
            self._item(item_id)
            inv = self._owner(owner)
            bound = self._bound[owner].get(item_id, 0)
            if bound + qty > inv.count(item_id):
                raise EconomySimError("cannot bind more than held")
            self._bound[owner][item_id] = bound + qty
            return bound + qty

    # -- inherited paths, now weight/binding aware --------------------------
    def vendor_buy(self, owner: str, item_id: str, qty: int = 1) -> int:
        _req_int(qty, "qty", minimum=1)
        with self._lock:
            self._item(item_id)
            self._owner(owner)
            self._require_fit(owner, {item_id: qty})
            cost = super().vendor_buy(owner, item_id, qty)
            self._record_mint(item_id, qty, ITEM_VENDOR_SOURCE)
            return cost

    def vendor_sell(self, owner: str, item_id: str, qty: int = 1) -> int:
        _req_int(qty, "qty", minimum=1)
        with self._lock:
            self._item(item_id)
            self._owner(owner)
            if self._inventories[owner].count(item_id) >= qty:
                bound_before = dict(self._bound[owner])
                self._unbind_for_removal(owner, item_id, qty)
            else:
                bound_before = None
            try:
                proceeds = super().vendor_sell(owner, item_id, qty)
            except EconomySimError:
                if bound_before is not None:
                    self._bound[owner] = bound_before
                raise
            self._record_burn(item_id, qty, ITEM_VENDOR_SOURCE)
            return proceeds

    def trade(self, seller: str, buyer: str, item_id: str, qty: int, price: int) -> dict[str, int]:
        _req_int(qty, "qty", minimum=1)
        with self._lock:
            self._item(item_id)
            self._owner(seller)
            self._owner(buyer)
            if self.free_count(seller, item_id) < qty:
                raise EconomySimError("seller lacks unbound items")
            self._require_fit(buyer, {item_id: qty}, "buyer inventory full")
            return super().trade(seller, buyer, item_id, qty, price)

    # -- exact-amount money sink ---------------------------------------------
    def charge_amount(self, sink_id: str, owner: str, amount: int) -> int:
        """Burn exactly ``amount`` under declared sink ``sink_id`` (controller use)."""
        _req_int(amount, "amount", minimum=1)
        with self._lock:
            spec = self.sinks.get(sink_id)
            if spec is None:
                raise EconomySimError("no such sink")
            self._owner(owner)
            self._require_funds(spec.currency, owner, amount)
            self._burn(spec.currency, owner, amount, sink_id)
            return amount

    # -- telemetry ------------------------------------------------------------
    def item_report(self, item_id: str) -> dict[str, Any]:
        with self._lock:
            self._item(item_id)
            flows = self._item_flows[item_id]
            held = sum(inv.count(item_id) for inv in self._inventories.values())
            return {
                "item": item_id,
                "held": held,
                "minted": flows.minted,
                "burned": flows.burned,
                "by_source": dict(sorted(flows.by_source.items())),
                "by_sink": dict(sorted(flows.by_sink.items())),
            }

    def item_audit(self) -> dict[str, Any]:
        """Per item: held == minted - burned, bound <= held per owner."""
        with self._lock:
            per: dict[str, Any] = {}
            ok = True
            for item_id in sorted(self.items):
                report = self.item_report(item_id)
                balanced = report["held"] == report["minted"] - report["burned"]
                ok = ok and balanced
                per[item_id] = {"held": report["held"], "balanced": balanced}
            for owner, bound in self._bound.items():
                for item_id, qty in bound.items():
                    if qty > self._inventories[owner].count(item_id) or qty < 1:
                        ok = False
            return {"ok": ok, "items": per}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            snap = super().snapshot()
            snap["bound"] = {
                owner: dict(sorted(b.items())) for owner, b in sorted(self._bound.items()) if b
            }
            return snap


__all__ = ["BURN_ACCOUNT", "ITEM_VENDOR_SOURCE", "VENDOR_FAUCET", "VENDOR_SINK", "GameplayEconomy"]
