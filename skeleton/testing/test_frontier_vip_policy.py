from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib

import pytest

from skeleton.frontier.commerce import VerifiedPurchaseEvidence
from skeleton.frontier.vip import (
    VIPState,
    cancel_auto_renew,
    plan_daily_vip_claim,
    plan_gem_subscription,
    plan_trial_subscription,
    plan_usd_subscription,
    plan_vip_benefits,
    refresh_vip,
    source_default_vip_tiers,
)


def _tier(number: int):
    return source_default_vip_tiers()[number - 1]


def _evidence(
    *,
    product_id: str,
    price_minor: int,
    transaction_id: str = "txn-1",
    subject_id: str = "user-1",
    verified_at: datetime | None = None,
):
    return VerifiedPurchaseEvidence(
        subject_id=subject_id,
        product_id=product_id,
        transaction_id=transaction_id,
        platform="ios",
        currency="USD",
        price_minor=price_minor,
        verified_at=verified_at or datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
        proof_sha256=hashlib.sha256(transaction_id.encode()).hexdigest(),
    )


def test_negative_and_zero_duration_cannot_credit_gems_or_activate_vip():
    for months in (0, -1):
        with pytest.raises(ValueError):
            plan_gem_subscription(
                VIPState(),
                _tier(1),
                duration_months=months,
                gem_balance=1_000,
                now=datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
            )


def test_gem_subscription_is_wallet_neutral_plan_with_exact_debit():
    now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    plan = plan_gem_subscription(
        VIPState(), _tier(2), duration_months=2, gem_balance=500, now=now
    )
    assert plan.gem_debit == 400
    assert plan.duration_days == 60
    assert plan.state.tier == 2
    assert plan.state.expires_at == now + timedelta(days=60)
    assert plan.state.auto_renew is False


def test_gem_subscription_rejects_insufficient_balance():
    with pytest.raises(PermissionError, match="insufficient gems"):
        plan_gem_subscription(
            VIPState(),
            _tier(4),
            duration_months=1,
            gem_balance=799,
            now=datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
        )


def test_trial_is_fixed_bronze_three_days_and_single_use():
    now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    plan = plan_trial_subscription(VIPState(), now=now)
    assert plan.state.tier == 1
    assert plan.duration_days == 3
    assert plan.state.trial_used is True
    with pytest.raises(ValueError, match="already been used"):
        plan_trial_subscription(plan.state, now=now + timedelta(days=4))


def test_usd_subscription_requires_verified_exact_product_price_and_subject():
    now = datetime(2026, 9, 15, 13, tzinfo=timezone.utc)
    spec = _tier(3)
    evidence = _evidence(product_id="vip_tier_3_2m", price_minor=1_998)
    plan = plan_usd_subscription(
        VIPState(),
        spec,
        evidence,
        subject_id="user-1",
        duration_months=2,
        now=now,
    )
    assert plan.state.tier == 3
    assert plan.state.auto_renew is True
    assert "txn-1" in plan.state.consumed_transaction_ids

    with pytest.raises(ValueError, match="product mismatch"):
        plan_usd_subscription(
            VIPState(),
            spec,
            _evidence(product_id="vip_tier_4_2m", price_minor=1_998),
            subject_id="user-1",
            duration_months=2,
            now=now,
        )
    with pytest.raises(ValueError, match="price/currency mismatch"):
        plan_usd_subscription(
            VIPState(),
            spec,
            _evidence(product_id="vip_tier_3_2m", price_minor=1),
            subject_id="user-1",
            duration_months=2,
            now=now,
        )
    with pytest.raises(PermissionError, match="another subject"):
        plan_usd_subscription(
            VIPState(),
            spec,
            _evidence(
                subject_id="attacker",
                product_id="vip_tier_3_2m",
                price_minor=1_998,
            ),
            subject_id="user-1",
            duration_months=2,
            now=now,
        )


