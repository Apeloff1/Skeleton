"""Deterministic original NPC schedules, relationships and finite shop economy.

A society block is optional. No legacy Director world, action, save or hash
changes without an explicitly reviewed society rule set. NPC interactions
are NOT an LLM hallucination: a player earns persistent trust by actually
speaking to the right character at the right time; a transaction consumes
real money and changes finite merchant stock and player inventory.

Time is measured in authoritative Director turns; there are four scheduled
phases, but the phase length is authored. No background tasks, wall-clock
drift, third-party economy, player telemetry, scripts or network I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

ID = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
SCHEMA = "skeleton.game_builder.society.v1"
MAX_RESIDENTS = 512
MAX_SHOPS = 256
MAX_GOODS = 1024
MAX_BALANCE = 1_000_000_000
PHASES = ("dawn", "day", "dusk", "night")


def _id(value: Any) -> str:
    if type(value) is not str or ID.fullmatch(value) is None:
        raise ValueError("society IDs must be safe 1..64 lowercase identifiers")
    return value


def _int(value: Any, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError("society amount is missing, unbounded or not an integer")
    return value


def _label(value: Any, limit: int = 280) -> str:
    if (type(value) is not str or not 1 <= len(value) <= limit
            or value.strip() != value or any(ord(ch) < 32 for ch in value)):
        raise ValueError("unprintable or invalid society dialogue/name")
    return value


def _exact(value: Any, keys: set[str], subject: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(subject + " requires exact typed schema")
    return value


@dataclass(frozen=True, slots=True)
class TrustRequirement:
    resident: str
    at_least: int = -100
    at_most: int = 100

    def __post_init__(self):
        _id(self.resident)
        _int(self.at_least, -100, 100)
        _int(self.at_most, -100, 100)
        if self.at_least > self.at_most:
            raise ValueError("minimum NPC trust exceeds maximum")

    def payload(self):
        return {"resident": self.resident, "at_least": self.at_least,
                "at_most": self.at_most}


@dataclass(frozen=True, slots=True)
class Resident:
    key: str
    name: str
    faction: str | None
    schedule: tuple[str, str, str, str]
    greeting: str
    initial_trust: int = 0
    trust_gain: int = 10
    reputation_gain: int = 0
    unlock_at_trust: int = 60
    unlock_world_flag: str | None = None

    def __post_init__(self):
        _id(self.key)
        _label(self.name, 120)
        _label(self.greeting, 480)
        if self.faction is not None:
            _id(self.faction)
        if not isinstance(self.schedule, tuple) or len(self.schedule) != 4:
            raise ValueError("NPC requires dawn, day, dusk and night locations")
        for scene in self.schedule:
            _id(scene)
        _int(self.initial_trust, -100, 100)
        _int(self.trust_gain, -30, 30)
        _int(self.reputation_gain, -20, 20)
        _int(self.unlock_at_trust, -100, 100)
        if self.unlock_world_flag is not None:
            _id(self.unlock_world_flag)
        if self.reputation_gain and self.faction is None:
            raise ValueError("NPC cannot alter an unspecified faction")

    def payload(self):
        return {"key": self.key, "name": self.name,
                "faction": self.faction, "schedule": list(self.schedule),
                "greeting": self.greeting, "initial_trust": self.initial_trust,
                "trust_gain": self.trust_gain,
                "reputation_gain": self.reputation_gain,
                "unlock_at_trust": self.unlock_at_trust,
                "unlock_world_flag": self.unlock_world_flag}


@dataclass(frozen=True, slots=True)
class Good:
    key: str
    name: str
    buy_price: int
    sell_price: int
    starting_stock: int

    def __post_init__(self):
        _id(self.key)
        _label(self.name, 120)
        _int(self.buy_price, 1, 1_000_000)
        _int(self.sell_price, 0, 1_000_000)
        _int(self.starting_stock, 0, 100_000)
        if self.sell_price > self.buy_price:
            raise ValueError("shop prices permit a no-risk buy/sell money exploit")

    def payload(self):
        return {"key": self.key, "name": self.name,
                "buy_price": self.buy_price, "sell_price": self.sell_price,
                "starting_stock": self.starting_stock}


@dataclass(frozen=True, slots=True)
class Shop:
    key: str
    keeper: str
    scene: str
    name: str
    goods: tuple[Good, ...]

    def __post_init__(self):
        _id(self.key)
        _id(self.keeper)
        _id(self.scene)
        _label(self.name, 140)
        if not isinstance(self.goods, tuple) or not 1 <= len(self.goods) <= 64:
            raise ValueError("original merchant requires 1..64 actual goods")
        if any(not isinstance(item, Good) for item in self.goods):
            raise ValueError("untyped merchandise")
        if len({item.key for item in self.goods}) != len(self.goods):
            raise ValueError("duplicate product in shop")
        for good in self.goods:
            if len(self.key + "_" + good.key) > 64:
                raise ValueError("shop/product IDs cannot form a legal Director action")

    def payload(self):
        return {"key": self.key, "keeper": self.keeper,
                "scene": self.scene, "name": self.name,
                "goods": [x.payload() for x in self.goods]}


@dataclass(frozen=True, slots=True)
class SocietyRules:
    phase_turns: int
    starting_balance: int
    residents: tuple[Resident, ...]
    shops: tuple[Shop, ...] = ()

    def __post_init__(self):
        _int(self.phase_turns, 1, 10_000)
        _int(self.starting_balance, 0, MAX_BALANCE)
        if not isinstance(self.residents, tuple) or len(self.residents) > MAX_RESIDENTS:
            raise ValueError("invalid bounded NPC roster")
        if not isinstance(self.shops, tuple) or len(self.shops) > MAX_SHOPS:
            raise ValueError("invalid bounded marketplace")
        if any(not isinstance(n, Resident) for n in self.residents):
            raise ValueError("untyped NPC")
        if any(not isinstance(s, Shop) for s in self.shops):
            raise ValueError("untyped shop")
        if len({n.key for n in self.residents}) != len(self.residents):
            raise ValueError("duplicate NPC identity")
        if len({s.key for s in self.shops}) != len(self.shops):
            raise ValueError("duplicate shop identity")
        known = {n.key: n for n in self.residents}
        products = set()
        for shop in self.shops:
            if shop.keeper not in known:
                raise ValueError("merchant has no resident NPC")
            if shop.scene not in known[shop.keeper].schedule:
                raise ValueError("NPC cannot ever attend their original shop")
            for good in shop.goods:
                if good.key in products:
                    raise ValueError("economy inventory IDs must be globally unambiguous")
                products.add(good.key)
        if len(products) > MAX_GOODS:
            raise ValueError("too many traded resources in one typed world")

    def payload(self):
        return {"schema": SCHEMA, "phase_turns": self.phase_turns,
                "starting_balance": self.starting_balance,
                "residents": [x.payload() for x in self.residents],
                "shops": [x.payload() for x in self.shops]}


@dataclass(frozen=True, slots=True)
class SocietyState:
    balance: int
    relationships: tuple[tuple[str, int], ...]
    last_talk_cycle: tuple[tuple[str, int], ...] = ()
    shop_stock: tuple[tuple[str, str, int], ...] = ()
    owned: tuple[tuple[str, int], ...] = ()
    transactions: tuple[tuple[str, str, int, int], ...] = ()

    def __post_init__(self):
        _int(self.balance, 0, MAX_BALANCE)
        if len(self.relationships) > MAX_RESIDENTS or len({
                key for key, _ in self.relationships
        }) != len(self.relationships):
            raise ValueError("invalid NPC relationship save data")
        for key, number in self.relationships:
            _id(key)
            _int(number, -100, 100)
        if len(self.last_talk_cycle) > MAX_RESIDENTS or len({
                key for key, _ in self.last_talk_cycle
        }) != len(self.last_talk_cycle):
            raise ValueError("invalid NPC conversation cooldown ledger")
        for key, count in self.last_talk_cycle:
            _id(key)
            if type(count) is not int or count < 0:
                raise ValueError("NPC cooldown cycle must be a valid nonnegative integer")
        if len(self.shop_stock) > MAX_GOODS or len({
                (shop, good) for shop, good, _ in self.shop_stock
        }) != len(self.shop_stock):
            raise ValueError("invalid original shop stock snapshot")
        for shop, good, count in self.shop_stock:
            _id(shop)
            _id(good)
            _int(count, 0, 100_000)
        if len(self.owned) > MAX_GOODS or len({
                item for item, _ in self.owned
        }) != len(self.owned):
            raise ValueError("invalid original acquired shop inventory")
        for item, count in self.owned:
            _id(item)
            _int(count, 1, 99)
        if len(self.transactions) > 2 * MAX_GOODS or len({
                (shop, good, direction)
                for shop, good, direction, _ in self.transactions
        }) != len(self.transactions):
            raise ValueError("invalid original shop transaction counters")
        for shop, good, direction, count in self.transactions:
            _id(shop)
            _id(good)
            if direction not in (0, 1):
                raise ValueError("transaction direction must be buy(0)/sell(1)")
            if type(count) is not int or count < 1:
                raise ValueError("shop transaction counter must be a positive integer")

    def payload(self):
        return {
            "balance": self.balance,
            "relationships": [list(x) for x in self.relationships],
            "last_talk_cycle": [list(x) for x in self.last_talk_cycle],
            "shop_stock": [list(x) for x in self.shop_stock],
            "owned": [list(x) for x in self.owned],
            "transactions": [list(x) for x in self.transactions],
        }


def compile_society(data: Any) -> SocietyRules:
    doc = _exact(data, {"schema", "phase_turns", "starting_balance",
                        "residents", "shops"}, "society")
    if doc["schema"] != SCHEMA:
        raise ValueError("unknown original-world society schema")
    if not isinstance(doc["residents"], list) or not isinstance(doc["shops"], list):
        raise ValueError("society actors and shops must be arrays")
    if len(doc["residents"]) > MAX_RESIDENTS or len(doc["shops"]) > MAX_SHOPS:
        raise ValueError("society source exceeds per-world resource limits")
    residents = []
    for item in doc["residents"]:
        row = _exact(item, {"key", "name", "faction", "schedule", "greeting",
                            "initial_trust", "trust_gain", "reputation_gain",
                            "unlock_at_trust", "unlock_world_flag"}, "resident")
        if type(row["schedule"]) is not list:
            raise ValueError("NPC schedule must be a four-phase array")
        residents.append(Resident(
            key=row["key"], name=row["name"], faction=row["faction"],
            schedule=tuple(row["schedule"]), greeting=row["greeting"],
            initial_trust=row["initial_trust"], trust_gain=row["trust_gain"],
            reputation_gain=row["reputation_gain"],
            unlock_at_trust=row["unlock_at_trust"],
            unlock_world_flag=row["unlock_world_flag"],
        ))
    shops = []
    for item in doc["shops"]:
        row = _exact(item, {"key", "keeper", "scene", "name", "goods"}, "shop")
        if type(row["goods"]) is not list or len(row["goods"]) > 64:
            raise ValueError("shop catalogue is not a bounded list")
        shops.append(Shop(row["key"], row["keeper"], row["scene"], row["name"],
                          tuple(Good(**_exact(g, {
                              "key", "name", "buy_price", "sell_price",
                              "starting_stock"}, "good")) for g in row["goods"])))
    return SocietyRules(doc["phase_turns"], doc["starting_balance"],
                        tuple(residents), tuple(shops))


def initial(rules: SocietyRules) -> SocietyState:
    return SocietyState(
        balance=rules.starting_balance,
        relationships=tuple(sorted((n.key, n.initial_trust)
                                   for n in rules.residents)),
        shop_stock=tuple(sorted((s.key, g.key, g.starting_stock)
                                for s in rules.shops for g in s.goods)),
    )


def phase(rules: SocietyRules, turn: int) -> dict[str, Any]:
    if type(turn) is not int or turn < 0:
        raise ValueError("authored world time must be a nonnegative integer")
    return {
        "phase": PHASES[(turn // rules.phase_turns) % 4],
        "phase_index": (turn // rules.phase_turns) % 4,
        "cycle": turn // (4 * rules.phase_turns),
        "phase_turns": rules.phase_turns,
        "turns_until_next_phase": rules.phase_turns - turn % rules.phase_turns,
    }


def residents_here(rules: SocietyRules, scene: str, turn: int) -> tuple[Resident, ...]:
    position = phase(rules, turn)["phase_index"]
    return tuple(n for n in rules.residents if n.schedule[position] == scene)


def legal_actions(rules: SocietyRules, state: Any) -> tuple[tuple[str, str], ...]:
    """Every returned action is executable with current trusted player state."""
    society = state.world_state.society
    if society is None:
        raise ValueError("missing original NPC and shop state")
    present = {n.key: n for n in residents_here(rules, state.scene, state.turn)}
    cooldown = dict(society.last_talk_cycle)
    cycle = phase(rules, state.turn)["cycle"]
    actions: list[tuple[str, str]] = []
    for npc in present.values():
        if cooldown.get(npc.key) != cycle:
            actions.append(("speak", npc.key))
    stock = {(shop, good): count for shop, good, count in society.shop_stock}
    owned = dict(society.owned)
    for shop in rules.shops:
        if shop.scene != state.scene or shop.keeper not in present:
            continue
        for good in shop.goods:
            ident = shop.key + "_" + good.key
            quantity = owned.get(good.key, 0)
            if (stock[(shop.key, good.key)] > 0
                    and society.balance >= good.buy_price
                    and quantity < 99):
                actions.append(("buy", ident))
            if quantity > 0 and stock[(shop.key, good.key)] < 100_000:
                if society.balance + good.sell_price <= MAX_BALANCE:
                    actions.append(("sell", ident))
    actions.append(("rest", "rest"))
    return tuple(actions)


def perform(rules: SocietyRules, state: Any, kind: str, key: str
            ) -> tuple[SocietyState, tuple[tuple[str, int], ...],
                       tuple[str, ...], tuple[str, ...], int]:
    """Return new state + faction effects + flags + new game inventory + turns.

    Direct callers must have admitted the action with legal_actions. The
    function enforces permission AGAIN so it cannot serve as a bypass.
    Item sources are disjoint from quest affordance rewards by world validation.
    """
    if (kind, key) not in legal_actions(rules, state):
        raise ValueError("original resident/shop action not currently legal")
    old = state.world_state.society
    if kind == "rest":
        return old, (), (), (), rules.phase_turns
    if kind == "speak":
        resident = next(n for n in rules.residents if n.key == key)
        relationships = dict(old.relationships)
        before = relationships[key]
        relationships[key] = max(-100, min(100, before + resident.trust_gain))
        touched = dict(old.last_talk_cycle)
        touched[key] = phase(rules, state.turn)["cycle"]
        flags = (resident.unlock_world_flag,) if (
            resident.unlock_world_flag is not None
            and relationships[key] >= resident.unlock_at_trust
        ) else ()
        faction_effects = ((resident.faction, resident.reputation_gain),) if (
            resident.faction is not None and resident.reputation_gain
        ) else ()
        return SocietyState(
            old.balance, tuple(sorted(relationships.items())),
            tuple(sorted(touched.items())), old.shop_stock, old.owned,
            old.transactions,
        ), faction_effects, flags, (), 1
    good_shop = next(
        (s for s in rules.shops for good in s.goods
         if s.key + "_" + good.key == key), None)
    if good_shop is None:
        raise ValueError("requested shop action absent from authored commerce")
    product = next(g for g in good_shop.goods if good_shop.key + "_" + g.key == key)
    stock = {(shop, item): quantity for shop, item, quantity in old.shop_stock}
    inventory = dict(old.owned)
    counts = {(shop, item, direction): count
              for shop, item, direction, count in old.transactions}
    owned_before = inventory.get(product.key, 0)
    transaction = (good_shop.key, product.key, 0 if kind == "buy" else 1)
    if kind == "buy":
        balance = old.balance - product.buy_price
        stock[(good_shop.key, product.key)] -= 1
        inventory[product.key] = owned_before + 1
        acquired = (product.key,) if owned_before == 0 else ()
        time_cost = 2
    else:
        balance = old.balance + product.sell_price
        stock[(good_shop.key, product.key)] += 1
        if owned_before == 1:
            inventory.pop(product.key)
        else:
            inventory[product.key] -= 1
        acquired = ("-" + product.key,) if owned_before == 1 else ()
        time_cost = 2
    counts[transaction] = counts.get(transaction, 0) + 1
    updated = SocietyState(
        balance=balance, relationships=old.relationships,
        last_talk_cycle=old.last_talk_cycle,
        shop_stock=tuple(sorted((shop, item, count)
                                for (shop, item), count in stock.items())),
        owned=tuple(sorted(inventory.items())),
        transactions=tuple(sorted((shop, item, direction, count)
                                  for (shop, item, direction), count in counts.items())),
    )
    return updated, (), (), acquired, time_cost


def verify_world(rules: SocietyRules, *, scene_ids: set[str],
                 faction_ids: set[str], quest_items: set[str]) -> None:
    all_goods = {good.key for shop in rules.shops for good in shop.goods}
    if all_goods & quest_items:
        raise ValueError("shop merchandise cannot alias script-earned quest resources")
    for resident in rules.residents:
        if not set(resident.schedule).issubset(scene_ids):
            raise ValueError("NPC schedule leaves the authored world")
        if resident.faction is not None and resident.faction not in faction_ids:
            raise ValueError("NPC alters an unauthored faction")
    for shop in rules.shops:
        if shop.scene not in scene_ids:
            raise ValueError("original shop exists in an absent game location")
