"""Economy simulation slice for #807 (B021–B030 gameplay lane).

Currencies, inventories, faucets and sinks on top of the double-entry
:class:`~skeleton.simulation.economy.treasury.Treasury`.

Design rules (fail closed, deterministic, no floats for money):

* Every currency owns its own ``Treasury``. Money only enters through a
  declared *faucet* (a provenance-tagged mint) and only leaves through a
  declared *sink* (a transfer into the currency's burn account). There is no
  third path, so ``circulating == minted - burned`` is an audited invariant.
* Faucets carry a per-owner cooldown and a rolling per-window cap, and every
  currency may declare a hard supply cap. Time is a caller-supplied integer
  tick, so a replay with the same inputs yields the same books and digest.
* Items live in slot-bounded, stack-bounded inventories. NPC vendors are a
  paired sink (buy) and faucet (sell); a minimum buy/sell spread is enforced
  at definition time so no item can be cycled through a vendor for profit.
* Player-to-player trades move money between owners and burn a market tax
  from the seller's proceeds, an EVE-style transaction-tax sink.
* Each mutation validates funds, stock and capacity before touching any
  book, so a refused operation leaves balances and inventories unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Iterable

from skeleton.simulation.economy.treasury import Treasury, TreasuryError

BPS = 10_000
BURN_ACCOUNT = "__sink__"
MIN_VENDOR_SPREAD_BPS = 500
MAX_MARKET_TAX_BPS = 5_000
VENDOR_FAUCET = "vendor_sell"
VENDOR_SINK = "vendor_buy"
MARKET_TAX_SINK = "market_tax"
_ID = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")


class EconomySimError(TreasuryError):
    """Economy simulation refusal: bad spec, cap, cooldown, stock or capacity."""

    code = "ECO.SIM"
    http_status = 400


def _req_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID.match(value):
        raise EconomySimError(f"invalid {label}")
    return value


def _req_int(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EconomySimError(f"invalid {label}")
    return value


def _bps_of(amount: int, bps: int) -> int:
    """Ceil ``amount * bps / BPS`` in integers, so fees never round to free."""
    return -(-amount * bps // BPS)


@dataclass(frozen=True)
class CurrencySpec:
    currency_id: str
    supply_cap: int | None = None
    tradeable: bool = True

    def __post_init__(self) -> None:
        _req_id(self.currency_id, "currency_id")
        if self.supply_cap is not None:
            _req_int(self.supply_cap, "supply_cap", minimum=1)


@dataclass(frozen=True)
class ItemSpec:
    item_id: str
    currency: str
    max_stack: int = 1
    vendor_buy_price: int | None = None
    vendor_sell_price: int | None = None
    tradeable: bool = True

    def __post_init__(self) -> None:
        _req_id(self.item_id, "item_id")
        _req_id(self.currency, "item currency")
        _req_int(self.max_stack, "max_stack", minimum=1)
        if self.vendor_buy_price is not None:
            _req_int(self.vendor_buy_price, "vendor_buy_price", minimum=1)
        if self.vendor_sell_price is not None:
            _req_int(self.vendor_sell_price, "vendor_sell_price", minimum=1)
            if self.vendor_buy_price is not None:
                ceiling = self.vendor_buy_price - _bps_of(self.vendor_buy_price, MIN_VENDOR_SPREAD_BPS)
                if self.vendor_sell_price > ceiling:
                    raise EconomySimError("vendor spread too thin: buy/sell loop would be a faucet")


@dataclass(frozen=True)
class FaucetSpec:
    faucet_id: str
    currency: str
    amount: int
    cooldown_ticks: int = 0
    window_ticks: int = 0
    window_cap: int | None = None

    def __post_init__(self) -> None:
        _req_id(self.faucet_id, "faucet_id")
        _req_id(self.currency, "faucet currency")
        _req_int(self.amount, "faucet amount", minimum=1)
        _req_int(self.cooldown_ticks, "cooldown_ticks")
        _req_int(self.window_ticks, "window_ticks")
        if self.window_cap is not None:
            _req_int(self.window_cap, "window_cap", minimum=1)
            if self.window_ticks < 1:
                raise EconomySimError("window_cap requires window_ticks >= 1")


@dataclass(frozen=True)
class SinkSpec:
    sink_id: str
    currency: str
    flat: int = 0
    bps: int = 0

    def __post_init__(self) -> None:
        _req_id(self.sink_id, "sink_id")
        _req_id(self.currency, "sink currency")
        _req_int(self.flat, "sink flat")
        _req_int(self.bps, "sink bps")
        if self.bps > BPS:
            raise EconomySimError("sink bps above 100%")
        if self.flat == 0 and self.bps == 0:
            raise EconomySimError("sink must remove something")

    def amount_for(self, base: int = 0) -> int:
        _req_int(base, "sink base")
        return self.flat + _bps_of(base, self.bps)


@dataclass
class Inventory:
    """Slot-bounded, stack-bounded item holdings for one owner."""

    owner: str
    slots: int
    stacks: dict[str, int] = field(default_factory=dict)

    def slots_used(self, specs: dict[str, ItemSpec], stacks: dict[str, int] | None = None) -> int:
        held = self.stacks if stacks is None else stacks
        return sum(-(-qty // specs[item].max_stack) for item, qty in held.items() if qty > 0)

    def count(self, item_id: str) -> int:
        return self.stacks.get(item_id, 0)

    def fits(self, specs: dict[str, ItemSpec], item_id: str, qty: int) -> bool:
        after = dict(self.stacks)
        after[item_id] = after.get(item_id, 0) + qty
        return self.slots_used(specs, after) <= self.slots

    def to_dict(self) -> dict[str, Any]:
        return {"owner": self.owner, "slots": self.slots, "stacks": dict(sorted(self.stacks.items()))}


@dataclass
class _Flows:
    minted: int = 0
    burned: int = 0
    by_faucet: dict[str, int] = field(default_factory=dict)
    by_sink: dict[str, int] = field(default_factory=dict)


class EconomySim:
    """Deterministic multi-currency economy with declared faucets and sinks."""

    def __init__(
        self,
        currencies: Iterable[CurrencySpec],
        items: Iterable[ItemSpec] = (),
        faucets: Iterable[FaucetSpec] = (),
        sinks: Iterable[SinkSpec] = (),
        *,
        market_tax_bps: int = 0,
        default_slots: int = 32,
    ) -> None:
        self._lock = threading.RLock()
        self.currencies = self._index(currencies, "currency_id")
        self.items = self._index(items, "item_id")
        self.faucets = self._index(faucets, "faucet_id")
        self.sinks = self._index(sinks, "sink_id")
        if not self.currencies:
            raise EconomySimError("at least one currency is required")
        for spec in [*self.items.values(), *self.faucets.values(), *self.sinks.values()]:
            if spec.currency not in self.currencies:
                raise EconomySimError(f"unknown currency {spec.currency!r}")
        reserved = {VENDOR_FAUCET, VENDOR_SINK, MARKET_TAX_SINK}
        if reserved & (set(self.faucets) | set(self.sinks)):
            raise EconomySimError("faucet/sink id collides with a reserved flow id")
        self.market_tax_bps = _req_int(market_tax_bps, "market_tax_bps")
        if market_tax_bps > MAX_MARKET_TAX_BPS:
            raise EconomySimError("market tax above ceiling")
        self.default_slots = _req_int(default_slots, "default_slots", minimum=1)
        self._treasuries: dict[str, Treasury] = {}
        self._flows: dict[str, _Flows] = {}
        for cid in self.currencies:
            treasury = Treasury()
            treasury.open_account(BURN_ACCOUNT)
            self._treasuries[cid] = treasury
            self._flows[cid] = _Flows()
        self._inventories: dict[str, Inventory] = {}
        self._seq = 0
        self._last_grant: dict[tuple[str, str], int] = {}
        self._window_grants: dict[tuple[str, str], list[tuple[int, int]]] = {}

    @staticmethod
    def _index(specs: Iterable[Any], key: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for spec in specs:
            ident = getattr(spec, key)
            if ident in out:
                raise EconomySimError(f"duplicate {key} {ident!r}")
            out[ident] = spec
        return out

    # -- accounts -------------------------------------------------------
    def open_account(self, owner: str, *, slots: int | None = None) -> None:
        _req_id(owner, "owner")
        if owner == BURN_ACCOUNT:
            raise EconomySimError("reserved owner")
        with self._lock:
            for treasury in self._treasuries.values():
                treasury.open_account(owner)
            if owner not in self._inventories:
                size = self.default_slots if slots is None else _req_int(slots, "slots", minimum=1)
                self._inventories[owner] = Inventory(owner=owner, slots=size)

    def _owner(self, owner: str) -> Inventory:
        inv = self._inventories.get(owner)
        if inv is None:
            raise EconomySimError("no such owner")
        return inv

    def _currency(self, currency: str) -> Treasury:
        treasury = self._treasuries.get(currency)
        if treasury is None:
            raise EconomySimError("no such currency")
        return treasury

    def balance(self, owner: str, currency: str) -> int:
        with self._lock:
            self._owner(owner)
            acc = self._currency(currency).account(owner)
            return 0 if acc is None else acc.balance

    def inventory(self, owner: str) -> Inventory:
        with self._lock:
            inv = self._owner(owner)
            return Inventory(owner=inv.owner, slots=inv.slots, stacks=dict(inv.stacks))

    def _item(self, item_id: str) -> ItemSpec:
        spec = self.items.get(item_id)
        if spec is None:
            raise EconomySimError("no such item")
        return spec

    # -- primitive flows (caller holds the lock) -------------------------
    def _circulating(self, currency: str) -> int:
        flows = self._flows[currency]
        return flows.minted - flows.burned

    def _mint(self, currency: str, owner: str, amount: int, source: str, provenance: str) -> None:
        cap = self.currencies[currency].supply_cap
        if cap is not None and self._circulating(currency) + amount > cap:
            raise EconomySimError("supply cap reached")
        self._treasuries[currency].mint(owner, amount, provenance, memo=source)
        flows = self._flows[currency]
        flows.minted += amount
        flows.by_faucet[source] = flows.by_faucet.get(source, 0) + amount

    def _burn(self, currency: str, owner: str, amount: int, sink: str) -> None:
        if amount <= 0:
            return
        self._treasuries[currency].transfer(owner, BURN_ACCOUNT, amount, memo=sink)
        flows = self._flows[currency]
        flows.burned += amount
        flows.by_sink[sink] = flows.by_sink.get(sink, 0) + amount

    def _require_funds(self, currency: str, owner: str, amount: int) -> None:
        if self.balance(owner, currency) < amount:
            raise EconomySimError("insufficient funds")

    # -- faucets ---------------------------------------------------------
    def grant(self, faucet_id: str, owner: str, tick: int) -> int:
        """Pay a declared faucet to ``owner`` at ``tick``; returns the amount minted."""
        _req_int(tick, "tick")
        with self._lock:
            spec = self.faucets.get(faucet_id)
            if spec is None:
                raise EconomySimError("no such faucet")
            self._owner(owner)
            key = (faucet_id, owner)
            last = self._last_grant.get(key)
            if last is not None and tick < last:
                raise EconomySimError("tick went backwards")
            if last is not None and tick - last < spec.cooldown_ticks:
                raise EconomySimError("faucet on cooldown")
            window = self._window_grants.setdefault(key, [])
            if spec.window_cap is not None:
                window[:] = [(t, a) for t, a in window if tick - t < spec.window_ticks]
                if sum(a for _, a in window) + spec.amount > spec.window_cap:
                    raise EconomySimError("faucet window cap reached")
            self._mint(spec.currency, owner, spec.amount, faucet_id, f"faucet:{faucet_id}:{owner}:{tick}")
            self._last_grant[key] = tick
            if spec.window_cap is not None:
                window.append((tick, spec.amount))
            return spec.amount

    # -- sinks -----------------------------------------------------------
    def charge(self, sink_id: str, owner: str, base: int = 0) -> int:
        """Burn a declared sink from ``owner`` (flat + bps of ``base``); returns the burn."""
        with self._lock:
            spec = self.sinks.get(sink_id)
            if spec is None:
                raise EconomySimError("no such sink")
            self._owner(owner)
            amount = spec.amount_for(base)
            self._require_funds(spec.currency, owner, amount)
            self._burn(spec.currency, owner, amount, sink_id)
            return amount

    # -- items -----------------------------------------------------------
    def vendor_buy(self, owner: str, item_id: str, qty: int = 1) -> int:
        """Buy from an NPC vendor: money is burned, items appear. Returns cost."""
        _req_int(qty, "qty", minimum=1)
        with self._lock:
            spec = self._item(item_id)
            inv = self._owner(owner)
            if spec.vendor_buy_price is None:
                raise EconomySimError("vendor does not sell this item")
            cost = spec.vendor_buy_price * qty
            self._require_funds(spec.currency, owner, cost)
            if not inv.fits(self.items, item_id, qty):
                raise EconomySimError("inventory full")
            self._burn(spec.currency, owner, cost, VENDOR_SINK)
            inv.stacks[item_id] = inv.count(item_id) + qty
            return cost

    def vendor_sell(self, owner: str, item_id: str, qty: int = 1) -> int:
        """Sell to an NPC vendor: items vanish, money is minted. Returns proceeds."""
        _req_int(qty, "qty", minimum=1)
        with self._lock:
            spec = self._item(item_id)
            inv = self._owner(owner)
            if spec.vendor_sell_price is None:
                raise EconomySimError("vendor does not buy this item")
            if inv.count(item_id) < qty:
                raise EconomySimError("not enough items")
            proceeds = spec.vendor_sell_price * qty
            self._seq += 1
            provenance = f"{VENDOR_FAUCET}:{owner}:{item_id}:{qty}:{self._seq}"
            self._mint(spec.currency, owner, proceeds, VENDOR_FAUCET, provenance)
            self._take(inv, item_id, qty)
            return proceeds

    @staticmethod
    def _take(inv: Inventory, item_id: str, qty: int) -> None:
        left = inv.count(item_id) - qty
        if left:
            inv.stacks[item_id] = left
        else:
            inv.stacks.pop(item_id, None)

    def trade(self, seller: str, buyer: str, item_id: str, qty: int, price: int) -> dict[str, int]:
        """Player market fill: buyer pays seller, seller pays the burned market tax."""
        _req_int(qty, "qty", minimum=1)
        _req_int(price, "price", minimum=1)
        if seller == buyer:
            raise EconomySimError("wash trade refused")
        with self._lock:
            spec = self._item(item_id)
            if not spec.tradeable or not self.currencies[spec.currency].tradeable:
                raise EconomySimError("item or currency is not tradeable")
            s_inv = self._owner(seller)
            b_inv = self._owner(buyer)
            if s_inv.count(item_id) < qty:
                raise EconomySimError("seller lacks items")
            self._require_funds(spec.currency, buyer, price)
            if not b_inv.fits(self.items, item_id, qty):
                raise EconomySimError("buyer inventory full")
            tax = _bps_of(price, self.market_tax_bps)
            self._treasuries[spec.currency].transfer(buyer, seller, price, memo=f"trade:{item_id}")
            self._burn(spec.currency, seller, tax, MARKET_TAX_SINK)
            self._take(s_inv, item_id, qty)
            b_inv.stacks[item_id] = b_inv.count(item_id) + qty
            return {"price": price, "tax": tax, "seller_net": price - tax}

    # -- telemetry / audit ----------------------------------------------
    def flow_report(self, currency: str) -> dict[str, Any]:
        with self._lock:
            self._currency(currency)
            flows = self._flows[currency]
            return {
                "currency": currency,
                "minted": flows.minted,
                "burned": flows.burned,
                "circulating": flows.minted - flows.burned,
                "supply_cap": self.currencies[currency].supply_cap,
                "by_faucet": dict(sorted(flows.by_faucet.items())),
                "by_sink": dict(sorted(flows.by_sink.items())),
                "sink_to_faucet_bps": (flows.burned * BPS // flows.minted) if flows.minted else 0,
            }

    def audit(self) -> dict[str, Any]:
        """Check books per currency: circulating == minted - burned, caps held."""
        with self._lock:
            per: dict[str, Any] = {}
            ok = True
            for cid, treasury in self._treasuries.items():
                flows = self._flows[cid]
                held = sum(a.balance for a in treasury.accounts() if a.name != BURN_ACCOUNT)
                burn = treasury.account(BURN_ACCOUNT)
                burned = 0 if burn is None else burn.balance
                cap = self.currencies[cid].supply_cap
                balanced = (
                    held == flows.minted - flows.burned
                    and burned == flows.burned
                    and treasury.audit()["window_balanced"]
                    and (cap is None or held <= cap)
                )
                ok = ok and balanced
                per[cid] = {"held": held, "minted": flows.minted, "burned": burned, "balanced": balanced}
            return {"ok": ok, "currencies": per}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            balances = {
                cid: {a.name: a.balance for a in sorted(t.accounts(), key=lambda a: a.name)}
                for cid, t in sorted(self._treasuries.items())
            }
            inventories = {o: inv.to_dict() for o, inv in sorted(self._inventories.items())}
            return {"balances": balances, "inventories": inventories}

    def digest(self) -> str:
        """Stable sha256 over balances and inventories, for replay contracts."""
        payload = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "BURN_ACCOUNT",
    "MARKET_TAX_SINK",
    "MIN_VENDOR_SPREAD_BPS",
    "VENDOR_FAUCET",
    "VENDOR_SINK",
    "CurrencySpec",
    "EconomySim",
    "EconomySimError",
    "FaucetSpec",
    "Inventory",
    "ItemSpec",
    "SinkSpec",
]