def test_usd_transaction_replay_is_rejected():
    now = datetime(2026, 9, 15, 13, tzinfo=timezone.utc)
    first = plan_usd_subscription(
        VIPState(),
        _tier(1),
        _evidence(product_id="vip_tier_1_1m", price_minor=299),
        subject_id="user-1",
        duration_months=1,
        now=now,
    )
    with pytest.raises(ValueError, match="already been consumed"):
        plan_usd_subscription(
            first.state,
            _tier(1),
            _evidence(product_id="vip_tier_1_1m", price_minor=299),
            subject_id="user-1",
            duration_months=1,
            now=now + timedelta(minutes=1),
        )


def test_active_subscription_extends_from_existing_expiry_not_now():
    now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    first = plan_gem_subscription(
        VIPState(), _tier(1), duration_months=1, gem_balance=500, now=now
    )
    extension = plan_gem_subscription(
        first.state,
        _tier(2),
        duration_months=1,
        gem_balance=500,
        now=now + timedelta(days=10),
    )
    assert extension.state.tier == 2
    assert extension.state.expires_at == now + timedelta(days=60)
    assert extension.state.started_at == now


def test_expired_vip_normalizes_to_free_before_benefits():
    now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    active = plan_gem_subscription(
        VIPState(), _tier(1), duration_months=1, gem_balance=100, now=now
    ).state
    expired = refresh_vip(active, now=now + timedelta(days=31))
    assert expired.tier == 0
    assert expired.expires_at is None
    with pytest.raises(PermissionError, match="not currently active"):
        plan_vip_benefits(expired, _tier(1), now=now + timedelta(days=31))


def test_benefit_plan_projects_bonuses_flags_items_and_titles():
    now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    state = plan_gem_subscription(
        VIPState(), _tier(4), duration_months=1, gem_balance=800, now=now
    ).state
    benefits = plan_vip_benefits(state, _tier(4), now=now)
    assert benefits.percentage_bonuses["xp_bonus"] == 100
    assert benefits.percentage_bonuses["coin_bonus"] == 25
    assert "ad_free" in benefits.flags
    assert "diamond_rod" in benefits.item_grants
    assert benefits.title_grants == ("Diamond Fisher",)


def test_daily_claim_is_date_idempotent_and_tier_bound():
    now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    state = plan_gem_subscription(
        VIPState(), _tier(2), duration_months=1, gem_balance=200, now=now
    ).state
    claim = plan_daily_vip_claim(
        state, _tier(2), claim_date=date(2026, 9, 15), now=now
    )
    assert claim.increments == {"gems": 25, "coins": 500}
    with pytest.raises(ValueError, match="already claimed"):
        plan_daily_vip_claim(
            claim.state,
            _tier(2),
            claim_date=date(2026, 9, 15),
            now=now,
        )
    with pytest.raises(PermissionError, match="not active"):
        plan_daily_vip_claim(
            claim.state,
            _tier(3),
            claim_date=date(2026, 9, 16),
            now=now + timedelta(days=1),
        )


def test_cancel_disables_renewal_without_destroying_remaining_entitlement():
    now = datetime(2026, 9, 15, 13, tzinfo=timezone.utc)
    state = plan_usd_subscription(
        VIPState(),
        _tier(1),
        _evidence(product_id="vip_tier_1_1m", price_minor=299),
        subject_id="user-1",
        duration_months=1,
        now=now,
    ).state
    cancelled = cancel_auto_renew(state, now=now + timedelta(days=1))
    assert cancelled.auto_renew is False
    assert cancelled.tier == 1
    assert cancelled.expires_at == state.expires_at


def test_source_default_tiers_preserve_core_prices_and_benefits():
    tiers = source_default_vip_tiers()
    assert [tier.tier for tier in tiers] == [1, 2, 3, 4]
    assert [tier.gem_cost_monthly for tier in tiers] == [100, 200, 400, 800]
    assert [tier.usd_price_minor_monthly for tier in tiers] == [299, 599, 999, 1999]
