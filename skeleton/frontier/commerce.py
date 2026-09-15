"""Pure commerce policy promoted from shared Lorebuffa/Openworld shop lineage.

The source repositories share ``backend/shop_routes.py`` blob
``c7bb3661f98642bc0e4220b624bcc7fd71e25d25``.  FastAPI, MongoDB, provider
receipt verification, catalog presentation and wallet persistence remain source-owned.

This module promotes the portable rules only:
- level-gated in-game purchases with positive quantities and exact catalog costs;
- non-consumable ownership and consumable quantity semantics;
- deterministic per-user daily deals without mutating process-global RNG state;
- catalog-bound deal quotes;
- externally verified IAP evidence bound to subject/product/price/currency;
- replay-safe one-time/cooldown bundle planning;
- wallet-neutral reward/debit plans.

The promoted boundary intentionally rejects two source trust flaws: negative purchase
quantities cannot become wallet credits, and simulated IAP requests cannot self-authorize
paid bundle/currency entitlements.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta, timezone
from random import Random
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence
import hashlib

from skeleton.frontier.contracts import stable_content_digest


_NON_CONSUMABLE_TYPES = frozenset({"rod", "lure", "boat"})
_SUPPORTED_ITEM_TYPES = frozenset({"rod", "lure", "boat", "bait", "upgrade"})
_SUPPORTED_GRANT_TYPES = frozenset({"coins", "gems", "energy", "item", "bait", "vip"})
_HEX = frozenset("0123456789abcdef")


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


def _money_map(values: Mapping[str, int], field_name: str) -> Mapping[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, int] = {}
    for raw_key, raw_value in values.items():
        key = _token(raw_key, f"{field_name} key")
        if key in normalized:
            raise ValueError(f"duplicate {field_name} key: {key}")
        normalized[key] = _nonnegative_int(raw_value, f"{field_name}[{key!r}]")
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if all(value == 0 for value in normalized.values()):
        raise ValueError(f"{field_name} must contain a positive amount")
    return MappingProxyType(normalized)


def _count_map(values: Mapping[str, int], field_name: str) -> Mapping[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, int] = {}
    for raw_key, raw_value in values.items():
        key = _token(raw_key, f"{field_name} key")
        normalized[key] = _nonnegative_int(raw_value, f"{field_name}[{key!r}]")
    return MappingProxyType(normalized)


def _positive_count_map(values: Mapping[str, int], field_name: str) -> Mapping[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, int] = {}
    for raw_key, raw_value in values.items():
        key = _token(raw_key, f"{field_name} key")
        normalized[key] = _positive_int(raw_value, f"{field_name}[{key!r}]")
    return MappingProxyType(normalized)


def _text_tuple(values: Iterable[str], field_name: str) -> tuple[str, ...]:
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


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _sha256(value: object, field_name: str) -> str:
    digest = _text(value, field_name)
    if len(digest) != 64 or any(character not in _HEX for character in digest):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return digest


@dataclass(frozen=True, slots=True)
class ShopItemSpec:
    id: str
    item_type: str
    cost: Mapping[str, int]
    unlock_level: int = 1
    grant_quantity: int = 1
    effects: Mapping[str, int] = field(default_factory=dict)
    unlocks: tuple[str, ...] = ()
    repeatable: bool | None = None

    def __post_init__(self) -> None:
        item_id = _token(self.id, "shop item id")
        item_type = _token(self.item_type, "shop item type")
        if item_type not in _SUPPORTED_ITEM_TYPES:
            raise ValueError(f"unsupported shop item type: {item_type}")
        cost = _money_map(self.cost, "shop item cost")
        level = _positive_int(self.unlock_level, "shop item unlock_level")
        quantity = _positive_int(self.grant_quantity, "shop item grant_quantity")
        effects = _positive_count_map(self.effects, "shop item effects")
        unlocks = _text_tuple(self.unlocks, "shop item unlocks")
        repeatable = self.repeatable
        if repeatable is None:
            repeatable = item_type not in _NON_CONSUMABLE_TYPES
        if not isinstance(repeatable, bool):
            raise TypeError("shop item repeatable must be a boolean")
        if item_type in _NON_CONSUMABLE_TYPES and repeatable:
            raise ValueError("rod/lure/boat items must be non-repeatable")
        object.__setattr__(self, "id", item_id)
        object.__setattr__(self, "item_type", item_type)
        object.__setattr__(self, "cost", cost)
        object.__setattr__(self, "unlock_level", level)
        object.__setattr__(self, "grant_quantity", quantity)
        object.__setattr__(self, "effects", effects)
        object.__setattr__(self, "unlocks", unlocks)
        object.__setattr__(self, "repeatable", repeatable)


@dataclass(frozen=True, slots=True)
class ShopPurchasePlan:
    item_id: str
    quantity: int
    debits: Mapping[str, int]
    item_grants: tuple[str, ...] = ()
    bait_increments: Mapping[str, int] = field(default_factory=dict)
    effect_increments: Mapping[str, int] = field(default_factory=dict)
    unlocks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_id", _token(self.item_id, "purchase plan item_id"))
        object.__setattr__(self, "quantity", _positive_int(self.quantity, "purchase plan quantity"))
        object.__setattr__(self, "debits", _money_map(self.debits, "purchase plan debits"))
        object.__setattr__(self, "item_grants", _text_tuple(self.item_grants, "purchase plan item_grants"))
        object.__setattr__(
            self,
            "bait_increments",
            _positive_count_map(self.bait_increments, "purchase plan bait_increments"),
        )
        object.__setattr__(
            self,
            "effect_increments",
            _positive_count_map(self.effect_increments, "purchase plan effect_increments"),
        )
        object.__setattr__(self, "unlocks", _text_tuple(self.unlocks, "purchase plan unlocks"))


def shop_item_digest(item: ShopItemSpec) -> str:
    if not isinstance(item, ShopItemSpec):
        raise TypeError("item must be ShopItemSpec")
    return stable_content_digest(
        {
            "id": item.id,
            "item_type": item.item_type,
            "cost": dict(item.cost),
            "unlock_level": item.unlock_level,
            "grant_quantity": item.grant_quantity,
            "effects": dict(item.effects),
            "unlocks": item.unlocks,
            "repeatable": item.repeatable,
        }
    )


def quote_shop_purchase(
    item: ShopItemSpec,
    *,
    player_level: int,
    balances: Mapping[str, int],
    owned_item_ids: Iterable[str] = (),
    quantity: int = 1,
    cost_override: Mapping[str, int] | None = None,
) -> ShopPurchasePlan:
    """Validate an in-game purchase and return a wallet-neutral plan."""

    if not isinstance(item, ShopItemSpec):
        raise TypeError("item must be ShopItemSpec")
    level = _positive_int(player_level, "player level")
    requested = _positive_int(quantity, "purchase quantity")
    balance_map = _count_map(balances, "wallet balances")
    owned = frozenset(_text_tuple(owned_item_ids, "owned item ids"))

    if level < item.unlock_level:
        raise PermissionError(f"shop item requires level {item.unlock_level}")
    if not item.repeatable:
        if requested != 1:
            raise ValueError("non-repeatable shop items must be purchased one at a time")
        if item.id in owned:
            raise ValueError("shop item is already owned")

    if cost_override is None:
        debits = {currency: amount * requested for currency, amount in item.cost.items()}
    else:
        override = _money_map(cost_override, "shop purchase cost override")
        if set(override) != set(item.cost):
            raise ValueError("shop purchase cost override currencies must match catalog cost")
        debits = dict(override)

    for currency, amount in debits.items():
        if balance_map.get(currency, 0) < amount:
            raise PermissionError(f"insufficient {currency}")

    item_grants: tuple[str, ...] = ()
    bait_increments: dict[str, int] = {}
    effect_increments: dict[str, int] = {}
    if item.item_type == "bait":
        bait_increments[item.id] = item.grant_quantity * requested
    elif item.item_type in _NON_CONSUMABLE_TYPES:
        item_grants = (item.id,)
    elif item.item_type == "upgrade":
        effect_increments = {
            key: amount * requested for key, amount in item.effects.items()
        }

    return ShopPurchasePlan(
        item_id=item.id,
        quantity=requested,
        debits=debits,
        item_grants=item_grants,
        bait_increments=bait_increments,
        effect_increments=effect_increments,
        unlocks=item.unlocks,
    )


def apply_debits(
    balances: Mapping[str, int],
    debits: Mapping[str, int],
) -> Mapping[str, int]:
    """Apply a previously validated debit plan without permitting underflow."""

    current = dict(_count_map(balances, "wallet balances"))
    normalized_debits = _money_map(debits, "wallet debits")
    for currency, amount in normalized_debits.items():
        if current.get(currency, 0) < amount:
            raise PermissionError(f"insufficient {currency}")
    for currency, amount in normalized_debits.items():
        current[currency] = current.get(currency, 0) - amount
    return MappingProxyType(current)


@dataclass(frozen=True, slots=True)
class DailyDeal:
    id: str
    subject_id: str
    deal_date: date
    item_id: str
    item_sha256: str
    discount_percent: int
    discounted_cost: Mapping[str, int]
    expires_at: datetime
    claimed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "daily deal id"))
        object.__setattr__(self, "subject_id", _text(self.subject_id, "daily deal subject_id"))
        if not isinstance(self.deal_date, date) or isinstance(self.deal_date, datetime):
            raise TypeError("daily deal deal_date must be a date")
        object.__setattr__(self, "item_id", _token(self.item_id, "daily deal item_id"))
        object.__setattr__(
            self,
            "item_sha256",
            _sha256(self.item_sha256, "daily deal item_sha256"),
        )
        discount = _positive_int(self.discount_percent, "daily deal discount_percent")
        if discount >= 100:
            raise ValueError("daily deal discount_percent must be below 100")
        object.__setattr__(self, "discount_percent", discount)
        object.__setattr__(
            self,
            "discounted_cost",
            _money_map(self.discounted_cost, "daily deal discounted_cost"),
        )
        object.__setattr__(self, "expires_at", _aware(self.expires_at, "daily deal expires_at"))
        if not isinstance(self.claimed, bool):
            raise TypeError("daily deal claimed must be a boolean")


def _discount_cost(cost: Mapping[str, int], discount_percent: int) -> Mapping[str, int]:
    discount = _positive_int(discount_percent, "discount_percent")
    if discount >= 100:
        raise ValueError("discount_percent must be below 100")
    normalized = _money_map(cost, "discount source cost")
    result: dict[str, int] = {}
    for currency, amount in normalized.items():
        discounted = amount * (100 - discount) // 100
        result[currency] = max(1, discounted) if amount > 0 else 0
    return MappingProxyType(result)


def generate_daily_deals(
    subject_id: str,
    deal_date: date,
    items: Sequence[ShopItemSpec],
    *,
    count: int = 3,
    max_unlock_level: int = 30,
    discount_options: Sequence[int] = (20, 30, 40, 50),
) -> tuple[DailyDeal, ...]:
    """Generate stable per-subject/day item deals with an isolated RNG instance."""

    subject = _text(subject_id, "daily deal subject_id")
    if not isinstance(deal_date, date) or isinstance(deal_date, datetime):
        raise TypeError("deal_date must be a date")
    requested_count = _positive_int(count, "daily deal count")
    max_level = _positive_int(max_unlock_level, "daily deal max_unlock_level")
    if isinstance(items, (str, bytes)):
        raise TypeError("items must be a sequence of ShopItemSpec values")
    catalog: dict[str, ShopItemSpec] = {}
    for item in items:
        if not isinstance(item, ShopItemSpec):
            raise TypeError("items must contain ShopItemSpec values")
        if item.id in catalog:
            raise ValueError(f"duplicate shop item id: {item.id}")
        catalog[item.id] = item
    available = [
        item for item in catalog.values()
        if item.unlock_level <= max_level
    ]
    if not available:
        return ()

    discounts = tuple(_positive_int(value, "daily deal discount option") for value in discount_options)
    if any(value >= 100 for value in discounts):
        raise ValueError("daily deal discounts must be below 100")

    seed_material = f"{subject}\0{deal_date.isoformat()}".encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:16], "big")
    rng = Random(seed)
    selected = rng.sample(available, min(requested_count, len(available)))
    expires_at = datetime.combine(
        deal_date + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    )

    deals: list[DailyDeal] = []
    for item in selected:
        discount = rng.choice(discounts)
        deals.append(
            DailyDeal(
                id=f"deal_{item.id}_{deal_date.isoformat()}",
                subject_id=subject,
                deal_date=deal_date,
                item_id=item.id,
                item_sha256=shop_item_digest(item),
                discount_percent=discount,
                discounted_cost=_discount_cost(item.cost, discount),
                expires_at=expires_at,
            )
        )
    return tuple(deals)


def quote_daily_deal_purchase(
    deal: DailyDeal,
    item: ShopItemSpec,
    *,
    subject_id: str,
    now: datetime,
    player_level: int,
    balances: Mapping[str, int],
    owned_item_ids: Iterable[str] = (),
) -> ShopPurchasePlan:
    if not isinstance(deal, DailyDeal):
        raise TypeError("deal must be DailyDeal")
    if not isinstance(item, ShopItemSpec):
        raise TypeError("item must be ShopItemSpec")
    subject = _text(subject_id, "daily deal subject_id")
    current = _aware(now, "daily deal now")
    if deal.subject_id != subject:
        raise PermissionError("daily deal belongs to another subject")
    if deal.claimed:
        raise ValueError("daily deal is already claimed")
    if current >= deal.expires_at:
        raise ValueError("daily deal has expired")
    if deal.item_id != item.id or deal.item_sha256 != shop_item_digest(item):
        raise ValueError("daily deal item binding mismatch")
    expected_cost = _discount_cost(item.cost, deal.discount_percent)
    if dict(expected_cost) != dict(deal.discounted_cost):
        raise ValueError("daily deal discounted cost binding mismatch")
    return quote_shop_purchase(
        item,
        player_level=player_level,
        balances=balances,
        owned_item_ids=owned_item_ids,
        quantity=1,
        cost_override=deal.discounted_cost,
    )


def mark_daily_deal_claimed(deal: DailyDeal) -> DailyDeal:
    if not isinstance(deal, DailyDeal):
        raise TypeError("deal must be DailyDeal")
    if deal.claimed:
        raise ValueError("daily deal is already claimed")
    return replace(deal, claimed=True)


@dataclass(frozen=True, slots=True)
class VerifiedPurchaseEvidence:
    """Provider-verified purchase evidence supplied by an external trust boundary."""

    subject_id: str
    product_id: str
    transaction_id: str
    platform: str
    currency: str
    price_minor: int
    verified_at: datetime
    proof_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", _text(self.subject_id, "verified purchase subject_id"))
        object.__setattr__(self, "product_id", _token(self.product_id, "verified purchase product_id"))
        object.__setattr__(self, "transaction_id", _text(self.transaction_id, "verified purchase transaction_id"))
        object.__setattr__(self, "platform", _token(self.platform, "verified purchase platform"))
        currency = _text(self.currency, "verified purchase currency").upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("verified purchase currency must be a three-letter code")
        object.__setattr__(self, "currency", currency)
        object.__setattr__(self, "price_minor", _positive_int(self.price_minor, "verified purchase price_minor"))
        object.__setattr__(self, "verified_at", _aware(self.verified_at, "verified purchase verified_at"))
        object.__setattr__(
            self,
            "proof_sha256",
            _sha256(self.proof_sha256, "verified purchase proof_sha256"),
        )


@dataclass(frozen=True, slots=True)
class CurrencyPackSpec:
    id: str
    grant_currency: str
    amount: int
    price_minor: int
    payment_currency: str = "USD"

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _token(self.id, "currency pack id"))
        object.__setattr__(self, "grant_currency", _token(self.grant_currency, "currency pack grant_currency"))
        object.__setattr__(self, "amount", _positive_int(self.amount, "currency pack amount"))
        object.__setattr__(self, "price_minor", _positive_int(self.price_minor, "currency pack price_minor"))
        currency = _text(self.payment_currency, "currency pack payment_currency").upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency pack payment_currency must be a three-letter code")
        object.__setattr__(self, "payment_currency", currency)


@dataclass(frozen=True, slots=True)
class CurrencyPackPlan:
    product_id: str
    transaction_id: str
    increments: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_id", _token(self.product_id, "currency pack plan product_id"))
        object.__setattr__(self, "transaction_id", _text(self.transaction_id, "currency pack plan transaction_id"))
        object.__setattr__(
            self,
            "increments",
            _positive_count_map(self.increments, "currency pack plan increments"),
        )


def _bind_verified_purchase(
    evidence: VerifiedPurchaseEvidence,
    *,
    subject_id: str,
    product_id: str,
    price_minor: int,
    currency: str,
    consumed_transaction_ids: Iterable[str] = (),
) -> None:
    if not isinstance(evidence, VerifiedPurchaseEvidence):
        raise TypeError("evidence must be VerifiedPurchaseEvidence")
    subject = _text(subject_id, "purchase subject_id")
    product = _token(product_id, "purchase product_id")
    expected_price = _positive_int(price_minor, "purchase price_minor")
    expected_currency = _text(currency, "purchase currency").upper()
    consumed = frozenset(
        _text(value, "consumed transaction id") for value in consumed_transaction_ids
    )
    if evidence.subject_id != subject:
        raise PermissionError("verified purchase belongs to another subject")
    if evidence.product_id != product:
        raise ValueError("verified purchase product mismatch")
    if evidence.price_minor != expected_price or evidence.currency != expected_currency:
        raise ValueError("verified purchase price/currency mismatch")
    if evidence.transaction_id in consumed:
        raise ValueError("verified purchase transaction has already been consumed")


def plan_currency_pack_purchase(
    pack: CurrencyPackSpec,
    evidence: VerifiedPurchaseEvidence,
    *,
    subject_id: str,
    consumed_transaction_ids: Iterable[str] = (),
) -> CurrencyPackPlan:
    if not isinstance(pack, CurrencyPackSpec):
        raise TypeError("pack must be CurrencyPackSpec")
    _bind_verified_purchase(
        evidence,
        subject_id=subject_id,
        product_id=pack.id,
        price_minor=pack.price_minor,
        currency=pack.payment_currency,
        consumed_transaction_ids=consumed_transaction_ids,
    )
    return CurrencyPackPlan(
        product_id=pack.id,
        transaction_id=evidence.transaction_id,
        increments={pack.grant_currency: pack.amount},
    )


@dataclass(frozen=True, slots=True)
class BundleGrant:
    grant_type: str
    amount: int = 1
    item_id: str | None = None

    def __post_init__(self) -> None:
        grant_type = _token(self.grant_type, "bundle grant type")
        if grant_type not in _SUPPORTED_GRANT_TYPES:
            raise ValueError(f"unsupported bundle grant type: {grant_type}")
        amount = _positive_int(self.amount, "bundle grant amount")
        item_id = self.item_id
        if grant_type in {"item", "bait"}:
            item_id = _token(item_id, "bundle grant item_id")
        elif item_id is not None:
            raise ValueError("bundle grant item_id is only valid for item/bait grants")
        object.__setattr__(self, "grant_type", grant_type)
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "item_id", item_id)


@dataclass(frozen=True, slots=True)
class BundleSpec:
    id: str
    price_minor: int
    grants: tuple[BundleGrant, ...]
    one_time_only: bool = False
    cooldown_days: int | None = None
    payment_currency: str = "USD"

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _token(self.id, "bundle id"))
        object.__setattr__(self, "price_minor", _positive_int(self.price_minor, "bundle price_minor"))
        if isinstance(self.grants, (str, bytes)) or not isinstance(self.grants, tuple):
            raise TypeError("bundle grants must be a tuple")
        if not self.grants:
            raise ValueError("bundle grants must not be empty")
        for grant in self.grants:
            if not isinstance(grant, BundleGrant):
                raise TypeError("bundle grants must contain BundleGrant values")
        if not isinstance(self.one_time_only, bool):
            raise TypeError("bundle one_time_only must be a boolean")
        cooldown = self.cooldown_days
        if cooldown is not None:
            cooldown = _positive_int(cooldown, "bundle cooldown_days")
        if self.one_time_only and cooldown is not None:
            raise ValueError("one-time bundle cannot also define a cooldown")
        object.__setattr__(self, "cooldown_days", cooldown)
        currency = _text(self.payment_currency, "bundle payment_currency").upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("bundle payment_currency must be a three-letter code")
        object.__setattr__(self, "payment_currency", currency)


@dataclass(frozen=True, slots=True)
class BundlePurchaseHistory:
    purchased_product_ids: frozenset[str] = frozenset()
    last_purchase_at: Mapping[str, datetime] = field(default_factory=dict)
    consumed_transaction_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        purchased = frozenset(_text_tuple(self.purchased_product_ids, "purchased product ids"))
        if not isinstance(self.last_purchase_at, Mapping):
            raise TypeError("bundle last_purchase_at must be a mapping")
        times: dict[str, datetime] = {}
        for raw_key, raw_value in self.last_purchase_at.items():
            key = _token(raw_key, "bundle last_purchase_at key")
            times[key] = _aware(raw_value, f"bundle last_purchase_at[{key!r}]")
        consumed = frozenset(
            _text(value, "consumed transaction id") for value in self.consumed_transaction_ids
        )
        object.__setattr__(self, "purchased_product_ids", purchased)
        object.__setattr__(self, "last_purchase_at", MappingProxyType(times))
        object.__setattr__(self, "consumed_transaction_ids", consumed)


@dataclass(frozen=True, slots=True)
class BundleRewardPlan:
    product_id: str
    transaction_id: str
    currency_increments: Mapping[str, int]
    item_grants: tuple[str, ...]
    bait_increments: Mapping[str, int]
    energy_increment: int
    vip_days: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_id", _token(self.product_id, "bundle plan product_id"))
        object.__setattr__(self, "transaction_id", _text(self.transaction_id, "bundle plan transaction_id"))
        object.__setattr__(
            self,
            "currency_increments",
            _positive_count_map(self.currency_increments, "bundle plan currency_increments"),
        )
        object.__setattr__(self, "item_grants", _text_tuple(self.item_grants, "bundle plan item_grants"))
        object.__setattr__(
            self,
            "bait_increments",
            _positive_count_map(self.bait_increments, "bundle plan bait_increments"),
        )
        object.__setattr__(self, "energy_increment", _nonnegative_int(self.energy_increment, "bundle plan energy_increment"))
        object.__setattr__(self, "vip_days", _nonnegative_int(self.vip_days, "bundle plan vip_days"))


def plan_bundle_purchase(
    bundle: BundleSpec,
    evidence: VerifiedPurchaseEvidence,
    history: BundlePurchaseHistory,
    *,
    subject_id: str,
    now: datetime,
) -> BundleRewardPlan:
    """Validate external payment evidence and produce an atomic reward plan."""

    if not isinstance(bundle, BundleSpec):
        raise TypeError("bundle must be BundleSpec")
    if not isinstance(history, BundlePurchaseHistory):
        raise TypeError("history must be BundlePurchaseHistory")
    current = _aware(now, "bundle purchase now")
    _bind_verified_purchase(
        evidence,
        subject_id=subject_id,
        product_id=bundle.id,
        price_minor=bundle.price_minor,
        currency=bundle.payment_currency,
        consumed_transaction_ids=history.consumed_transaction_ids,
    )
    if evidence.verified_at > current + timedelta(minutes=5):
        raise ValueError("verified purchase timestamp is implausibly in the future")
    if bundle.one_time_only and bundle.id in history.purchased_product_ids:
        raise ValueError("one-time bundle has already been purchased")
    if bundle.cooldown_days is not None and bundle.id in history.last_purchase_at:
        next_allowed = history.last_purchase_at[bundle.id] + timedelta(days=bundle.cooldown_days)
        if current < next_allowed:
            raise PermissionError("bundle purchase cooldown is still active")

    currency: dict[str, int] = {}
    item_grants: list[str] = []
    bait: dict[str, int] = {}
    energy = 0
    vip_days = 0
    for grant in bundle.grants:
        if grant.grant_type in {"coins", "gems"}:
            currency[grant.grant_type] = currency.get(grant.grant_type, 0) + grant.amount
        elif grant.grant_type == "energy":
            energy += grant.amount
        elif grant.grant_type == "vip":
            vip_days += grant.amount
        elif grant.grant_type == "item":
            assert grant.item_id is not None
            if grant.amount != 1:
                raise ValueError("bundle non-consumable item grants must have amount=1")
            if grant.item_id in item_grants:
                raise ValueError(f"duplicate bundle item grant: {grant.item_id}")
            item_grants.append(grant.item_id)
        elif grant.grant_type == "bait":
            assert grant.item_id is not None
            bait[grant.item_id] = bait.get(grant.item_id, 0) + grant.amount
        else:
            raise ValueError(f"unsupported bundle grant type: {grant.grant_type}")

    return BundleRewardPlan(
        product_id=bundle.id,
        transaction_id=evidence.transaction_id,
        currency_increments=currency,
        item_grants=tuple(item_grants),
        bait_increments=bait,
        energy_increment=energy,
        vip_days=vip_days,
    )


def record_bundle_purchase(
    history: BundlePurchaseHistory,
    bundle: BundleSpec,
    plan: BundleRewardPlan,
    *,
    purchased_at: datetime,
) -> BundlePurchaseHistory:
    if not isinstance(history, BundlePurchaseHistory):
        raise TypeError("history must be BundlePurchaseHistory")
    if not isinstance(bundle, BundleSpec):
        raise TypeError("bundle must be BundleSpec")
    if not isinstance(plan, BundleRewardPlan):
        raise TypeError("plan must be BundleRewardPlan")
    if plan.product_id != bundle.id:
        raise ValueError("bundle plan product mismatch")
    purchased = _aware(purchased_at, "bundle purchased_at")
    if plan.transaction_id in history.consumed_transaction_ids:
        raise ValueError("bundle transaction has already been consumed")
    product_ids = set(history.purchased_product_ids)
    product_ids.add(bundle.id)
    last = dict(history.last_purchase_at)
    last[bundle.id] = purchased
    transactions = set(history.consumed_transaction_ids)
    transactions.add(plan.transaction_id)
    return BundlePurchaseHistory(
        purchased_product_ids=frozenset(product_ids),
        last_purchase_at=last,
        consumed_transaction_ids=frozenset(transactions),
    )
