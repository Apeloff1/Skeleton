"""Multi-scene NPC trade routes: escrow, graph traversal and conserved goods.

Extends colocated NPC trades with multi-turn routes. No merchant teleports,
unfunded settlement, free cargo, or external side effects are possible.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace

from .contracts import canonical_digest
from .npc_social_economy import Economy, EconomyError, Account, GOODS, price
from .npc_society_runtime import Society
from .quest_scene_engine import DirectorWorld

MAX_SHIPMENTS = 256
MAX_EVENTS = 4096


@dataclass(frozen=True, slots=True)
class TradeShipment:
    shipment_id: str
    seller: str
    buyer: str
    good: str
    amount: int
    escrow_coins: int
    route: tuple[str, ...]
    position: int
    created_turn: int
    last_advanced_turn: int
    state: str = "moving"

    def payload(self) -> dict:
        return dict(
            shipment_id=self.shipment_id, seller=self.seller, buyer=self.buyer,
            good=self.good, amount=self.amount, escrow_coins=self.escrow_coins,
            route=list(self.route), position=self.position,
            created_turn=self.created_turn,
            last_advanced_turn=self.last_advanced_turn, state=self.state,
        )


@dataclass(frozen=True, slots=True)
class TradeRouteEvent:
    turn: int
    action: str
    shipment_id: str
    scene: str
    improvement: str

    def payload(self) -> dict:
        return dict(turn=self.turn, action=self.action,
                    shipment_id=self.shipment_id, scene=self.scene,
                    improvement=self.improvement)


@dataclass(frozen=True, slots=True)
class TradeLogistics:
    world_digest: str
    economy: Economy
    shipments: tuple[TradeShipment, ...] = ()
    events: tuple[TradeRouteEvent, ...] = ()

    def payload(self) -> dict:
        return dict(
            schema="skeleton.game_builder.npc_trade_logistics.v1",
            world_digest=self.world_digest, economy=self.economy.payload(),
            shipments=[x.payload() for x in self.shipments],
            events=[event.payload() for event in self.events],
        )

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


def _check(logistics: TradeLogistics, society: Society,
           world: DirectorWorld, authorized: bool) -> None:
    if authorized is not True:
        raise PermissionError("trading routes require trusted simulation authority")
    if (not isinstance(logistics, TradeLogistics)
            or not isinstance(society, Society)
            or not isinstance(world, DirectorWorld)
            or logistics.world_digest != world.digest
            or logistics.economy.society_digest != world.digest
            or society.world_digest != world.digest
            or len(logistics.shipments) > MAX_SHIPMENTS
            or len(logistics.events) > MAX_EVENTS):
        raise EconomyError("foreign, unbounded or incompatible route state")


def new_logistics(economy: Economy, society: Society, world: DirectorWorld, *,
                  authorized: bool) -> TradeLogistics:
    if not isinstance(economy, Economy):
        raise EconomyError("canonical original-world economy required")
    record = TradeLogistics(world.digest, economy)
    _check(record, society, world, authorized)
    if tuple(a.owner for a in economy.accounts) != tuple(p.key for p in society.profiles):
        raise EconomyError("route accounts must match actual citizens")
    return record


def _route(world: DirectorWorld, start: str, end: str) -> tuple[str, ...]:
    if start == end:
        raise EconomyError("inter-region trades require different scenes")
    edges = {scene.key: scene.links for scene in world.scenes}
    if start not in edges or end not in edges:
        raise EconomyError("shipment references uncreated scene")
    todo = deque([(start, (start,))])
    seen = {start}
    while todo:
        node, path = todo.popleft()
        for neighbor in sorted(edges[node]):
            if neighbor not in edges:
                raise EconomyError("authored transit points outside world")
            if neighbor in seen:
                continue
            steps = path + (neighbor,)
            if neighbor == end:
                return steps
            seen.add(neighbor)
            todo.append((neighbor, steps))
    raise EconomyError("no physical route between regional markets")


def _accounts(economy: Economy) -> dict[str, Account]:
    data = {a.owner: a for a in economy.accounts}
    if len(data) != len(economy.accounts):
        raise EconomyError("duplicate simulated market account")
    return data


def schedule_trade(logistics: TradeLogistics, society: Society,
                   world: DirectorWorld, *, seller: str, buyer: str,
                   good: str, quantity: int, authorized: bool) -> TradeLogistics:
    _check(logistics, society, world, authorized)
    if (seller == buyer or type(quantity) is not int
            or not 1 <= quantity <= 16 or good not in GOODS):
        raise EconomyError("invalid inter-region transaction")
    if len(logistics.shipments) >= MAX_SHIPMENTS or len(logistics.events) >= MAX_EVENTS:
        raise EconomyError("shipping capacity requires archival")
    actors = {mind.key: mind for mind in society.minds}
    accounts = _accounts(logistics.economy)
    if seller not in actors or buyer not in actors or seller not in accounts or buyer not in accounts:
        raise EconomyError("shipment requires actual known citizens")
    origin, destination = actors[seller].scene, actors[buyer].scene
    path = _route(world, origin, destination)
    rate = price(logistics.economy, good, region_keys=tuple(
        m.key for m in society.minds if m.scene == origin
    ))
    total = rate * quantity
    source, target = accounts[seller], accounts[buyer]
    available = dict(source.goods)
    receiving = dict(target.goods)
    if available.get(good, 0) < quantity or target.coins < total:
        raise EconomyError("finite cargo and prepaid currency required")
    incoming = sum(
        s.amount for s in logistics.shipments
        if s.state == "moving" and s.buyer == buyer and s.good == good
    )
    seller_owed = sum(
        s.escrow_coins for s in logistics.shipments
        if s.state == "moving" and s.seller == seller
    )
    if (receiving.get(good, 0) + quantity + incoming > 255
            or source.coins + total + seller_owed > 100000):
        raise EconomyError("receiver or seller has insufficient bounded capacity")
    available[good] -= quantity
    accounts[seller] = replace(source, goods=tuple(sorted(available.items())))
    accounts[buyer] = replace(target, coins=target.coins - total)
    serial = len(logistics.shipments)
    identity = canonical_digest((
        world.digest, seller, buyer, good, quantity, total,
        society.turn, origin, destination, serial,
    ))
    shipment = TradeShipment(
        identity, seller, buyer, good, quantity, total, path, 0,
        society.turn, society.turn,
    )
    event = TradeRouteEvent(society.turn, "escrow_reserved", identity, origin,
                            "(cargo and payment reserved without teleporting assets)")
    return replace(logistics, economy=replace(
        logistics.economy,
        accounts=tuple(accounts[a.owner] for a in logistics.economy.accounts),
    ), shipments=(*logistics.shipments, shipment),
        events=(*logistics.events, event))


def advance_trade_routes(logistics: TradeLogistics, society: Society,
                         world: DirectorWorld, *, authorized: bool,
                         max_active: int = 24) -> TradeLogistics:
    _check(logistics, society, world, authorized)
    if type(max_active) is not int or not 1 <= max_active <= 128:
        raise EconomyError("bounded route simulation budget required")
    shipments = []
    events = list(logistics.events)
    accounts = _accounts(logistics.economy)
    moved = 0
    edges = {scene.key: set(scene.links) for scene in world.scenes}
    for old in logistics.shipments:
        if (old.state != "moving" or moved >= max_active
                or society.turn <= old.last_advanced_turn):
            shipments.append(old)
            continue
        if (old.position < 0 or old.position >= len(old.route) - 1
                or old.route[old.position] not in edges
                or old.route[old.position + 1] not in edges[old.route[old.position]]):
            raise EconomyError("shipment route invalid or forged")
        if len(events) >= MAX_EVENTS:
            raise EconomyError("shipping journal requires archival")
        index = old.position + 1
        next_scene = old.route[index]
        done = index == len(old.route) - 1
        if done:
            seller, buyer = accounts[old.seller], accounts[old.buyer]
            stock = dict(buyer.goods)
            if (seller.coins + old.escrow_coins > 100000
                    or stock.get(old.good, 0) + old.amount > 255):
                raise EconomyError("escrow settlement has exceeded bounded capacity")
            stock[old.good] = stock.get(old.good, 0) + old.amount
            accounts[old.seller] = replace(
                seller, coins=seller.coins + old.escrow_coins,
            )
            accounts[old.buyer] = replace(
                buyer, goods=tuple(sorted(stock.items())),
            )
        current = replace(
            old, position=index, last_advanced_turn=society.turn,
            state="delivered" if done else "moving",
        )
        shipments.append(current)
        events.append(TradeRouteEvent(
            society.turn, "delivered" if done else "route_step",
            old.shipment_id, next_scene,
            "(escrow settled after physical arrival)" if done else
            "(physical route advanced one authored scene)",
        ))
        moved += 1
    return replace(logistics,
        economy=replace(logistics.economy,
                        accounts=tuple(accounts[a.owner] for a in logistics.economy.accounts)),
        shipments=tuple(shipments), events=tuple(events),
    )


def conserved_totals(logistics: TradeLogistics) -> dict:
    """Audit finite inventories including goods and coins still in escrow."""
    total_coins = sum(a.coins for a in logistics.economy.accounts)
    totals = {good: sum(dict(a.goods).get(good, 0)
                        for a in logistics.economy.accounts) for good in GOODS}
    for shipment in logistics.shipments:
        if shipment.state == "moving":
            total_coins += shipment.escrow_coins
            totals[shipment.good] += shipment.amount
    return {"coins": total_coins, "goods": totals}


def simulate_market_corridor(
    world: DirectorWorld, *, population: int,
    seller_index: int, buyer_index: int,
    good: str, quantity: int, steps: int,
    authorized: bool, active_budget: int = 24,
    ambient_budget: int = 48,
) -> dict:
    """Deterministic gameplay integration: AI citizens plus independent trade.

    A real society_tick advances citizen needs/locations and a separate
    authoritative logistics step advances the shipment one authored scene.
    Outputs contain replay-verifiable digests and finite conservation checks.
    This is a game simulation, not a real-world logistics service.
    """
    if authorized is not True:
        raise PermissionError("operator authority required to run market world")
    if (type(population) is not int or not 3 <= population <= 512
            or type(seller_index) is not int or not 0 <= seller_index < population
            or type(buyer_index) is not int or not 0 <= buyer_index < population
            or seller_index == buyer_index
            or type(steps) is not int or not 1 <= steps <= 128):
        raise EconomyError("market simulation requires bounded citizens and clock")
    from .npc_society_runtime import make_society, society_tick
    from .npc_social_economy import new_economy
    society = make_society(world, population, authorized=True)
    seller = society.profiles[seller_index].key
    buyer = society.profiles[buyer_index].key
    initial = new_logistics(
        new_economy(society, authorized=True), society, world, authorized=True,
    )
    before = conserved_totals(initial)
    current = schedule_trade(
        initial, society, world, seller=seller, buyer=buyer,
        good=good, quantity=quantity, authorized=True,
    )
    root = current.shipments[0].shipment_id
    digests = []
    player_scene = society.minds[seller_index].scene
    for _ in range(steps):
        society = society_tick(
            society, world, player_scene=player_scene,
            active_budget=active_budget, ambient_budget=ambient_budget,
            authorized=True,
        )
        current = advance_trade_routes(
            current, society, world, authorized=True,
        )
        if conserved_totals(current) != before:
            raise EconomyError("gameplay violated finite trade conservation")
        digests.append(current.digest)
    shipment = current.shipments[0]
    result = {
        "schema": "skeleton.game_builder.npc_market_corridor.v1",
        "world_digest": world.digest,
        "society_digest": society.digest,
        "route": list(shipment.route),
        "position": shipment.position,
        "delivered": shipment.state == "delivered",
        "shipment_id": root,
        "turns": steps,
        "seller": seller,
        "buyer": buyer,
        "good": good,
        "quantity": quantity,
        "replay_digests": digests,
        "conserved_assets": before,
        "events": [event.payload() for event in current.events],
        "final_economy": current.economy.payload(),
        "native_hardware_verified": False,
        "model_training_authorized": False,
    }
    return {**result, "replay_digest": canonical_digest(result)}


def verify_market_corridor(report: dict, world: DirectorWorld, *,
                          population: int, seller_index: int, buyer_index: int,
                          good: str, quantity: int, steps: int,
                          authorized: bool, active_budget: int = 24,
                          ambient_budget: int = 48) -> bool:
    """Reject forged outcome receipts by replaying the original-world engine."""
    if authorized is not True:
        raise PermissionError("review requires operator authority")
    if not isinstance(report, dict):
        return False
    try:
        expected = simulate_market_corridor(
            world, population=population, seller_index=seller_index,
            buyer_index=buyer_index, good=good, quantity=quantity, steps=steps,
            active_budget=active_budget, ambient_budget=ambient_budget,
            authorized=True,
        )
        return report == expected
    except (ValueError, TypeError, KeyError, OverflowError):
        return False
