from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from skeleton.frontier.commerce import (
    BundleGrant,
    BundlePurchaseHistory,
    BundleSpec,
    CurrencyPackSpec,
    ShopItemSpec,
    VerifiedPurchaseEvidence,
    apply_debits,
    generate_daily_deals,
    mark_daily_deal_claimed,
    plan_bundle_purchase,
    plan_currency_pack_purchase,
    quote_daily_deal_purchase,
    quote_shop_purchase,
    record_bundle_purchase,
    shop_item_digest,
)


def _proof(seed: str = "proof") -> str:
    import hashlib
    return hashlib.sha256(seed.encode()).hexdigest()


def _evidence(
    *,
    subject_id: str = "user-1",
    product_id: str = "starter_pack",
    transaction_id: str = "txn-1",
    price_minor: int = 499,
    currency: str = "USD",
    verified_at: datetime | None = None,
) -> VerifiedPurchaseEvidence:
    return VerifiedPurchaseEvidence(
        subject_id=subject_id,
        product_id=product_id,
        transaction_id=transaction_id,
        platform="ios",
        currency=currency,
        price_minor=price_minor,
        verified_at=verified_at or datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
        proof_sha256=_proof(transaction_id),
    )


def test_negative_or_zero_quantity_cannot_credit_wallet():
    item = ShopItemSpec(
        id="bait_worm",
        item_type="bait",
        cost={"coins": 100},
        grant_quantity=10,
    )
    with pytest.raises(ValueError, match="positive"):
        quote_shop_purchase(item, player_level=10, balances={"coins": 1_000}, quantity=0)
    with pytest.raises(ValueError, match="negative"):
        quote_shop_purchase(item, player_level=10, balances={"coins": 1_000}, quantity=-2)


def test_level_balance_and_non_consumable_ownership_are_fail_closed():
    rod = ShopItemSpec(
        id="rod_carbon",
        item_type="rod",
        cost={"coins": 2_500},
        unlock_level=10,
    )
    with pytest.raises(PermissionError, match="requires level 10"):
        quote_shop_purchase(rod, player_level=9, balances={"coins": 9_999})
    with pytest.raises(PermissionError, match="insufficient coins"):
        quote_shop_purchase(rod, player_level=10, balances={"coins": 2_499})
    with pytest.raises(ValueError, match="already owned"):
        quote_shop_purchase(
            rod,
            player_level=10,
            balances={"coins": 9_999},
            owned_item_ids={"rod_carbon"},
        )
    with pytest.raises(ValueError, match="one at a time"):
        quote_shop_purchase(rod, player_level=10, balances={"coins": 9_999}, quantity=2)


def test_consumable_purchase_scales_catalog_cost_and_grant():
    bait = ShopItemSpec(
        id="bait_premium",
        item_type="bait",
        cost={"coins": 300},
        unlock_level=5,
        grant_quantity=10,
    )
    plan = quote_shop_purchase(
        bait,
        player_level=5,
        balances={"coins": 1_000},
        quantity=3,
    )
    assert plan.debits == {"coins": 900}
    assert plan.bait_increments == {"bait_premium": 30}
    assert apply_debits({"coins": 1_000, "gems": 5}, plan.debits) == {"coins": 100, "gems": 5}


def test_upgrade_effects_scale_without_mutating_wallet_in_policy():
    upgrade = ShopItemSpec(
        id="aquarium_expansion",
        item_type="upgrade",
        cost={"coins": 2_000},
        unlock_level=5,
        effects={"aquarium_slots": 10},
    )
    plan = quote_shop_purchase(
        upgrade,
        player_level=20,
        balances={"coins": 10_000},
        quantity=2,
    )
    assert plan.debits == {"coins": 4_000}
    assert plan.effect_increments == {"aquarium_slots": 20}


