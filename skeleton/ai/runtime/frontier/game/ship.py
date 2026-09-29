"""Pure crew/store policy adapted from Lorebuffa and Openworld ship systems.

The two source files are divergent blobs (Lorebuffa ``ef37a57...`` and
Openworld ``9ddbd1d...``) but share the portable rules promoted here. Large
catalogs, FastAPI routes, MongoDB access, wallet mutation and inventory writes
remain in the source applications.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class CrewRoleSpec:
    role: str
    title: str
    max_per_ship: int
    salary: int
    name_pool: tuple[str, ...] = ()
    abilities: tuple[str, ...] = ()
    skill_bonuses: Mapping[str, int] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _strings(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be a sequence")
    return tuple(text for item in value if (text := str(item).strip()))


def crew_role_from_record(role: str, record: Mapping[str, Any]) -> CrewRoleSpec:
    """Normalize one source crew-role catalog record into portable policy."""

    role = role.strip().lower()
    if not role:
        raise ValueError("crew role must not be empty")
    title = str(record.get("title") or role.replace("_", " ").title()).strip()
    if not title:
        raise ValueError("crew role title must not be empty")

    try:
        max_per_ship = int(record.get("max_per_ship", 1))
        salary = int(record.get("salary", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("crew max_per_ship and salary must be integers") from exc
    if max_per_ship < 1:
        raise ValueError("crew max_per_ship must be positive")
    if salary < 0:
        raise ValueError("crew salary must not be negative")

    raw_bonuses = record.get("skill_bonuses") or {}
    if not isinstance(raw_bonuses, Mapping):
        raise TypeError("skill_bonuses must be a mapping")
    bonuses: dict[str, int] = {}
    for key, value in raw_bonuses.items():
        bonus = str(key).strip()
        if not bonus:
            raise ValueError("skill bonus names must not be empty")
        try:
            bonuses[bonus] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"skill bonus {bonus!r} must be an integer") from exc

    consumed = {
        "role",
        "title",
        "max_per_ship",
        "salary",
        "name_pool",
        "abilities",
        "skill_bonuses",
    }
    metadata = {key: value for key, value in record.items() if key not in consumed}
    return CrewRoleSpec(
        role=role,
        title=title,
        max_per_ship=max_per_ship,
        salary=salary,
        name_pool=_strings(record.get("name_pool"), field_name="name_pool"),
        abilities=tuple(
            ability.lower()
            for ability in _strings(record.get("abilities"), field_name="abilities")
        ),
        skill_bonuses=bonuses,
        metadata=metadata,
    )


def hiring_cost(role: CrewRoleSpec, *, salary_multiplier: int = 10) -> int:
    """Return the source hiring policy: salary multiplied by ten by default."""

    if salary_multiplier < 0:
        raise ValueError("salary_multiplier must not be negative")
    return role.salary * salary_multiplier


def can_hire(existing_role_count: int, role: CrewRoleSpec) -> bool:
    if existing_role_count < 0:
        raise ValueError("existing_role_count must not be negative")
    return existing_role_count < role.max_per_ship


def choose_crew_name(role: CrewRoleSpec, *, rng: random.Random) -> str:
    if not role.name_pool:
        raise ValueError(f"crew role {role.role!r} has no name pool")
    return rng.choice(role.name_pool)


def aggregate_crew(
    crew: Sequence[Mapping[str, Any]],
    roles: Mapping[str, CrewRoleSpec],
) -> dict[str, Any]:
    """Aggregate source-style daily salary and skill bonuses for a crew."""

    total_bonuses: dict[str, int] = {}
    total_salary = 0
    role_counts: dict[str, int] = {}
    for member in crew:
        role_name = str(member.get("role") or "").strip().lower()
        if not role_name:
            raise ValueError("crew member requires a role")
        role = roles.get(role_name)
        if role is None:
            raise KeyError(f"unknown crew role: {role_name}")

        role_counts[role_name] = role_counts.get(role_name, 0) + 1
        if role_counts[role_name] > role.max_per_ship:
            raise ValueError(f"crew role limit exceeded: {role_name}")

        raw_salary = member.get("salary", role.salary)
        try:
            member_salary = int(raw_salary)
        except (TypeError, ValueError) as exc:
            raise ValueError("crew member salary must be an integer") from exc
        if member_salary < 0:
            raise ValueError("crew member salary must not be negative")
        total_salary += member_salary

        for bonus, value in role.skill_bonuses.items():
            total_bonuses[bonus] = total_bonuses.get(bonus, 0) + value

    return {
        "total_crew": len(crew),
        "total_bonuses": total_bonuses,
        "daily_salary": total_salary,
        "role_counts": role_counts,
    }


def generate_crew_dialogue(
    crew: Mapping[str, Any],
    role: CrewRoleSpec,
) -> dict[str, str]:
    """Preserve the source morale bands and role-story policy without HTTP."""

    name = str(crew.get("name") or "").strip()
    if not name:
        raise ValueError("crew member requires a name")
    try:
        morale = int(crew.get("morale", 100))
    except (TypeError, ValueError) as exc:
        raise ValueError("crew morale must be an integer") from exc

    if morale >= 80:
        status = "Feeling great, Captain! Ready for anything the sea throws at us."
        advice = "The crew's spirits are high. Good time for a challenging voyage!"
    elif morale >= 50:
        status = "Getting by, Captain. Could use some shore leave soon."
        advice = "Maybe stop at a port? The crew could use some relaxation."
    else:
        status = "*sighs* It's been rough, Captain. The crew is wearing thin."
        advice = "We need rest, Captain. Pushing further could be dangerous."

    stories = {
        "first_mate": "Let me tell you about the time I served under Captain Blackwood...",
        "cook": "You know what the secret to good ship's biscuit is? Anger. Lots of anger.",
        "navigator": "See that constellation? It saved my life once in the Storm Straits...",
        "lookout": "I once spotted a whale so big it blocked out the horizon...",
        "surgeon": "I've stitched up wounds that would make lesser men faint...",
        "musician": "*strums instrument* Want to hear a shanty about the Leviathan?",
        "carpenter": "This ship's got character. Every plank tells a story.",
        "gunner": "BOOM! Haha, sorry Captain, I just love the sound of cannons.",
    }
    return {
        "greeting": f"*{name} nods* Aye, Captain?",
        "status": status,
        "advice": advice,
        "story": stories.get(
            role.role,
            "I've seen some things on these seas, Captain...",
        ),
    }


@dataclass(frozen=True, slots=True)
class PurchaseQuote:
    item_id: str
    quantity: int
    unit_price: int
    markup: float
    total_price: int


def quote_purchase(
    item: Mapping[str, Any],
    quantity: int,
    *,
    markup: float = 1.0,
) -> PurchaseQuote:
    """Quote a source-style store purchase without mutating wallet or inventory."""

    if quantity < 1:
        raise ValueError("purchase quantity must be positive")
    if not math.isfinite(markup) or markup < 0:
        raise ValueError("markup must be finite and non-negative")

    item_id = str(item.get("id") or "").strip()
    if not item_id:
        raise ValueError("store item requires an id")
    try:
        unit_price = int(item["price"])
        stock = int(item["quantity"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("store item requires integer price and quantity") from exc
    if unit_price < 0 or stock < 0:
        raise ValueError("store item price and quantity must not be negative")
    if stock < quantity:
        raise ValueError("not enough stock")

    return PurchaseQuote(
        item_id=item_id,
        quantity=quantity,
        unit_price=unit_price,
        markup=markup,
        total_price=int(unit_price * quantity * markup),
    )


def can_afford(gold: int, quote: PurchaseQuote) -> bool:
    if gold < 0:
        raise ValueError("gold must not be negative")
    return gold >= quote.total_price


def stores_for_location(
    location_id: str,
    stores: Mapping[str, Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    """Select common and conditional stores using the source location policy."""

    normalized = location_id.strip().lower()
    if not normalized:
        raise ValueError("location_id must not be empty")

    selected_ids = ["general_store", "bait_shop", "tavern", "fish_market"]
    if "port" in normalized or "city" in normalized:
        selected_ids.append("shipyard")
    if "pirate" in normalized or "haven" in normalized:
        selected_ids.append("black_market")

    selected: list[Mapping[str, Any]] = []
    for store_id in selected_ids:
        store = stores.get(store_id)
        if store is not None:
            selected.append(dict(store))
    return tuple(selected)
