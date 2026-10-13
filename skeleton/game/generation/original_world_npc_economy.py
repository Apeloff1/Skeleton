"""Finite, spatially accountable household and person-to-person economy.

Household pantry allocations are debited from the *existing* settlement
warehouse. Pantry meals are debited from their specific home before reducing
a real person's hunger. Person-to-person trades exchange already-carried
goods, only at co-located coordinates, with explicit offered goods and
deterministic consent. No goods or currency is created by a proposal.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .original_foundation_compiler import FoundationError
from .original_world_product_agents import Person, PhysicalSociety, validate_society
from .original_world_product_terrain import TerrainState, cell_at

SCHEMA = "original-citizen-household-economy.v1"
MAX_HOUSEHOLDS = 32
MAX_TRADES = 32
KINDS = ("food", "water", "wood", "stone")
WAREHOUSE = {"food": "provisions", "water": "freshwater",
             "wood": "lumber", "stone": "masonry"}


@dataclass(frozen=True)
class Household:
    household_id: int
    members: tuple[int, ...]
    x: int = 0
    y: int = 0
    food: int = 0
    water: int = 0
    meals_provided: int = 0


@dataclass(frozen=True)
class Trade:
    trade_id: int
    proposer: int
    recipient: int
    offers: str
    requests: str
    units: int
    created_day: int
    status: str = "pending"


@dataclass(frozen=True)
class Economy:
    design_id: str
    households: tuple[Household, ...]
    trades: tuple[Trade, ...] = ()
    next_trade: int = 0
    meals_served: int = 0
    trades_completed: int = 0
    trades_refused: int = 0
    day: int = 0
    event_head: str = "0" * 64


@dataclass(frozen=True)
class EconomyReceipt:
    category: str
    participants: tuple[int, ...]
    stock: str
    units: int
    reason: str


def _hash(raw: object) -> str:
    return sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode()).hexdigest()


def _integer(value: object, lower: int, upper: int, label: str) -> None:
    if type(value) is not int or not lower <= value <= upper:
        raise FoundationError("invalid household economic " + label)


def create_economy(people: PhysicalSociety, world: TerrainState) -> Economy:
    validate_society(people, world)
    groups = []
    # Deterministic households of 1–3 named people. Residency, not an
    # anonymous population counter. No food or monetary starting grant.
    for i in range(0, len(people.inhabitants), 3):
        groups.append(Household(len(groups), tuple(
            p.id for p in people.inhabitants[i:i+3]
        )))
    result = Economy(world.design_id, tuple(groups), day=people.tick)
    validate_economy(result, people, world)
    return result


def validate_economy(
    economy: Economy, people: PhysicalSociety, world: TerrainState,
) -> None:
    validate_society(people, world)
    if not isinstance(economy, Economy) or economy.design_id != world.design_id:
        raise FoundationError("economic state does not belong to this physical world")
    if economy.day != people.tick:
        raise FoundationError("household and resident clocks have diverged")
    if not isinstance(economy.households, tuple) or not 1 <= len(economy.households) <= MAX_HOUSEHOLDS:
        raise FoundationError("unbounded or missing household census")
    membership = []
    for h in economy.households:
        if not isinstance(h, Household):
            raise FoundationError("malformed household census")
        _integer(h.household_id, 0, MAX_HOUSEHOLDS-1, "household identity")
        if not isinstance(h.members, tuple) or not 1 <= len(h.members) <= 3:
            raise FoundationError("household requires 1–3 specific residents")
        for person in h.members:
            _integer(person, 0, len(people.inhabitants)-1, "household member")
        if tuple(sorted(set(h.members))) != h.members:
            raise FoundationError("household has duplicated citizens")
        membership.extend(h.members)
        for coord in (h.x, h.y):
            _integer(coord, -(1 << 20), 1 << 20, "home location")
        if cell_at(world, h.x, h.y).blocking:
            raise FoundationError("household resides inside physical obstruction")
        for field in ("food", "water", "meals_provided"):
            _integer(getattr(h, field), 0, 1000, field)
    if [h.household_id for h in economy.households] != list(range(len(economy.households))):
        raise FoundationError("household identity order was rewritten")
    if sorted(membership) != list(range(len(people.inhabitants))):
        raise FoundationError("a citizen is homeless or assigned to multiple households")
    if not isinstance(economy.trades, tuple) or len(economy.trades) > MAX_TRADES:
        raise FoundationError("market offer budget exceeded")
    ids = set()
    for trade in economy.trades:
        if not isinstance(trade, Trade):
            raise FoundationError("malformed individual market offer")
        _integer(trade.trade_id, 0, 100000, "market ID")
        _integer(trade.proposer, 0, len(people.inhabitants)-1, "proposer")
        _integer(trade.recipient, 0, len(people.inhabitants)-1, "recipient")
        if trade.proposer == trade.recipient or trade.offers not in KINDS or (
            trade.requests not in KINDS or trade.offers == trade.requests
        ):
            raise FoundationError("market offer is not a material exchange")
        _integer(trade.units, 1, 3, "exchange quantity")
        _integer(trade.created_day, 0, economy.day, "offer creation day")
        if trade.status not in ("pending", "accepted", "refused", "expired"):
            raise FoundationError("unknown trade settlement outcome")
        if trade.trade_id in ids:
            raise FoundationError("duplicate market offer")
        ids.add(trade.trade_id)
    if ids and max(ids) >= economy.next_trade:
        raise FoundationError("trade identity was reused")
    _integer(economy.next_trade, 0, 100000, "next trade")
    for field in ("meals_served", "trades_completed", "trades_refused"):
        _integer(getattr(economy, field), 0, 10000, field)
    _integer(economy.day, 0, 1000, "physical market clock")
    if not isinstance(economy.event_head, str) or len(economy.event_head) != 64 or any(
        c not in "0123456789abcdef" for c in economy.event_head
    ):
        raise FoundationError("invalid market accounting receipt")


def fund_home(
    economy: Economy, people: PhysicalSociety, world: TerrainState,
    household_id: int, kind: str, quantity: int,
) -> tuple[Economy, TerrainState]:
    validate_economy(economy, people, world)
    _integer(household_id, 0, len(economy.households)-1, "funded family")
    _integer(quantity, 1, 3, "transferred goods")
    if kind not in ("food", "water"):
        raise FoundationError("home pantry accepts only physical food and drinking water")
    source = WAREHOUSE[kind]
    home = economy.households[household_id]
    if getattr(world, source) < quantity or getattr(home, kind) + quantity > 1000:
        raise FoundationError("insufficient existing warehouse stock or full household pantry")
    revised = replace(
        world, **{source: getattr(world, source) - quantity},
    )
    homes = list(economy.households)
    homes[household_id] = replace(
        home, **{kind: getattr(home, kind) + quantity},
    )
    updated = replace(economy, households=tuple(homes))
    validate_economy(updated, people, revised)
    return updated, revised


def propose_trade(
    economy: Economy, people: PhysicalSociety, world: TerrainState,
    proposer: int, recipient: int, offers: str, requests: str, units: int = 1,
) -> Economy:
    validate_economy(economy, people, world)
    _integer(proposer, 0, len(people.inhabitants)-1, "seller")
    _integer(recipient, 0, len(people.inhabitants)-1, "buyer")
    _integer(units, 1, 3, "real traded units")
    if proposer == recipient or offers not in KINDS or (
        requests not in KINDS or offers == requests
    ):
        raise FoundationError("market requires reciprocal distinct real goods")
    left, right = people.inhabitants[proposer], people.inhabitants[recipient]
    if (left.x, left.y) != (right.x, right.y):
        raise FoundationError("material trades require face-to-face physical exchange")
    if (left.cargo_kind != offers or right.cargo_kind != requests
            or left.cargo != units or right.cargo != units):
        raise FoundationError("participants must carry exact offered physical stock")
    if len(economy.trades) >= MAX_TRADES:
        raise FoundationError("market trading history full")
    if any(x.status == "pending" and (
        proposer in (x.proposer, x.recipient)
        or recipient in (x.proposer, x.recipient)
    ) for x in economy.trades):
        raise FoundationError("citizen already negotiating another non-escrowed offer")
    new = Trade(economy.next_trade, proposer, recipient,
                offers, requests, units, economy.day)
    result = replace(economy, trades=economy.trades + (new,),
                     next_trade=economy.next_trade + 1)
    validate_economy(result, people, world)
    return result


def household_tick(
    economy: Economy, people: PhysicalSociety, world: TerrainState,
) -> tuple[Economy, PhysicalSociety, tuple[EconomyReceipt, ...]]:
    """One bounded cooperative meal round before each actor's planning tick.

    Only physically present household members may eat. Home food stock
    is independently owned and cannot also be counted in public stores.
    """
    validate_economy(economy, people, world)
    residents = list(people.inhabitants)
    homes = []
    receipts = []
    served = 0
    for home in economy.households:
        left = home.food
        local = 0
        for citizen_id in home.members:
            p = residents[citizen_id]
            if ((p.x, p.y) != (home.x, home.y)
                    or p.health == 0 or p.hunger < 6 or left <= 0):
                continue
            left -= 1
            local += 1
            served += 1
            residents[citizen_id] = replace(
                p, hunger=max(0, p.hunger - 6),
                health=min(20, p.health + 1),
            )
            receipts.append(EconomyReceipt(
                "household-care", (home.household_id, citizen_id),
                "food", 1, "A present household member ate one existing pantry meal",
            ))
        homes.append(replace(home, food=left,
                             meals_provided=home.meals_provided + local))
    outcome = replace(economy, households=tuple(homes),
                      meals_served=economy.meals_served + served)
    result_people = replace(people, inhabitants=tuple(residents))
    validate_economy(outcome, result_people, world)
    return outcome, result_people, tuple(receipts)


def settle_trades(
    economy: Economy, people: PhysicalSociety, world: TerrainState,
    *, empathies: tuple[int, ...],
) -> tuple[Economy, PhysicalSociety, tuple[EconomyReceipt, ...]]:
    """Issue finite, consent-checked 1-for-1 physical trades.

    Higher empathy and personally valuable goods increase acceptance.
    Neither actor may give their final food away while starving.
    A pending trade expiring/refusing never transfers inventory.
    """
    validate_economy(economy, people, world)
    if len(empathies) != len(people.inhabitants) or any(
        type(value) is not int or not 1 <= value <= 10 for value in empathies
    ):
        raise FoundationError("invalid individual NPC negotiation attributes")
    roster = list(people.inhabitants)
    offers = []
    receipts = []
    accepted, rejected = 0, 0
    for trade in economy.trades:
        if trade.status != "pending":
            offers.append(trade)
            continue
        buyer, seller = roster[trade.proposer], roster[trade.recipient]
        physical = (
            (buyer.x, buyer.y) == (seller.x, seller.y)
            and buyer.cargo_kind == trade.offers
            and seller.cargo_kind == trade.requests
            and buyer.cargo == seller.cargo == trade.units
        )
        if economy.day - trade.created_day >= 3:
            offers.append(replace(trade, status="expired"))
            rejected += 1
            continue
        if not physical:
            offers.append(trade)
            continue
        if (buyer.health == 0 or seller.health == 0
                or (trade.offers == "food" and buyer.hunger >= 6)
                or (trade.requests == "food" and seller.hunger >= 6)):
            offers.append(replace(trade, status="refused"))
            rejected += 1
            receipts.append(EconomyReceipt(
                "refused", (buyer.id, seller.id), "", 0,
                "One party declined or cannot safely trade away survival stock",
            ))
            continue
        # A specific physical food benefit is always meaningful when hungry.
        want = (trade.offers == "food" and seller.hunger >= 3) or (
            trade.offers == "water" and seller.health <= 15
        ) or empathies[seller.id] >= 6
        if not want:
            offers.append(replace(trade, status="refused"))
            rejected += 1
            continue
        roster[buyer.id] = replace(buyer, cargo_kind=trade.requests)
        roster[seller.id] = replace(seller, cargo_kind=trade.offers)
        accepted += 1
        offers.append(replace(trade, status="accepted"))
        receipts.append(EconomyReceipt(
            "swap", (buyer.id, seller.id), "physical-barter",
            trade.units, "Two co-located citizens exchanged equal quantities of existing owned cargo",
        ))
    result = replace(
        economy, trades=tuple(offers),
        trades_completed=economy.trades_completed + accepted,
        trades_refused=economy.trades_refused + rejected,
    )
    updated = replace(people, inhabitants=tuple(roster))
    validate_economy(result, updated, world)
    return result, updated, tuple(receipts)


def advance_economy(
    state: Economy, people: PhysicalSociety, world: TerrainState,
) -> Economy:
    validate_economy(state, people, world)
    if state.day >= 1000:
        raise FoundationError("household simulation tick capacity exhausted")
    future = replace(state, day=state.day + 1,
                     event_head=_hash({
                         "schema": SCHEMA, "previous": state.event_head,
                         "before": asdict(state),
                         "citizens": [asdict(p) for p in people.inhabitants],
                         "terrain_head": world.event_head,
                     }))
    advanced_bodies = replace(people, tick=future.day)
    validate_economy(future, advanced_bodies, world)
    return future


def economy_save(state: Economy) -> dict:
    packet = asdict(state)
    return {"schema": SCHEMA, "payload": packet, "checksum": _hash(packet)}


def economy_restore(
    raw: dict, people: PhysicalSociety, world: TerrainState,
) -> Economy:
    try:
        if not isinstance(raw, dict) or set(raw) != {
            "schema", "payload", "checksum"
        } or raw["schema"] != SCHEMA:
            raise FoundationError("unsupported material economy version")
        body = raw["payload"]
        if raw["checksum"] != _hash(body) or set(body) != set(Economy.__dataclass_fields__):
            raise FoundationError("material economy ledger checksum mismatch")
        result = Economy(**{
            **body,
            "households": tuple(Household(
                **{**h, "members": tuple(h["members"])}
            ) for h in body["households"]),
            "trades": tuple(Trade(**x) for x in body["trades"]),
        })
        validate_economy(result, people, world)
        return result
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise FoundationError("rejected persistent household economic state") from exc


def economy_report(state: Economy, people: PhysicalSociety,
                   world: TerrainState) -> dict:
    validate_economy(state, people, world)
    return {
        "schema": SCHEMA,
        "households": [asdict(h) for h in state.households],
        "open_market_offers": [asdict(t) for t in state.trades if t.status == "pending"],
        "trade_history": [asdict(t) for t in state.trades],
        "meals_physically_served": state.meals_served,
        "barters_completed": state.trades_completed,
        "refused_or_expired_trades": state.trades_refused,
        "no_unsupported_credits_or_ownership_fabricated": True,
    }
