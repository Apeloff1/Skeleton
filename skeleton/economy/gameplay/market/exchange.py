"""Player market: escrow, price-time matching and settlement.

:class:`PlayerMarket` runs a continuous double auction on top of a
:class:`~skeleton.economy.gameplay.core.GameplayEconomy` and never creates
or destroys money or items on its own:

* **Escrow.** Placing a sell offer moves the items into the reserved
  ``ESCROW_OWNER`` inventory (``move_items`` — bound items cannot be
  listed). Placing a buy request moves ``qty * unit_price`` from the buyer
  to the escrow ledger account. Cancels, expiries and IOC remainders return
  exactly what is still escrowed.
* **Matching.** An incoming order trades against the best resting opposite
  order while prices cross; the print is at the *resting* (maker) price.
  A buyer filled below their limit gets the difference back from escrow.
* **Settlement.** Items go escrow -> buyer (or to a claim held in escrow
  when the buyer's bags are full), money goes escrow -> seller, then the
  sales tax is burned from the seller under a declared economy sink.
* **Sinks.** The listing fee (``listing_sink``) is charged on every placed
  order from its notional and is not refunded; the sales tax
  (``sales_tax_sink``) is charged per fill from the gross. Both go through
  :meth:`EconomySim.charge`, so they appear in the economy's faucet/sink
  ledger and flow reports. The base ``EconomySim.trade`` market tax is not
  used by this path.
* **Integrity.** Wash fills (same owner / linked circle) cancel the
  incoming remainder (self-trade prevention, cancel-newest). Resting orders
  that would print outside the reference band are cancelled. Fast-cancel
  spoofers are restricted. Serialized items must carry valid serials.

All money is integer, all iteration is in sorted or sequence order, and the
market's command log replays to the same :meth:`digest`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.economy.gameplay.market.book import BUY, SELL, SIDES, Order, OrderBook
from skeleton.economy.gameplay.market.errors import (
    ConservationError,
    MarketError,
    OrderRejected,
)
from skeleton.economy.gameplay.market.history import PriceHistory
from skeleton.economy.gameplay.market.integrity import (
    CIRCULAR,
    DUPLICATE,
    OUT_OF_BAND,
    SPOOF,
    WASH,
    AccountLinks,
    IncidentLog,
    ManipulationMonitor,
    SerialRegistry,
    WashTradeDetector,
)
from skeleton.economy.gameplay.market.telemetry import InflationTelemetry
from skeleton.simulation.economy.sim import _req_id, _req_int

ESCROW_OWNER = "market:escrow"
ESCROW_SLOTS = 1_000_000
ESCROW_MAX_WEIGHT = 10**15
GTC = "gtc"
IOC = "ioc"
TIFS = (GTC, IOC)


@dataclass(frozen=True)
class MarketConfig:
    currency: str
    listing_sink: str
    sales_tax_sink: str
    max_order_qty: int = 10_000
    max_unit_price: int = 10**12
    max_open_orders: int = 50
    default_ttl: int | None = 10_000
    period_ticks: int = 100
    history_retain: int = 1_000
    band_bps: int = 3_000
    ema_bps: int = 2_000
    spoof_ticks: int = 10
    spoof_window: int = 200
    spoof_ratio_bps: int = 8_000
    spoof_min_orders: int = 3
    spoof_fill_bps: int = 1_000
    penalty_ticks: int = 300
    cycle_ticks: int = 500
    max_cycle: int = 4
    basket: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        _req_id(self.currency, "currency")
        _req_id(self.listing_sink, "listing_sink")
        _req_id(self.sales_tax_sink, "sales_tax_sink")
        for name in (
            "max_order_qty",
            "max_unit_price",
            "max_open_orders",
            "period_ticks",
            "history_retain",
        ):
            _req_int(getattr(self, name), name, minimum=1)
        if self.default_ttl is not None:
            _req_int(self.default_ttl, "default_ttl", minimum=1)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["basket"] = [list(b) for b in self.basket]
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MarketConfig":
        kw = dict(data)
        kw["basket"] = tuple((str(i), int(w)) for i, w in kw.get("basket", ()))
        return cls(**kw)


class PlayerMarket:
    def __init__(
        self,
        econ: GameplayEconomy,
        config: MarketConfig,
        *,
        links: AccountLinks | None = None,
        serialized: Iterable[str] = (),
        reference_prices: Mapping[str, int] | None = None,
    ) -> None:
        self.econ = econ
        self.config = config
        self._validate_econ()
        econ.open_account(
            ESCROW_OWNER, slots=ESCROW_SLOTS, max_weight=ESCROW_MAX_WEIGHT
        )
        self.book = OrderBook()
        self.history = PriceHistory(config.period_ticks, config.history_retain)
        self.telemetry = InflationTelemetry(config.currency, dict(config.basket))
        self.wash = WashTradeDetector(
            links or AccountLinks(), config.cycle_ticks, config.max_cycle
        )
        self.monitor = ManipulationMonitor(
            band_bps=config.band_bps,
            ema_bps=config.ema_bps,
            spoof_ticks=config.spoof_ticks,
            spoof_window=config.spoof_window,
            spoof_ratio_bps=config.spoof_ratio_bps,
            spoof_min_orders=config.spoof_min_orders,
            spoof_fill_bps=config.spoof_fill_bps,
            penalty_ticks=config.penalty_ticks,
        )
        self.serials = SerialRegistry(serialized)
        for item_id in sorted(self.serials.serialized):
            self._tradeable_item(item_id)
        self.incidents = IncidentLog()
        self.claims: dict[str, dict[str, int]] = {}
        self._claim_serials: dict[str, dict[str, list[str]]] = {}
        self.log: list[dict[str, Any]] = []
        self.fills: list[dict[str, Any]] = []
        self._next_id = 1
        self._seq = 0
        self._tick = 0
        self._period: int | None = None
        for item_id, spec in sorted(econ.items.items()):
            if spec.vendor_buy_price is not None and spec.vendor_sell_price is not None:
                self.monitor.seed(
                    item_id, (spec.vendor_buy_price + spec.vendor_sell_price) // 2
                )
        for item_id, price in sorted((reference_prices or {}).items()):
            self._tradeable_item(item_id)
            self.monitor.set_reference(item_id, price)

    # -- validation ---------------------------------------------------------------
    def _validate_econ(self) -> None:
        cfg = self.config
        econ = self.econ
        if cfg.currency not in econ.currencies:
            raise MarketError("market currency is not an economy currency")
        if not econ.currencies[cfg.currency].tradeable:
            raise MarketError("market currency is not tradeable")
        for sink_id in (cfg.listing_sink, cfg.sales_tax_sink):
            spec = econ.sinks.get(sink_id)
            if spec is None or spec.currency != cfg.currency:
                raise MarketError(
                    f"{sink_id!r} must be a declared sink of {cfg.currency!r}"
                )
        if cfg.listing_sink == cfg.sales_tax_sink:
            raise MarketError("listing and sales-tax sinks must differ")

    def _tradeable_item(self, item_id: str) -> None:
        spec = self.econ.items.get(item_id)
        if spec is None:
            raise OrderRejected("no such item")
        if not spec.tradeable or spec.currency != self.config.currency:
            raise OrderRejected("item is not tradeable on this market")

    def _owner(self, owner: str) -> None:
        _req_id(owner, "owner")
        if owner == ESCROW_OWNER:
            raise OrderRejected("reserved owner")
        if owner not in self.econ.owners():
            raise OrderRejected("no such owner")

    # -- ledger primitives (econ lock held) --------------------------------------
    def _transfer(self, src: str, dst: str, amount: int, memo: str) -> None:
        if amount > 0:
            self.econ._treasuries[self.config.currency].transfer(
                src, dst, amount, memo=memo
            )

    def balance(self, owner: str) -> int:
        return self.econ.balance(owner, self.config.currency)

    def listing_fee(self, notional: int) -> int:
        return self.econ.sinks[self.config.listing_sink].amount_for(notional)

    def sales_tax(self, gross: int) -> int:
        return self.econ.sinks[self.config.sales_tax_sink].amount_for(gross)

    # -- time -----------------------------------------------------------------------
    def _advance(self, tick: int) -> None:
        _req_int(tick, "tick")
        if tick < self._tick:
            raise MarketError("tick went backwards")
        self._tick = tick
        period = self.history.period_of(tick)
        if self._period is None:
            self._period = period
        elif period > self._period:
            self._close(self._period)
            self._period = period
        for order in self.book.expired(tick):
            self._release(order, tick, "expired")

    def advance(self, tick: int) -> list[dict[str, Any]]:
        """Move the clock: expire orders and close finished periods."""
        with self.econ._lock:
            before = len(self.telemetry.rows)
            self._advance(tick)
            self.log.append({"op": "advance", "tick": tick})
            return [dict(r) for r in self.telemetry.rows[before:]]

    def _close(self, period: int) -> dict[str, int]:
        supply = self.econ.flow_report(self.config.currency)["circulating"]
        vwaps = {}
        for item_id in self.telemetry.basket:
            c = self.history.candle(item_id, period)
            vwaps[item_id] = None if c is None else c["vwap"]
        return self.telemetry.close(period, supply, self.balance(ESCROW_OWNER), vwaps)

    # -- placing orders ---------------------------------------------------------------
    def place(
        self,
        owner: str,
        side: str,
        item_id: str,
        qty: int,
        unit_price: int,
        tick: int,
        *,
        ttl: int | None = None,
        tif: str = GTC,
        serials: Iterable[str] = (),
    ) -> dict[str, Any]:
        """Place an order; returns ``{order_id, fee, fills, resting, status}``."""
        serials = tuple(serials)
        cfg = self.config
        with self.econ._lock:
            self._owner(owner)
            if side not in SIDES:
                raise OrderRejected("side must be 'sell' or 'buy'")
            if tif not in TIFS:
                raise OrderRejected("tif must be 'gtc' or 'ioc'")
            self._tradeable_item(item_id)
            _req_int(qty, "qty", minimum=1)
            _req_int(unit_price, "unit_price", minimum=1)
            if qty > cfg.max_order_qty or unit_price > cfg.max_unit_price:
                raise OrderRejected("order exceeds market limits")
            ttl = cfg.default_ttl if ttl is None else _req_int(ttl, "ttl", minimum=1)
            self._advance(tick)
            if self.monitor.is_restricted(owner, tick):
                raise OrderRejected("owner restricted for order spoofing")
            if len(self.book.orders_of(owner)) >= cfg.max_open_orders:
                raise OrderRejected("too many open orders")
            notional = qty * unit_price
            fee = self.listing_fee(notional)
            if side == SELL:
                if self.econ.free_count(owner, item_id) < qty:
                    raise OrderRejected("not enough unbound items")
                problem = self.serials.problem(item_id, owner, serials, qty)
                if problem is not None:
                    self.incidents.record(
                        tick, DUPLICATE, owner=owner, item=item_id, reason=problem
                    )
                    raise OrderRejected(f"serial check failed: {problem}")
                if self.balance(owner) < fee:
                    raise OrderRejected("insufficient funds for listing fee")
            else:
                if serials:
                    raise OrderRejected("buy requests carry no serials")
                if self.balance(owner) < notional + fee:
                    raise OrderRejected("insufficient funds for escrow and fee")
            # -- all checks passed: mutate ------------------------------------------
            if fee:
                self.econ.charge(cfg.listing_sink, owner, notional)
                self.telemetry.on_fee(self._period, fee)
            if side == SELL:
                self.econ.move_items(owner, ESCROW_OWNER, item_id, qty)
                self.serials.move(serials, ESCROW_OWNER)
            else:
                self._transfer(owner, ESCROW_OWNER, notional, f"escrow:{item_id}")
            self._seq += 1
            order = Order(
                order_id=self._next_id,
                side=side,
                owner=owner,
                item_id=item_id,
                qty=qty,
                unit_price=unit_price,
                seq=self._seq,
                tick=tick,
                expires_at=None if ttl is None else tick + ttl,
                serials=serials,
            )
            self._next_id += 1
            self.monitor.on_place(owner, tick, notional)
            fills, status = self._match(order, tick)
            if order.remaining and status == "open" and tif == GTC:
                self.book.add(order)
            elif order.remaining:
                self._refund(order, tick, "ioc" if status == "open" else status)
                status = "ioc_cancelled" if status == "open" else status
            else:
                status = "filled"
            self.log.append(
                {
                    "op": "place",
                    "owner": owner,
                    "side": side,
                    "item": item_id,
                    "qty": qty,
                    "price": unit_price,
                    "tick": tick,
                    "ttl": ttl,
                    "tif": tif,
                    "serials": list(serials),
                }
            )
            return {
                "order_id": order.order_id,
                "fee": fee,
                "fills": fills,
                "resting": order.remaining if order.order_id in self.book else 0,
                "status": status,
            }

    def _match(self, incoming: Order, tick: int) -> tuple[list[dict[str, Any]], str]:
        fills: list[dict[str, Any]] = []
        opposite = BUY if incoming.side == SELL else SELL
        for resting in self.book.iter_side(incoming.item_id, opposite):
            if not incoming.remaining:
                break
            if not incoming.crosses(resting.unit_price):
                break
            if self.wash.is_wash(incoming.owner, resting.owner):
                self.incidents.record(
                    tick,
                    WASH,
                    item=incoming.item_id,
                    incoming=incoming.owner,
                    resting=resting.owner,
                    order_id=incoming.order_id,
                )
                return fills, "wash_cancelled"
            if not self.monitor.in_band(incoming.item_id, resting.unit_price):
                self.incidents.record(
                    tick,
                    OUT_OF_BAND,
                    item=incoming.item_id,
                    order_id=resting.order_id,
                    owner=resting.owner,
                    price=resting.unit_price,
                    reference=self.monitor.reference(incoming.item_id),
                )
                self._release(resting, tick, "out_of_band")
                continue
            qty = min(incoming.remaining, resting.remaining)
            sell, buy = (
                (incoming, resting) if incoming.side == SELL else (resting, incoming)
            )
            fills.append(self._settle(sell, buy, qty, resting.unit_price, tick))
            if not resting.remaining:
                self.book.remove(resting.order_id)
        return fills, "open"

    def _settle(
        self, sell: Order, buy: Order, qty: int, price: int, tick: int
    ) -> dict[str, Any]:
        item_id = sell.item_id
        gross = qty * price
        serials = sell.serials[sell.filled : sell.filled + qty]
        sell.remaining -= qty
        buy.remaining -= qty
        if self.econ.fits_many(buy.owner, {item_id: qty}):
            self.econ.move_items(ESCROW_OWNER, buy.owner, item_id, qty)
            self.serials.move(serials, buy.owner)
            claimed = 0
        else:
            per = self.claims.setdefault(buy.owner, {})
            per[item_id] = per.get(item_id, 0) + qty
            claimed = qty
            self._claim_serials.setdefault(buy.owner, {}).setdefault(
                item_id, []
            ).extend(serials)
        self._transfer(ESCROW_OWNER, sell.owner, gross, f"settle:{item_id}")
        improvement = (buy.unit_price - price) * qty
        self._transfer(ESCROW_OWNER, buy.owner, improvement, f"improve:{item_id}")
        tax = (
            self.econ.charge(self.config.sales_tax_sink, sell.owner, gross)
            if self.sales_tax(gross)
            else 0
        )
        self.history.record(item_id, tick, price, qty)
        self.telemetry.on_fill(self._period, item_id, price, qty, tax)
        self.monitor.on_print(item_id, price)
        cycle = self.wash.observe(tick, item_id, sell.owner, buy.owner)
        if cycle is not None:
            self.incidents.record(tick, CIRCULAR, item=item_id, owners=cycle)
        fill = {
            "tick": tick,
            "item": item_id,
            "qty": qty,
            "price": price,
            "gross": gross,
            "tax": tax,
            "seller": sell.owner,
            "buyer": buy.owner,
            "sell_order": sell.order_id,
            "buy_order": buy.order_id,
            "claimed": claimed,
            "serials": list(serials),
        }
        self.fills.append(fill)
        return dict(fill)

    # -- releasing escrow -------------------------------------------------------------
    def _refund(self, order: Order, tick: int, reason: str) -> None:
        """Return what ``order`` still has in escrow (order not resting)."""
        if order.side == SELL:
            left = order.serials[order.filled :]
            if self.econ.fits_many(order.owner, {order.item_id: order.remaining}):
                self.econ.move_items(
                    ESCROW_OWNER, order.owner, order.item_id, order.remaining
                )
                self.serials.move(left, order.owner)
            else:
                per = self.claims.setdefault(order.owner, {})
                per[order.item_id] = per.get(order.item_id, 0) + order.remaining
                self._claim_serials.setdefault(order.owner, {}).setdefault(
                    order.item_id, []
                ).extend(left)
        else:
            self._transfer(
                ESCROW_OWNER,
                order.owner,
                order.remaining * order.unit_price,
                f"refund:{reason}",
            )
        order.remaining = 0

    def _release(self, order: Order, tick: int, reason: str) -> None:
        self.book.remove(order.order_id)
        self._refund(order, tick, reason)

    def cancel(self, owner: str, order_id: int, tick: int) -> dict[str, Any]:
        with self.econ._lock:
            self._advance(tick)
            order = self.book.get(order_id)
            if order is None:
                raise OrderRejected("no such open order")
            if order.owner != owner:
                raise OrderRejected("not your order")
            remaining = order.remaining
            notional = order.qty * order.unit_price
            self._release(order, tick, "cancel")
            spoof = self.monitor.on_cancel(
                owner, tick, order.tick, order.qty, remaining, notional
            )
            if spoof:
                self.incidents.record(
                    tick,
                    SPOOF,
                    owner=owner,
                    item=order.item_id,
                    until=self.monitor.restricted_until(owner),
                )
            self.log.append(
                {"op": "cancel", "owner": owner, "order_id": order_id, "tick": tick}
            )
            return {"order_id": order_id, "returned": remaining, "spoof_flagged": spoof}

    def claim(self, owner: str, item_id: str, tick: int) -> int:
        """Collect items held for ``owner`` because their bags were full."""
        with self.econ._lock:
            self._advance(tick)
            qty = self.claims.get(owner, {}).get(item_id, 0)
            if not qty:
                raise OrderRejected("nothing to claim")
            take = qty
            while take and not self.econ.fits_many(owner, {item_id: take}):
                take -= 1
            if not take:
                raise OrderRejected("inventory full")
            self.econ.move_items(ESCROW_OWNER, owner, item_id, take)
            pending = self._claim_serials.get(owner, {}).get(item_id, [])
            self.serials.move(pending[:take], owner)
            del pending[:take]
            if qty == take:
                del self.claims[owner][item_id]
                if not self.claims[owner]:
                    del self.claims[owner]
            else:
                self.claims[owner][item_id] = qty - take
            self.log.append(
                {"op": "claim", "owner": owner, "item": item_id, "tick": tick}
            )
            return take

    # -- serials --------------------------------------------------------------------
    def mint_serialized(
        self, source: str, owner: str, item_id: str, serials: Iterable[str]
    ) -> int:
        """Item faucet for serialized items: grant and register in one step."""
        serials = tuple(serials)
        with self.econ._lock:
            self._owner(owner)
            if not self.serials.is_serialized(item_id):
                raise MarketError("item is not serialized")
            if not serials or len(set(serials)) != len(serials):
                raise MarketError("need distinct serials")
            for s in serials:
                if self.serials.holder(s) is not None:
                    self.incidents.record(
                        self._tick,
                        DUPLICATE,
                        owner=owner,
                        item=item_id,
                        reason=f"serial {s} exists",
                    )
                    raise MarketError("serial already exists")
            self.econ.grant_items(source, owner, item_id, len(serials))
            for s in serials:
                self.serials.register(item_id, owner, s)
            self.log.append(
                {
                    "op": "mint_serialized",
                    "source": source,
                    "owner": owner,
                    "item": item_id,
                    "serials": list(serials),
                }
            )
            return len(serials)

    # -- inspection ----------------------------------------------------------------
    def quote(self, item_id: str, levels: int = 5) -> dict[str, Any]:
        return {
            "item": item_id,
            "bid": self.book.best_price(item_id, BUY),
            "ask": self.book.best_price(item_id, SELL),
            "spread": self.book.spread(item_id),
            "bids": self.book.depth(item_id, BUY, levels),
            "asks": self.book.depth(item_id, SELL, levels),
            "reference": self.monitor.reference(item_id),
            "last": self.history.last_price(item_id),
        }

    def open_orders(self, owner: str | None = None) -> list[dict[str, Any]]:
        orders = self.book.orders() if owner is None else self.book.orders_of(owner)
        return [o.to_dict() for o in orders]

    def audit(self) -> dict[str, Any]:
        """Escrow and ledger conservation. ``ok`` is the conjunction of all checks."""
        with self.econ._lock:
            money_expected = sum(
                o.remaining * o.unit_price for o in self.book.orders() if o.side == BUY
            )
            money_held = self.balance(ESCROW_OWNER)
            items_held = dict(self.econ.inventory(ESCROW_OWNER).stacks)
            items_expected: dict[str, int] = {}
            for o in self.book.orders():
                if o.side == SELL:
                    items_expected[o.item_id] = (
                        items_expected.get(o.item_id, 0) + o.remaining
                    )
            for per in self.claims.values():
                for item_id, qty in per.items():
                    items_expected[item_id] = items_expected.get(item_id, 0) + qty
            counts = {}
            for owner in self.econ.owners():
                for item_id, qty in self.econ.inventory(owner).stacks.items():
                    counts[(owner, item_id)] = qty
            serial_audit = self.serials.audit(counts)
            econ_audit = self.econ.audit()
            item_audit = self.econ.item_audit()
            checks = {
                "escrow_money": money_held == money_expected,
                "escrow_items": items_held == items_expected,
                "serials": serial_audit["ok"],
                "economy": econ_audit["ok"],
                "items": item_audit["ok"],
            }
            return {
                "ok": all(checks.values()),
                "checks": checks,
                "escrow_money": {"held": money_held, "expected": money_expected},
                "escrow_items": {"held": items_held, "expected": items_expected},
                "serial_problems": serial_audit["problems"],
            }

    def require_conserved(self) -> None:
        report = self.audit()
        if not report["ok"]:
            raise ConservationError(f"market books do not balance: {report['checks']}")

    def sink_report(self) -> dict[str, int]:
        flows = self.econ.flow_report(self.config.currency)["by_sink"]
        return {
            "listing_fees": flows.get(self.config.listing_sink, 0),
            "sales_tax": flows.get(self.config.sales_tax_sink, 0),
        }

    # -- state -----------------------------------------------------------------------
    def to_state(self) -> dict[str, Any]:
        with self.econ._lock:
            return {
                "config": self.config.to_dict(),
                "orders": [o.to_dict() for o in self.book.orders()],
                "next_id": self._next_id,
                "seq": self._seq,
                "tick": self._tick,
                "period": self._period,
                "claims": {
                    o: dict(sorted(c.items())) for o, c in sorted(self.claims.items())
                },
                "claim_serials": {
                    o: {i: list(s) for i, s in sorted(per.items()) if s}
                    for o, per in sorted(self._claim_serials.items())
                },
                "history": self.history.to_state(),
                "telemetry": self.telemetry.to_state(),
                "wash": self.wash.to_state(),
                "monitor": self.monitor.to_state(),
                "serials": self.serials.to_state(),
                "incidents": [dict(r) for r in self.incidents.rows],
                "fills": [dict(f) for f in self.fills],
            }

    @classmethod
    def from_state(
        cls, econ: GameplayEconomy, state: Mapping[str, Any]
    ) -> "PlayerMarket":
        """Rebuild a market over an already-restored economy (escrow included)."""
        config = MarketConfig.from_dict(state["config"])
        market = cls(econ, config, serialized=state["serials"]["serialized"])
        market._next_id = int(state["next_id"])
        market._seq = int(state["seq"])
        market._tick = int(state["tick"])
        market._period = None if state["period"] is None else int(state["period"])
        for row in state["orders"]:
            market.book.add(Order.from_dict(row))
        market.claims = {
            o: {i: int(q) for i, q in c.items()} for o, c in state["claims"].items()
        }
        market._claim_serials = {
            o: {i: list(s) for i, s in per.items()}
            for o, per in state.get("claim_serials", {}).items()
        }
        market.history = PriceHistory.from_state(state["history"])
        market.telemetry = InflationTelemetry.from_state(state["telemetry"])
        market.wash = WashTradeDetector.from_state(state["wash"])
        market.monitor = ManipulationMonitor.from_state(state["monitor"])
        market.serials = SerialRegistry.from_state(state["serials"])
        market.incidents = IncidentLog([dict(r) for r in state["incidents"]])
        market.fills = [dict(f) for f in state["fills"]]
        return market

    def digest(self) -> str:
        """sha256 over economy snapshot plus market state (replay contract)."""
        payload = json.dumps(
            {"econ": self.econ.snapshot(), "market": self.to_state()},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["ESCROW_OWNER", "GTC", "IOC", "MarketConfig", "PlayerMarket"]