def test_daily_deals_are_stable_per_subject_day_and_catalog_bound():
    items = (
        ShopItemSpec(id="rod_bamboo", item_type="rod", cost={"coins": 500}),
        ShopItemSpec(id="bait_worm", item_type="bait", cost={"coins": 100}, grant_quantity=10),
        ShopItemSpec(
            id="tackle_box_upgrade",
            item_type="upgrade",
            cost={"coins": 1_500},
            effects={"inventory_slots": 20},
        ),
        ShopItemSpec(id="lure_golden", item_type="lure", cost={"gems": 100}, unlock_level=15),
    )
    day = date(2026, 9, 15)
    first = generate_daily_deals("user-1", day, items)
    second = generate_daily_deals("user-1", day, items)
    other = generate_daily_deals("user-2", day, items)

    assert first == second
    assert len(first) == 3
    assert first != other
    assert all(deal.subject_id == "user-1" for deal in first)
    assert all(
        deal.item_sha256 == shop_item_digest(next(i for i in items if i.id == deal.item_id))
        for deal in first
    )


def test_daily_deal_purchase_rejects_subject_expiry_and_catalog_rebinding():
    item = ShopItemSpec(id="rod_bamboo", item_type="rod", cost={"coins": 500})
    deal = generate_daily_deals("user-1", date(2026, 9, 15), (item,), count=1)[0]

    with pytest.raises(PermissionError, match="another subject"):
        quote_daily_deal_purchase(
            deal,
            item,
            subject_id="user-2",
            now=datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
            player_level=1,
            balances={"coins": 500},
        )
    with pytest.raises(ValueError, match="expired"):
        quote_daily_deal_purchase(
            deal,
            item,
            subject_id="user-1",
            now=datetime(2026, 9, 16, 0, tzinfo=timezone.utc),
            player_level=1,
            balances={"coins": 500},
        )

    forged_catalog_item = ShopItemSpec(id="rod_bamboo", item_type="rod", cost={"coins": 1})
    with pytest.raises(ValueError, match="binding mismatch"):
        quote_daily_deal_purchase(
            deal,
            forged_catalog_item,
            subject_id="user-1",
            now=datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
            player_level=1,
            balances={"coins": 500},
        )


def test_daily_deal_claim_is_single_use():
    item = ShopItemSpec(id="bait_worm", item_type="bait", cost={"coins": 100}, grant_quantity=10)
    deal = generate_daily_deals("u", date(2026, 9, 15), (item,), count=1)[0]
    claimed = mark_daily_deal_claimed(deal)
    assert claimed.claimed is True
    with pytest.raises(ValueError, match="already claimed"):
        mark_daily_deal_claimed(claimed)


def test_currency_pack_requires_exact_verified_subject_product_price_and_currency():
    pack = CurrencyPackSpec(id="gems_medium", grant_currency="gems", amount=280, price_minor=499)
    plan = plan_currency_pack_purchase(
        pack,
        _evidence(product_id="gems_medium", price_minor=499),
        subject_id="user-1",
    )
    assert plan.increments == {"gems": 280}

    with pytest.raises(ValueError, match="price/currency mismatch"):
        plan_currency_pack_purchase(
            pack,
            _evidence(product_id="gems_medium", price_minor=99),
            subject_id="user-1",
        )
    with pytest.raises(PermissionError, match="another subject"):
        plan_currency_pack_purchase(
            pack,
            _evidence(subject_id="attacker", product_id="gems_medium", price_minor=499),
            subject_id="user-1",
        )


def test_currency_pack_rejects_transaction_replay():
    pack = CurrencyPackSpec(id="coins_small", grant_currency="coins", amount=1_000, price_minor=99)
    with pytest.raises(ValueError, match="already been consumed"):
        plan_currency_pack_purchase(
            pack,
            _evidence(product_id="coins_small", price_minor=99, transaction_id="txn-used"),
            subject_id="user-1",
            consumed_transaction_ids={"txn-used"},
        )


def _starter_bundle() -> BundleSpec:
    return BundleSpec(
        id="starter_pack",
        price_minor=499,
        one_time_only=True,
        grants=(
            BundleGrant("coins", 5_000),
            BundleGrant("gems", 100),
            BundleGrant("item", item_id="rod_bamboo"),
            BundleGrant("bait", 50, item_id="bait_worm"),
            BundleGrant("energy", 100),
            BundleGrant("vip", 30),
        ),
    )


