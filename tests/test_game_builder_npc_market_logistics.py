"""Real NPC inter-region commerce: physical hops and conserved escrow."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.ai.game_builder.npc_market_logistics import (
    TradeLogistics, TradeShipment, advance_trade_routes, conserved_totals,
    new_logistics, schedule_trade,
)
from skeleton.ai.game_builder.npc_social_economy import (
    Account, EconomyError, new_economy,
)
from skeleton.ai.game_builder.npc_society_runtime import make_society
from skeleton.ai.game_builder.quest_scene_forge import forge_director


@pytest.fixture(scope="module")
def world():
    return forge_director(
        "transit_economy", seed=7117,
        regions=tuple(f"region_{i:02d}" for i in range(12)),
        quest_types=("main_story", "profession", "regional_story"),
        stages=2,
    )


@pytest.fixture
def market(world):
    society = make_society(world, 36, authorized=True)
    return society, new_logistics(new_economy(society, authorized=True),
                                  society, world, authorized=True)


def create(market, world, **kwargs):
    society, state = market
    return schedule_trade(
        state, society, world, seller=society.profiles[0].key,
        buyer=society.profiles[1].key, good="grain", quantity=1,
        authorized=True, **kwargs,
    )


def test_trade_reserves_real_assets_and_advances_only_on_authoritative_turn(world, market):
    society, initial = market
    assert society.minds[0].scene != society.minds[1].scene
    original = conserved_totals(initial)
    shipped = create(market, world)
    assert conserved_totals(shipped) == original
    assert len(shipped.shipments) == 1
    parcel = shipped.shipments[0]
    assert parcel.route[0] == society.minds[0].scene
    assert parcel.route[-1] == society.minds[1].scene
    assert parcel.position == 0
    assert parcel.state == "moving"
    assert len(parcel.route) >= 2
    seller_before = initial.economy.accounts[0]
    buyer_before = initial.economy.accounts[1]
    assert dict(shipped.economy.accounts[0].goods)["grain"] == (
        dict(seller_before.goods)["grain"] - 1
    )
    assert shipped.economy.accounts[1].coins == (
        buyer_before.coins - parcel.escrow_coins
    )
    # Cannot move on the same simulation tick that placed the order.
    assert advance_trade_routes(shipped, society, world, authorized=True) == shipped
    state = shipped
    for turn in range(1, len(parcel.route)):
        advanced_society = replace(society, turn=turn)
        advanced = advance_trade_routes(state, advanced_society, world, authorized=True)
        assert advanced.shipments[0].position == turn
        assert advanced.shipments[0].last_advanced_turn == turn
        assert conserved_totals(advanced) == original
        assert advance_trade_routes(
            advanced, advanced_society, world, authorized=True,
        ) == advanced
        state = advanced
    assert state.shipments[0].state == "delivered"
    assert state.economy.accounts[0].coins == seller_before.coins + parcel.escrow_coins
    assert dict(state.economy.accounts[1].goods)["grain"] == (
        dict(buyer_before.goods)["grain"] + 1
    )
    assert state.events[-1].action == "delivered"
    assert all(event.improvement.startswith("(") for event in state.events)
    assert state.digest == advance_trade_routes(
        state, replace(society, turn=999),
        world, authorized=True,
    ).digest


def test_repeated_shipments_reserve_each_buyers_coin_only_once(world, market):
    society, logistics = market
    original = conserved_totals(logistics)
    one = create(market, world)
    two = schedule_trade(
        one, society, world, seller=society.profiles[0].key,
        buyer=society.profiles[1].key, good="grain", quantity=1,
        authorized=True,
    )
    assert len({x.shipment_id for x in two.shipments}) == 2
    assert two.shipments[0].shipment_id != two.shipments[1].shipment_id
    assert conserved_totals(two) == original
    with pytest.raises(EconomyError, match="finite cargo"):
        schedule_trade(
            two, society, world, seller=society.profiles[0].key,
            buyer=society.profiles[1].key, good="grain", quantity=1,
            authorized=True,
        )


def test_zero_authority_and_fake_cargo_never_enter_original_world(world, market):
    society, state = market
    seller, buyer = society.profiles[0].key, society.profiles[1].key
    for overrides in (
        {"good": "pirated_asset", "quantity": 1},
        {"good": "grain", "quantity": 0},
        {"good": "grain", "quantity": 17},
        {"good": "grain", "quantity": True},
    ):
        with pytest.raises(EconomyError):
            schedule_trade(
                state, society, world, seller=seller, buyer=buyer,
                authorized=True, **overrides,
            )
    with pytest.raises(PermissionError):
        schedule_trade(
            state, society, world, seller=seller, buyer=buyer,
            good="grain", quantity=1, authorized=False,
        )
    with pytest.raises(PermissionError):
        advance_trade_routes(state, society, world, authorized=False)


def test_forged_route_cannot_teleport_to_final_delivery(world, market):
    society, initial = market
    parcel = create(market, world)
    old = parcel.shipments[0]
    assert len(old.route) > 1
    forged = replace(
        parcel,
        shipments=(replace(old, route=(
            old.route[0], "uncreated_world_gate", old.route[-1],
        )),),
    )
    with pytest.raises(EconomyError, match="route invalid"):
        advance_trade_routes(
            forged, replace(society, turn=1), world, authorized=True,
        )


def test_destination_capacity_and_seller_coin_limits_fail_before_reservation(world, market):
    society, initial = market
    accounts = list(initial.economy.accounts)
    receiver = accounts[1]
    receiver_goods = dict(receiver.goods)
    receiver_goods["grain"] = 255
    accounts[1] = replace(receiver, goods=tuple(sorted(receiver_goods.items())))
    full = replace(initial, economy=replace(initial.economy, accounts=tuple(accounts)))
    with pytest.raises(EconomyError, match="bounded capacity"):
        create((society, full), world)
    accounts = list(initial.economy.accounts)
    accounts[0] = replace(accounts[0], coins=100000)
    rich = replace(initial, economy=replace(initial.economy, accounts=tuple(accounts)))
    with pytest.raises(EconomyError, match="bounded capacity"):
        create((society, rich), world)


def test_world_digest_and_registered_accounts_must_match(world, market):
    society, original = market
    bogus = replace(original, world_digest="a" * 64)
    with pytest.raises(EconomyError):
        create((society, bogus), world)
    with pytest.raises(EconomyError):
        new_logistics(
            replace(original.economy, accounts=original.economy.accounts[1:]),
            society, world, authorized=True,
        )
