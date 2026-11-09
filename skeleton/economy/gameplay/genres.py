"""B030 genre composition for economies.

A :class:`GenreEconomy` is a reusable bundle of currencies, items, faucets,
sinks and inventory defaults for one genre. Presets for common genres ship
in :data:`PRESETS`; :func:`compose` merges several (an "RPG + survival"
hybrid) and fails closed on any id defined differently by two parts.
:func:`lint` enforces design health before an economy is built: every
currency needs at least one faucet and at least one sink (no dead-end or
ever-growing currencies), and every item needs a way in and a way out.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.simulation.economy.sim import (
    MAX_MARKET_TAX_BPS,
    CurrencySpec,
    EconomySimError,
    FaucetSpec,
    ItemSpec,
    SinkSpec,
    _req_id,
)


@dataclass(frozen=True)
class GenreEconomy:
    name: str
    currencies: tuple[CurrencySpec, ...] = ()
    items: tuple[ItemSpec, ...] = ()
    faucets: tuple[FaucetSpec, ...] = ()
    sinks: tuple[SinkSpec, ...] = ()
    item_weights: tuple[tuple[str, int], ...] = ()
    item_sources: tuple[str, ...] = ()
    item_sinks: tuple[str, ...] = ()
    market_tax_bps: int = 0
    default_slots: int = 32
    default_max_weight: int | None = None
    tags: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        _req_id(self.name, "genre name")

    def build(self, *, check: bool = True) -> GameplayEconomy:
        if check:
            problems = lint(self)
            if problems:
                raise EconomySimError("genre economy failed lint: " + "; ".join(problems))
        return GameplayEconomy(
            self.currencies,
            self.items,
            self.faucets,
            self.sinks,
            market_tax_bps=self.market_tax_bps,
            default_slots=self.default_slots,
            item_weights=dict(self.item_weights),
            default_max_weight=self.default_max_weight,
        )


def lint(genre: GenreEconomy) -> list[str]:
    """Design-health problems; an empty list means the economy can close its loops."""
    problems: list[str] = []
    for cur in genre.currencies:
        cid = cur.currency_id
        has_faucet = any(f.currency == cid for f in genre.faucets) or any(
            i.currency == cid and i.vendor_sell_price for i in genre.items
        )
        has_sink = any(s.currency == cid for s in genre.sinks) or any(
            i.currency == cid and i.vendor_buy_price for i in genre.items
        ) or (cur.tradeable and genre.market_tax_bps > 0)
        if not has_faucet:
            problems.append(f"currency {cid} has no faucet")
        if not has_sink:
            problems.append(f"currency {cid} has no sink")
    sources = set(genre.item_sources)
    sinks = set(genre.item_sinks)
    for item in genre.items:
        entry = item.vendor_buy_price is not None or item.item_id in sources
        exit_ = item.vendor_sell_price is not None or item.item_id in sinks
        if not entry:
            problems.append(f"item {item.item_id} can never be obtained")
        if not exit_:
            problems.append(f"item {item.item_id} can never leave the economy")
    return problems


def _merge(kind: str, key: str, *groups: tuple[Any, ...]) -> tuple[Any, ...]:
    out: dict[str, Any] = {}
    for group in groups:
        for spec in group:
            ident = getattr(spec, key)
            if ident in out and out[ident] != spec:
                raise EconomySimError(f"conflicting {kind} {ident!r}")
            out[ident] = spec
    return tuple(out[k] for k in sorted(out))


def compose(name: str, *parts: GenreEconomy, market_tax_bps: int | None = None) -> GenreEconomy:
    """Merge genre economies; identical specs dedupe, conflicting ones refuse."""
    if not parts:
        raise EconomySimError("compose needs at least one genre")
    weights: dict[str, int] = {}
    for part in parts:
        for item_id, w in part.item_weights:
            if weights.get(item_id, w) != w:
                raise EconomySimError(f"conflicting weight for {item_id!r}")
            weights[item_id] = w
    taxes = {p.market_tax_bps for p in parts}
    if market_tax_bps is None:
        if len(taxes) > 1:
            raise EconomySimError("parts disagree on market tax; pass market_tax_bps")
        market_tax_bps = taxes.pop()
    if market_tax_bps > MAX_MARKET_TAX_BPS:
        raise EconomySimError("market tax above ceiling")
    caps = [p.default_max_weight for p in parts if p.default_max_weight is not None]
    return GenreEconomy(
        name=name,
        currencies=_merge("currency", "currency_id", *(p.currencies for p in parts)),
        items=_merge("item", "item_id", *(p.items for p in parts)),
        faucets=_merge("faucet", "faucet_id", *(p.faucets for p in parts)),
        sinks=_merge("sink", "sink_id", *(p.sinks for p in parts)),
        item_weights=tuple(sorted(weights.items())),
        item_sources=tuple(sorted({s for p in parts for s in p.item_sources})),
        item_sinks=tuple(sorted({s for p in parts for s in p.item_sinks})),
        market_tax_bps=market_tax_bps,
        default_slots=max(p.default_slots for p in parts),
        default_max_weight=min(caps) if caps else None,
        tags=frozenset().union(*(p.tags for p in parts)) | {f"composed:{p.name}" for p in parts},
    )


RPG = GenreEconomy(
    name="rpg",
    currencies=(CurrencySpec("gold"),),
    items=(
        ItemSpec("potion", "gold", max_stack=20, vendor_buy_price=50, vendor_sell_price=10),
        ItemSpec("sword", "gold", max_stack=1, vendor_buy_price=400, vendor_sell_price=100),
        ItemSpec("relic", "gold", max_stack=1, vendor_sell_price=250),
    ),
    faucets=(FaucetSpec("quest_gold", "gold", amount=150, cooldown_ticks=60),),
    sinks=(SinkSpec("repair", "gold", flat=5, bps=1_000), SinkSpec("fast_travel", "gold", flat=20)),
    item_sources=("relic",),
    item_sinks=("potion",),
    market_tax_bps=0,
    default_slots=40,
    tags=frozenset({"single-player"}),
)

SURVIVAL = GenreEconomy(
    name="survival",
    currencies=(CurrencySpec("scrap"),),
    items=(
        ItemSpec("wood", "scrap", max_stack=50, vendor_sell_price=1),
        ItemSpec("ration", "scrap", max_stack=10, vendor_buy_price=8, vendor_sell_price=2),
    ),
    faucets=(FaucetSpec("salvage", "scrap", amount=5, cooldown_ticks=5, window_ticks=100, window_cap=50),),
    sinks=(SinkSpec("base_upkeep", "scrap", flat=10),),
    item_weights=(("wood", 2), ("ration", 1)),
    item_sources=("wood",),
    item_sinks=("wood", "ration"),
    default_slots=24,
    default_max_weight=200,
    tags=frozenset({"crafting", "weight"}),
)

MMO = GenreEconomy(
    name="mmo",
    currencies=(CurrencySpec("gold"), CurrencySpec("honor", supply_cap=10_000_000, tradeable=False)),
    items=(
        ItemSpec("potion", "gold", max_stack=20, vendor_buy_price=50, vendor_sell_price=10),
        ItemSpec("ore", "gold", max_stack=200, vendor_sell_price=2),
        ItemSpec("pvp_badge", "honor", max_stack=1, vendor_buy_price=500, tradeable=False),
    ),
    faucets=(
        FaucetSpec("daily_gold", "gold", amount=500, cooldown_ticks=1_440),
        FaucetSpec("arena_honor", "honor", amount=25, window_ticks=1_440, window_cap=500),
    ),
    sinks=(SinkSpec("auction_listing", "gold", flat=1, bps=100), SinkSpec("respec", "honor", flat=100)),
    item_sources=("ore",),
    item_sinks=("potion", "pvp_badge"),
    market_tax_bps=500,
    default_slots=60,
    tags=frozenset({"multiplayer", "market"}),
)

ROGUELITE = GenreEconomy(
    name="roguelite",
    currencies=(CurrencySpec("shards", supply_cap=1_000_000, tradeable=False),),
    items=(ItemSpec("key", "shards", max_stack=9, vendor_buy_price=30, tradeable=False),),
    faucets=(FaucetSpec("run_reward", "shards", amount=40, cooldown_ticks=1),),
    sinks=(SinkSpec("meta_unlock", "shards", flat=200), SinkSpec("reroll", "shards", flat=15)),
    item_sinks=("key",),
    default_slots=8,
    tags=frozenset({"meta-progression"}),
)

PRESETS: dict[str, GenreEconomy] = {g.name: g for g in (RPG, SURVIVAL, MMO, ROGUELITE)}


def preset(name: str, /, **overrides: Any) -> GenreEconomy:
    if name not in PRESETS:
        raise EconomySimError(f"unknown genre {name!r}")
    return replace(PRESETS[name], **overrides) if overrides else PRESETS[name]


__all__ = ["PRESETS", "GenreEconomy", "compose", "lint", "preset"]
