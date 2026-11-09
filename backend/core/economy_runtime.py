"""Transactional economy and inventory primitives for generated playables.

Promotes useful shop/inventory semantics from Newmove2 into a storage-neutral
ledger. Currency and item mutations are validated and applied atomically so a
failed purchase cannot partially debit or credit state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


class EconomyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CatalogItem:
    id: str
    price: dict[str, int]
    quantity: int = 1
    min_level: int = 1
    grants: tuple[str, ...] = ()
    stackable: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise EconomyError("catalog item id cannot be blank")
        if self.quantity <= 0 or self.min_level <= 0:
            raise EconomyError("quantity and min_level must be positive")
        if not self.price or any(not key.strip() or value < 0 for key, value in self.price.items()):
            raise EconomyError("catalog price must contain non-negative currencies")


@dataclass(slots=True)
class Wallet:
    balances: dict[str, int] = field(default_factory=dict)

    def credit(self, currency: str, amount: int) -> None:
        if not currency.strip() or amount < 0:
            raise EconomyError("invalid credit")
        self.balances[currency] = self.balances.get(currency, 0) + amount

    def debit(self, currency: str, amount: int) -> None:
        if amount < 0:
            raise EconomyError("invalid debit")
        if self.balances.get(currency, 0) < amount:
            raise EconomyError(f"insufficient {currency}")
        self.balances[currency] -= amount


@dataclass(slots=True)
class Inventory:
    items: dict[str, int] = field(default_factory=dict)
    unlocks: set[str] = field(default_factory=set)
    capacity: int | None = None

    @property
    def used_slots(self) -> int:
        return sum(self.items.values())

    def can_add(self, quantity: int) -> bool:
        return self.capacity is None or self.used_slots + quantity <= self.capacity


@dataclass(frozen=True, slots=True)
class PurchaseReceipt:
    item_id: str
    quantity: int
    spent: dict[str, int]
    granted: tuple[str, ...]


class EconomyRuntime:
    def __init__(self, catalog: Iterable[CatalogItem]) -> None:
        items = tuple(catalog)
        self.catalog = {item.id: item for item in items}
        if not self.catalog:
            raise EconomyError("catalog cannot be empty")
        if len(self.catalog) != len(items):
            raise EconomyError("duplicate catalog item id")

    def purchase(
        self,
        *,
        item_id: str,
        quantity: int,
        player_level: int,
        wallet: Wallet,
        inventory: Inventory,
        price_multiplier: float = 1.0,
    ) -> PurchaseReceipt:
        if quantity <= 0:
            raise EconomyError("purchase quantity must be positive")
        if price_multiplier < 0:
            raise EconomyError("price multiplier cannot be negative")
        try:
            item = self.catalog[item_id]
        except KeyError as exc:
            raise EconomyError(f"unknown catalog item: {item_id}") from exc
        if player_level < item.min_level:
            raise EconomyError("item level gate not met")
        total_units = item.quantity * quantity
        if not item.stackable and inventory.items.get(item.id, 0) > 0:
            raise EconomyError("non-stackable item already owned")
        if not inventory.can_add(total_units):
            raise EconomyError("inventory capacity exceeded")

        spent = {
            currency: int(round(unit_cost * quantity * price_multiplier))
            for currency, unit_cost in item.price.items()
        }
        for currency, amount in spent.items():
            if wallet.balances.get(currency, 0) < amount:
                raise EconomyError(f"insufficient {currency}")

        # Commit only after every invariant has been validated.
        for currency, amount in spent.items():
            wallet.debit(currency, amount)
        inventory.items[item.id] = inventory.items.get(item.id, 0) + total_units
        inventory.unlocks.update(item.grants)
        return PurchaseReceipt(item.id, total_units, spent, item.grants)

    @staticmethod
    def sell(
        *,
        item_id: str,
        quantity: int,
        unit_value: dict[str, int],
        wallet: Wallet,
        inventory: Inventory,
    ) -> dict[str, int]:
        if quantity <= 0 or inventory.items.get(item_id, 0) < quantity:
            raise EconomyError("invalid sale quantity")
        if any(value < 0 for value in unit_value.values()):
            raise EconomyError("sale value cannot be negative")
        payout = {currency: value * quantity for currency, value in unit_value.items()}
        inventory.items[item_id] -= quantity
        if inventory.items[item_id] == 0:
            del inventory.items[item_id]
        for currency, amount in payout.items():
            wallet.credit(currency, amount)
        return payout

    @staticmethod
    def snapshot(wallet: Wallet, inventory: Inventory) -> dict[str, object]:
        return {
            "balances": dict(wallet.balances),
            "items": dict(inventory.items),
            "unlocks": sorted(inventory.unlocks),
            "capacity": inventory.capacity,
            "used_slots": inventory.used_slots,
        }
