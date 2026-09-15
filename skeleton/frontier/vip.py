"""Dependency-free VIP entitlement policy promoted from Lorebuffa/Openworld.

Both source repositories share ``backend/vip_routes.py`` blob
``f67aedc7877bf6e8c9e6bf11d97507f426383ac1``.  The source catalogs and
presentation fields remain source-owned.  This module retains portable
subscription, expiry, trial, daily-reward and benefit semantics while routing
paid USD authorization through the canonical commerce verification boundary.

Hardening over the source implementation:
- subscription duration is strictly positive;
- payment methods are an explicit closed set;
- USD subscriptions require externally verified purchase evidence;
- provider transactions are replay protected;
- trials are one-time, fixed to Bronze and three days;
- gem purchases produce debit plans rather than mutating wallets;
- entitlement extension is calculated from max(now, current expiry);
- benefit grants and daily rewards are pure, idempotent plans;
- expired memberships are normalized before benefits can be queried.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

from skeleton.frontier.commerce import VerifiedPurchaseEvidence


PAYMENT_METHODS = frozenset({"gems", "usd", "trial"})
MAX_VIP_TIER = 4
TRIAL_TIER = 1
TRIAL_DAYS = 3


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be non-empty and normalized")
    return value


def _token(value: object, field_name: str) -> str:
    value = _text(value, field_name)
    lowered = value.lower()
    if lowered != value:
        raise ValueError(f"{field_name} must be lowercase and normalized")
    return lowered


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _positive_int(value: object, field_name: str) -> int:
    value = _nonnegative_int(value, field_name)
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _tier(value: object, field_name: str = "VIP tier", *, allow_free: bool = True) -> int:
    tier = _nonnegative_int(value, field_name)
    minimum = 0 if allow_free else 1
    if tier < minimum or tier > MAX_VIP_TIER:
        raise ValueError(f"{field_name} must be between {minimum} and {MAX_VIP_TIER}")
    return tier


def _count_map(values: Mapping[str, int], field_name: str) -> Mapping[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, int] = {}
    for raw_key, raw_value in values.items():
        key = _token(raw_key, f"{field_name} key")
        normalized[key] = _nonnegative_int(raw_value, f"{field_name}[{key!r}]")
    return MappingProxyType(normalized)


def _tokens(values: Iterable[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _token(raw, f"{field_name} entry")
        if value in seen:
            raise ValueError(f"duplicate {field_name} entry: {value}")
        seen.add(value)
        result.append(value)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class VIPBenefit:
    kind: str
    amount: int = 0
    item_id: str | None = None
    title: str | None = None

    def __post_init__(self) -> None:
        kind = _token(self.kind, "VIP benefit kind")
        amount = _nonnegative_int(self.amount, "VIP benefit amount")
        item_id = self.item_id
        title = self.title
        if item_id is not None:
            item_id = _token(item_id, "VIP benefit item_id")
        if title is not None:
            title = _text(title, "VIP benefit title")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "item_id", item_id)
        object.__setattr__(self, "title", title)


@dataclass(frozen=True, slots=True)
class VIPTierSpec:
    tier: int
    gem_cost_monthly: int
    usd_price_minor_monthly: int
    benefits: tuple[VIPBenefit, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tier", _tier(self.tier, allow_free=False))
        object.__setattr__(
            self,
            "gem_cost_monthly",
            _positive_int(self.gem_cost_monthly, "VIP gem_cost_monthly"),
        )
        object.__setattr__(
            self,
            "usd_price_minor_monthly",
            _positive_int(self.usd_price_minor_monthly, "VIP usd_price_minor_monthly"),
        )
        if not isinstance(self.benefits, tuple):
            raise TypeError("VIP benefits must be a tuple")
        for benefit in self.benefits:
            if not isinstance(benefit, VIPBenefit):
                raise TypeError("VIP benefits must contain VIPBenefit values")


@dataclass(frozen=True, slots=True)
class VIPState:
    tier: int = 0
    started_at: datetime | None = None
    expires_at: datetime | None = None
    auto_renew: bool = False
    trial_used: bool = False
    total_days_vip: int = 0
    last_daily_claim: date | None = None
    consumed_transaction_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        tier = _tier(self.tier)
        started = self.started_at
        expires = self.expires_at
        if started is not None:
            started = _aware(started, "VIP started_at")
        if expires is not None:
            expires = _aware(expires, "VIP expires_at")
        if tier == 0:
            if started is not None or expires is not None:
                raise ValueError("free VIP state must not retain active subscription timestamps")
            if self.auto_renew:
                raise ValueError("free VIP state cannot auto-renew")
        else:
            if started is None or expires is None:
                raise ValueError("active VIP tier requires started_at and expires_at")
            if expires <= started:
                raise ValueError("VIP expires_at must be after started_at")
        if not isinstance(self.auto_renew, bool):
            raise TypeError("VIP auto_renew must be a boolean")
        if not isinstance(self.trial_used, bool):
            raise TypeError("VIP trial_used must be a boolean")
        total_days = _nonnegative_int(self.total_days_vip, "VIP total_days_vip")
        if self.last_daily_claim is not None and (
            not isinstance(self.last_daily_claim, date)
            or isinstance(self.last_daily_claim, datetime)
        ):
            raise TypeError("VIP last_daily_claim must be a date")
        if isinstance(self.consumed_transaction_ids, (str, bytes)):
            raise TypeError("VIP consumed_transaction_ids must be an iterable")
        consumed = frozenset(
            _text(value, "VIP consumed transaction id")
            for value in self.consumed_transaction_ids
        )
        object.__setattr__(self, "tier", tier)
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(self, "total_days_vip", total_days)
        object.__setattr__(self, "consumed_transaction_ids", consumed)

    @property
    def is_active(self) -> bool:
        return self.tier > 0


def refresh_vip(state: VIPState, *, now: datetime) -> VIPState:
    if not isinstance(state, VIPState):
        raise TypeError("state must be VIPState")
    current = _aware(now, "VIP refresh now")
    if state.tier == 0 or state.expires_at is None or state.expires_at > current:
        return state
    return VIPState(
        tier=0,
        trial_used=state.trial_used,
        total_days_vip=state.total_days_vip,
        last_daily_claim=state.last_daily_claim,
        consumed_transaction_ids=state.consumed_transaction_ids,
    )


@dataclass(frozen=True, slots=True)
class VIPSubscriptionPlan:
    state: VIPState
    payment_method: str
    duration_days: int
    gem_debit: int = 0
    transaction_id: str | None = None

    def __post_init__(self) -> None:
        method = _token(self.payment_method, "VIP payment_method")
        if method not in PAYMENT_METHODS:
            raise ValueError(f"unsupported VIP payment method: {method}")
        object.__setattr__(self, "payment_method", method)
        object.__setattr__(self, "duration_days", _positive_int(self.duration_days, "VIP duration_days"))
        object.__setattr__(self, "gem_debit", _nonnegative_int(self.gem_debit, "VIP gem_debit"))
        if method == "gems" and self.gem_debit < 1:
            raise ValueError("gem VIP purchase must have a positive debit")
        if method != "gems" and self.gem_debit != 0:
            raise ValueError("only gem VIP purchase may contain a gem debit")
        if method == "usd" and self.transaction_id is None:
            raise ValueError("USD VIP purchase requires transaction_id")
        if self.transaction_id is not None:
            object.__setattr__(
                self,
                "transaction_id",
                _text(self.transaction_id, "VIP transaction_id"),
            )


def _extended_state(
    state: VIPState,
    *,
    tier: int,
    duration_days: int,
    now: datetime,
    auto_renew: bool,
    trial_used: bool | None = None,
    transaction_id: str | None = None,
) -> VIPState:
    current = _aware(now, "VIP subscription now")
    existing = refresh_vip(state, now=current)
    duration = _positive_int(duration_days, "VIP duration_days")
    selected_tier = _tier(tier, allow_free=False)
    base = (
        existing.expires_at
        if existing.tier > 0 and existing.expires_at is not None and existing.expires_at > current
        else current
    )
    started = existing.started_at if existing.tier > 0 and existing.started_at is not None else current
    transactions = set(existing.consumed_transaction_ids)
    if transaction_id is not None:
        transaction = _text(transaction_id, "VIP transaction_id")
        if transaction in transactions:
            raise ValueError("VIP transaction has already been consumed")
        transactions.add(transaction)
    return VIPState(
        tier=selected_tier,
        started_at=started,
        expires_at=base + timedelta(days=duration),
        auto_renew=auto_renew,
        trial_used=existing.trial_used if trial_used is None else trial_used,
        total_days_vip=existing.total_days_vip + duration,
        last_daily_claim=existing.last_daily_claim,
        consumed_transaction_ids=frozenset(transactions),
    )


def plan_gem_subscription(
    state: VIPState,
    spec: VIPTierSpec,
    *,
    duration_months: int,
    gem_balance: int,
    now: datetime,
) -> VIPSubscriptionPlan:
    months = _positive_int(duration_months, "VIP duration_months")
    balance = _nonnegative_int(gem_balance, "VIP gem_balance")
    debit = spec.gem_cost_monthly * months
    if balance < debit:
        raise PermissionError("insufficient gems for VIP subscription")
    duration = months * 30
    next_state = _extended_state(
        state,
        tier=spec.tier,
        duration_days=duration,
        now=now,
        auto_renew=False,
    )
    return VIPSubscriptionPlan(
        state=next_state,
        payment_method="gems",
        duration_days=duration,
        gem_debit=debit,
    )


def plan_trial_subscription(state: VIPState, *, now: datetime) -> VIPSubscriptionPlan:
    if state.trial_used:
        raise ValueError("VIP trial has already been used")
    next_state = _extended_state(
        state,
        tier=TRIAL_TIER,
        duration_days=TRIAL_DAYS,
        now=now,
        auto_renew=False,
        trial_used=True,
    )
    return VIPSubscriptionPlan(
        state=next_state,
        payment_method="trial",
        duration_days=TRIAL_DAYS,
    )


def plan_usd_subscription(
    state: VIPState,
    spec: VIPTierSpec,
    evidence: VerifiedPurchaseEvidence,
    *,
    subject_id: str,
    duration_months: int,
    now: datetime,
) -> VIPSubscriptionPlan:
    months = _positive_int(duration_months, "VIP duration_months")
    current = _aware(now, "VIP USD purchase now")
    subject = _text(subject_id, "VIP subject_id")
    if not isinstance(evidence, VerifiedPurchaseEvidence):
        raise TypeError("evidence must be VerifiedPurchaseEvidence")
    expected_product = f"vip_tier_{spec.tier}_{months}m"
    if evidence.subject_id != subject:
        raise PermissionError("verified VIP purchase belongs to another subject")
    if evidence.product_id != expected_product:
        raise ValueError("verified VIP product mismatch")
    expected_price = spec.usd_price_minor_monthly * months
    if evidence.currency != "USD" or evidence.price_minor != expected_price:
        raise ValueError("verified VIP price/currency mismatch")
    if evidence.transaction_id in state.consumed_transaction_ids:
        raise ValueError("VIP transaction has already been consumed")
    if evidence.verified_at > current + timedelta(minutes=5):
        raise ValueError("verified VIP timestamp is implausibly in the future")
    duration = months * 30
    next_state = _extended_state(
        state,
        tier=spec.tier,
        duration_days=duration,
        now=current,
        auto_renew=True,
        transaction_id=evidence.transaction_id,
    )
    return VIPSubscriptionPlan(
        state=next_state,
        payment_method="usd",
        duration_days=duration,
        transaction_id=evidence.transaction_id,
    )


def cancel_auto_renew(state: VIPState, *, now: datetime) -> VIPState:
    current = refresh_vip(state, now=now)
    if current.tier == 0:
        raise ValueError("cannot cancel an inactive VIP subscription")
    return replace(current, auto_renew=False)


@dataclass(frozen=True, slots=True)
class VIPBenefitPlan:
    percentage_bonuses: Mapping[str, int]
    flags: frozenset[str]
    item_grants: tuple[str, ...]
    title_grants: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "percentage_bonuses",
            _count_map(self.percentage_bonuses, "VIP percentage_bonuses"),
        )
        if isinstance(self.flags, (str, bytes)):
            raise TypeError("VIP flags must be an iterable")
        object.__setattr__(
            self,
            "flags",
            frozenset(_token(value, "VIP flag") for value in self.flags),
        )
        object.__setattr__(self, "item_grants", _tokens(self.item_grants, "VIP item grants"))
        if isinstance(self.title_grants, (str, bytes)):
            raise TypeError("VIP title_grants must be an iterable")
        titles: list[str] = []
        for title in self.title_grants:
            normalized = _text(title, "VIP title grant")
            if normalized in titles:
                raise ValueError(f"duplicate VIP title grant: {normalized}")
            titles.append(normalized)
        object.__setattr__(self, "title_grants", tuple(titles))


def plan_vip_benefits(
    state: VIPState,
    spec: VIPTierSpec,
    *,
    now: datetime,
) -> VIPBenefitPlan:
    current = refresh_vip(state, now=now)
    if current.tier == 0 or current.tier != spec.tier:
        raise PermissionError("VIP tier is not currently active")
    percentages: dict[str, int] = {}
    flags: set[str] = set()
    items: list[str] = []
    titles: list[str] = []
    for benefit in spec.benefits:
        if benefit.kind in {
            "energy_max_bonus",
            "energy_regen_bonus",
            "xp_bonus",
            "coin_bonus",
            "rare_fish_bonus",
            "legendary_fish_bonus",
        }:
            percentages[benefit.kind] = max(percentages.get(benefit.kind, 0), benefit.amount)
        elif benefit.kind in {"ad_free", "priority_support", "early_access", "monthly_mystery_box"}:
            flags.add(benefit.kind)
        elif benefit.kind.startswith("exclusive_") and benefit.item_id is not None:
            if benefit.item_id not in items:
                items.append(benefit.item_id)
        elif benefit.kind == "exclusive_title" and benefit.title is not None:
            if benefit.title not in titles:
                titles.append(benefit.title)
    return VIPBenefitPlan(
        percentage_bonuses=percentages,
        flags=frozenset(flags),
        item_grants=tuple(items),
        title_grants=tuple(titles),
    )


@dataclass(frozen=True, slots=True)
class VIPDailyClaimPlan:
    state: VIPState
    increments: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "increments", _count_map(self.increments, "VIP daily increments"))
        if not self.increments or all(value == 0 for value in self.increments.values()):
            raise ValueError("VIP daily claim must award at least one reward")


def plan_daily_vip_claim(
    state: VIPState,
    spec: VIPTierSpec,
    *,
    claim_date: date,
    now: datetime,
) -> VIPDailyClaimPlan:
    if not isinstance(claim_date, date) or isinstance(claim_date, datetime):
        raise TypeError("VIP claim_date must be a date")
    current = refresh_vip(state, now=now)
    if current.tier == 0 or current.tier != spec.tier:
        raise PermissionError("VIP membership is not active")
    if current.last_daily_claim == claim_date:
        raise ValueError("VIP daily reward already claimed for this date")
    increments: dict[str, int] = {}
    for benefit in spec.benefits:
        if benefit.kind == "daily_gems":
            increments["gems"] = increments.get("gems", 0) + benefit.amount
        elif benefit.kind == "daily_coins":
            increments["coins"] = increments.get("coins", 0) + benefit.amount
    if not increments:
        raise ValueError("VIP tier has no daily currency reward")
    return VIPDailyClaimPlan(
        state=replace(current, last_daily_claim=claim_date),
        increments=increments,
    )


def source_default_vip_tiers() -> tuple[VIPTierSpec, ...]:
    """Portable subset of the exact source tier semantics."""

    return (
        VIPTierSpec(
            tier=1,
            gem_cost_monthly=100,
            usd_price_minor_monthly=299,
            benefits=(
                VIPBenefit("daily_gems", 10),
                VIPBenefit("energy_max_bonus", 10),
                VIPBenefit("xp_bonus", 10),
                VIPBenefit("ad_free"),
            ),
        ),
        VIPTierSpec(
            tier=2,
            gem_cost_monthly=200,
            usd_price_minor_monthly=599,
            benefits=(
                VIPBenefit("daily_gems", 25),
                VIPBenefit("daily_coins", 500),
                VIPBenefit("energy_max_bonus", 25),
                VIPBenefit("energy_regen_bonus", 25),
                VIPBenefit("xp_bonus", 25),
                VIPBenefit("rare_fish_bonus", 15),
                VIPBenefit("ad_free"),
                VIPBenefit("exclusive_lure", item_id="silver_lure"),
            ),
        ),
        VIPTierSpec(
            tier=3,
            gem_cost_monthly=400,
            usd_price_minor_monthly=999,
            benefits=(
                VIPBenefit("daily_gems", 50),
                VIPBenefit("daily_coins", 1_500),
                VIPBenefit("energy_max_bonus", 50),
                VIPBenefit("energy_regen_bonus", 50),
                VIPBenefit("xp_bonus", 50),
                VIPBenefit("rare_fish_bonus", 30),
                VIPBenefit("legendary_fish_bonus", 15),
                VIPBenefit("ad_free"),
                VIPBenefit("exclusive_lure", item_id="gold_lure"),
                VIPBenefit("exclusive_rod", item_id="gold_rod"),
                VIPBenefit("priority_support"),
            ),
        ),
        VIPTierSpec(
            tier=4,
            gem_cost_monthly=800,
            usd_price_minor_monthly=1_999,
            benefits=(
                VIPBenefit("daily_gems", 100),
                VIPBenefit("daily_coins", 3_000),
                VIPBenefit("energy_max_bonus", 100),
                VIPBenefit("energy_regen_bonus", 100),
                VIPBenefit("xp_bonus", 100),
                VIPBenefit("coin_bonus", 25),
                VIPBenefit("rare_fish_bonus", 50),
                VIPBenefit("legendary_fish_bonus", 30),
                VIPBenefit("ad_free"),
                VIPBenefit("exclusive_lure", item_id="diamond_lure"),
                VIPBenefit("exclusive_rod", item_id="diamond_rod"),
                VIPBenefit("exclusive_boat", item_id="diamond_yacht"),
                VIPBenefit("exclusive_title", title="Diamond Fisher"),
                VIPBenefit("early_access"),
                VIPBenefit("priority_support"),
                VIPBenefit("monthly_mystery_box"),
            ),
        ),
    )