def test_bundle_reward_plan_aggregates_source_grant_shapes():
    bundle = _starter_bundle()
    now = datetime(2026, 9, 15, 13, tzinfo=timezone.utc)
    plan = plan_bundle_purchase(
        bundle,
        _evidence(),
        BundlePurchaseHistory(),
        subject_id="user-1",
        now=now,
    )
    assert plan.currency_increments == {"coins": 5_000, "gems": 100}
    assert plan.item_grants == ("rod_bamboo",)
    assert plan.bait_increments == {"bait_worm": 50}
    assert plan.energy_increment == 100
    assert plan.vip_days == 30


def test_one_time_bundle_and_transaction_replay_are_enforced():
    bundle = _starter_bundle()
    now = datetime(2026, 9, 15, 13, tzinfo=timezone.utc)
    plan = plan_bundle_purchase(
        bundle,
        _evidence(),
        BundlePurchaseHistory(),
        subject_id="user-1",
        now=now,
    )
    history = record_bundle_purchase(BundlePurchaseHistory(), bundle, plan, purchased_at=now)

    with pytest.raises(ValueError, match="already been consumed"):
        plan_bundle_purchase(
            bundle,
            _evidence(),
            history,
            subject_id="user-1",
            now=now + timedelta(minutes=1),
        )
    with pytest.raises(ValueError, match="one-time bundle"):
        plan_bundle_purchase(
            bundle,
            _evidence(transaction_id="txn-2"),
            history,
            subject_id="user-1",
            now=now + timedelta(minutes=1),
        )


def test_repeatable_bundle_cooldown_is_enforced():
    bundle = BundleSpec(
        id="weekly_booster",
        price_minor=299,
        cooldown_days=7,
        grants=(BundleGrant("coins", 10_000),),
    )
    purchased_at = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
    history = BundlePurchaseHistory(
        purchased_product_ids=frozenset({"weekly_booster"}),
        last_purchase_at={"weekly_booster": purchased_at},
        consumed_transaction_ids=frozenset({"old-txn"}),
    )

    with pytest.raises(PermissionError, match="cooldown"):
        plan_bundle_purchase(
            bundle,
            _evidence(
                product_id="weekly_booster",
                transaction_id="new-txn",
                price_minor=299,
                verified_at=datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
            ),
            history,
            subject_id="user-1",
            now=datetime(2026, 9, 15, 13, tzinfo=timezone.utc),
        )

    plan = plan_bundle_purchase(
        bundle,
        _evidence(
            product_id="weekly_booster",
            transaction_id="newer-txn",
            price_minor=299,
            verified_at=datetime(2026, 9, 17, 12, tzinfo=timezone.utc),
        ),
        history,
        subject_id="user-1",
        now=datetime(2026, 9, 17, 13, tzinfo=timezone.utc),
    )
    assert plan.currency_increments == {"coins": 10_000}


def test_verified_purchase_cannot_be_rebound_to_another_product():
    bundle = _starter_bundle()
    with pytest.raises(ValueError, match="product mismatch"):
        plan_bundle_purchase(
            bundle,
            _evidence(product_id="legendary_pack", price_minor=499),
            BundlePurchaseHistory(),
            subject_id="user-1",
            now=datetime(2026, 9, 15, 13, tzinfo=timezone.utc),
        )


def test_future_verified_timestamp_fails_closed():
    bundle = _starter_bundle()
    now = datetime(2026, 9, 15, 13, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="future"):
        plan_bundle_purchase(
            bundle,
            _evidence(verified_at=now + timedelta(hours=1)),
            BundlePurchaseHistory(),
            subject_id="user-1",
            now=now,
        )


def test_bundle_grants_reject_unknown_types_and_duplicate_non_consumables():
    with pytest.raises(ValueError, match="unsupported"):
        BundleGrant("mystery")

    bundle = BundleSpec(
        id="bad_pack",
        price_minor=99,
        grants=(
            BundleGrant("item", item_id="rod_bamboo"),
            BundleGrant("item", item_id="rod_bamboo"),
        ),
    )
    with pytest.raises(ValueError, match="duplicate bundle item"):
        plan_bundle_purchase(
            bundle,
            _evidence(product_id="bad_pack", price_minor=99),
            BundlePurchaseHistory(),
            subject_id="user-1",
            now=datetime(2026, 9, 15, 13, tzinfo=timezone.utc),
        )
