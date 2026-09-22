"""Pure equipment/loadout policy promoted from shared Lorebuffa/Openworld lineage.

Both source repositories carry the identical ``backend/equipment_routes.py`` blob
``037724170943e13e237336f0df4631e2a81dd9d3``. Large equipment catalogs,
FastAPI/MongoDB handlers, wallets and persistence remain source-owned.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

_ALLOWED_CATEGORIES = frozenset({"rod", "line", "bobber"})


def _text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    if normalized != value:
        raise ValueError(f"{field} must be normalized")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer")
    if value < 0:
        raise ValueError(f"{field} must not be negative")
    return value


def _positive_int(value: object, field: str) -> int:
    value = _nonnegative_int(value, field)
    if value < 1:
        raise ValueError(f"{field} must be positive")
    return value


def _finite_number(value: object, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    if positive and result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _numeric_map(
    values: Mapping[str, Any],
    field: str,
    *,
    positive: bool = False,
) -> dict[str, float]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field} must be a mapping")
    result: dict[str, float] = {}
    for raw_key, raw_value in values.items():
        key = _text(raw_key, f"{field} key")
        if key in result:
            raise ValueError(f"duplicate {field} key: {key}")
        result[key] = _finite_number(
            raw_value,
            f"{field} {key}",
            positive=positive,
        )
    return result


def _cost_map(values: Mapping[str, Any]) -> dict[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError("equipment cost must be a mapping")
    result: dict[str, int] = {}
    for raw_currency, raw_amount in values.items():
        currency = _text(raw_currency, "equipment cost currency")
        if currency in result:
            raise ValueError(f"duplicate equipment cost currency: {currency}")
        result[currency] = _nonnegative_int(
            raw_amount,
            f"equipment cost {currency}",
        )
    return result


@dataclass(frozen=True, slots=True)
class EquipmentSpec:
    id: str
    name: str
    category: str
    biotope: str
    stats: Mapping[str, float] = field(default_factory=dict)
    bonuses: Mapping[str, float] = field(default_factory=dict)
    cost: Mapping[str, int] = field(default_factory=dict)
    unlock_level: int = 1
    rarity: str = "common"
    description: str = ""
    icon: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "equipment id"))
        object.__setattr__(self, "name", _text(self.name, "equipment name"))
        category = _text(self.category, "equipment category").lower()
        if category not in _ALLOWED_CATEGORIES:
            raise ValueError(f"unsupported equipment category: {category}")
        object.__setattr__(self, "category", category)
        object.__setattr__(
            self,
            "biotope",
            _text(self.biotope, "equipment biotope").lower(),
        )
        object.__setattr__(self, "stats", _numeric_map(self.stats, "equipment stats"))
        object.__setattr__(
            self,
            "bonuses",
            _numeric_map(self.bonuses, "equipment bonuses", positive=True),
        )
        object.__setattr__(self, "cost", _cost_map(self.cost))
        object.__setattr__(
            self,
            "unlock_level",
            _positive_int(self.unlock_level, "equipment unlock_level"),
        )
        object.__setattr__(
            self,
            "rarity",
            _text(self.rarity, "equipment rarity").lower(),
        )
        if not isinstance(self.metadata, Mapping):
            raise TypeError("equipment metadata must be a mapping")
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class EquipmentLoadout:
    owned_rods: frozenset[str] = frozenset()
    owned_lines: frozenset[str] = frozenset()
    owned_bobbers: frozenset[str] = frozenset()
    equipped_rod: str | None = None
    equipped_line: str | None = None
    equipped_bobber: str | None = None

    def __post_init__(self) -> None:
        for attr in ("owned_rods", "owned_lines", "owned_bobbers"):
            normalized = frozenset(
                _text(item, f"{attr} id") for item in getattr(self, attr)
            )
            object.__setattr__(self, attr, normalized)
        for attr, owned in (
            ("equipped_rod", self.owned_rods),
            ("equipped_line", self.owned_lines),
            ("equipped_bobber", self.owned_bobbers),
        ):
            value = getattr(self, attr)
            if value is None:
                continue
            normalized = _text(value, f"{attr} id")
            if normalized not in owned:
                raise ValueError(f"{attr} must reference owned equipment")
            object.__setattr__(self, attr, normalized)

    def owned_for(self, category: str) -> frozenset[str]:
        category = _text(category, "equipment category").lower()
        if category == "rod":
            return self.owned_rods
        if category == "line":
            return self.owned_lines
        if category == "bobber":
            return self.owned_bobbers
        raise ValueError(f"unsupported equipment category: {category}")


@dataclass(frozen=True, slots=True)
class EquipmentPurchaseQuote:
    equipment_id: str
    category: str
    cost: Mapping[str, int]
    missing_funds: Mapping[str, int]
    level_eligible: bool
    already_owned: bool

    @property
    def affordable(self) -> bool:
        return not self.missing_funds

    @property
    def can_purchase(self) -> bool:
        return self.level_eligible and not self.already_owned and self.affordable


@dataclass(frozen=True, slots=True)
class EquipmentBonuses:
    catch_rate: float = 1.0
    rare_chance: float = 1.0
    cast_distance: float = 1.0
    sensitivity: float = 1.0
    fighting_power: float = 1.0


def equipment_from_record(record: Mapping[str, Any]) -> EquipmentSpec:
    if not isinstance(record, Mapping):
        raise TypeError("equipment record must be a mapping")
    consumed = {
        "id",
        "name",
        "category",
        "biotope",
        "description",
        "stats",
        "bonuses",
        "cost",
        "unlock_level",
        "icon",
        "rarity",
    }
    return EquipmentSpec(
        id=_text(record.get("id"), "equipment id"),
        name=_text(record.get("name"), "equipment name"),
        category=_text(record.get("category"), "equipment category"),
        biotope=_text(record.get("biotope"), "equipment biotope"),
        description=str(record.get("description") or "").strip(),
        stats=dict(record.get("stats") or {}),
        bonuses=dict(record.get("bonuses") or {}),
        cost=dict(record.get("cost") or {}),
        unlock_level=_positive_int(
            record.get("unlock_level", 1),
            "equipment unlock_level",
        ),
        icon=str(record.get("icon") or "").strip(),
        rarity=_text(record.get("rarity", "common"), "equipment rarity"),
        metadata={key: value for key, value in record.items() if key not in consumed},
    )


def equipment_matches_biotope(item: EquipmentSpec, biotope: str) -> bool:
    target = _text(biotope, "biotope").lower()
    return item.biotope in {"universal", target}


def quote_equipment_purchase(
    item: EquipmentSpec,
    loadout: EquipmentLoadout,
    balances: Mapping[str, int],
    *,
    user_level: int,
) -> EquipmentPurchaseQuote:
    level = _positive_int(user_level, "equipment user_level")
    funds = _cost_map(balances)
    missing = {
        currency: amount - funds.get(currency, 0)
        for currency, amount in item.cost.items()
        if funds.get(currency, 0) < amount
    }
    return EquipmentPurchaseQuote(
        equipment_id=item.id,
        category=item.category,
        cost=dict(item.cost),
        missing_funds=missing,
        level_eligible=level >= item.unlock_level,
        already_owned=item.id in loadout.owned_for(item.category),
    )


def apply_equipment_purchase(
    loadout: EquipmentLoadout,
    item: EquipmentSpec,
) -> EquipmentLoadout:
    if item.id in loadout.owned_for(item.category):
        raise ValueError("equipment already owned")
    if item.category == "rod":
        return replace(loadout, owned_rods=loadout.owned_rods | {item.id})
    if item.category == "line":
        return replace(loadout, owned_lines=loadout.owned_lines | {item.id})
    return replace(loadout, owned_bobbers=loadout.owned_bobbers | {item.id})


def equip_item(loadout: EquipmentLoadout, item: EquipmentSpec) -> EquipmentLoadout:
    if item.id not in loadout.owned_for(item.category):
        raise ValueError("equipment item is not owned")
    if item.category == "rod":
        return replace(loadout, equipped_rod=item.id)
    if item.category == "line":
        return replace(loadout, equipped_line=item.id)
    return replace(loadout, equipped_bobber=item.id)


def _multiply(current: float, value: float) -> float:
    result = current * value
    if not math.isfinite(result):
        raise ValueError("equipment bonus aggregation overflowed")
    return result


def calculate_equipment_bonuses(
    rod: EquipmentSpec,
    line: EquipmentSpec,
    bobber: EquipmentSpec,
    *,
    biotope: str,
) -> EquipmentBonuses:
    if rod.category != "rod" or line.category != "line" or bobber.category != "bobber":
        raise ValueError("equipment bonus calculation requires rod, line and bobber")
    target = _text(biotope, "biotope").lower()
    values = {
        "catch_rate": 1.0,
        "rare_chance": 1.0,
        "cast_distance": 1.0,
        "sensitivity": 1.0,
        "fighting_power": 1.0,
    }

    for key, value in rod.bonuses.items():
        key_lower = key.lower()
        if target in key_lower or "bonus" in key_lower:
            values["catch_rate"] = _multiply(values["catch_rate"], value)
        if "rare" in key_lower or "legendary" in key_lower:
            values["rare_chance"] = _multiply(values["rare_chance"], value)
        if "distance" in key_lower:
            values["cast_distance"] = _multiply(values["cast_distance"], value)
        if "fighting" in key_lower or "power" in key_lower:
            values["fighting_power"] = _multiply(values["fighting_power"], value)

    for key, value in line.bonuses.items():
        key_lower = key.lower()
        if "stealth" in key_lower:
            values["catch_rate"] = _multiply(values["catch_rate"], value)
        if "sensitivity" in key_lower:
            values["sensitivity"] = _multiply(values["sensitivity"], value)

    for key, value in bobber.bonuses.items():
        key_lower = key.lower()
        if "detection" in key_lower:
            values["sensitivity"] = _multiply(values["sensitivity"], value)
        if "bonus" in key_lower:
            values["catch_rate"] = _multiply(values["catch_rate"], value)

    return EquipmentBonuses(**values)


def recommended_equipment(
    items: Sequence[EquipmentSpec],
    *,
    biotope: str,
    include_universal: bool = False,
) -> tuple[EquipmentSpec, ...]:
    target = _text(biotope, "biotope").lower()
    if not isinstance(include_universal, bool):
        raise TypeError("include_universal must be a boolean")
    selected: list[EquipmentSpec] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, EquipmentSpec):
            raise TypeError("recommended equipment inputs must be EquipmentSpec values")
        if item.id in seen:
            raise ValueError(f"duplicate equipment id: {item.id}")
        seen.add(item.id)
        if item.biotope == target or (
            include_universal and item.biotope == "universal"
        ):
            selected.append(item)
    return tuple(selected)
