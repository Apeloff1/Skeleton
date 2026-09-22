"""Pure breeding/genetics policy from exact shared Lorebuffa/Openworld lineage.

Both source repositories use ``backend/breeding_routes.py`` blob
``8f016084c60b44a4d3d09d16f6e5076722355212``. FastAPI, MongoDB, tacklebox
mutation, wallet mutation and source catalogs remain source-owned. This module
promotes only deterministic/explicitly-injected genetics, compatibility,
timing, valuation, progression and slot-upgrade policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import math
from typing import Any, Callable, Mapping, Protocol, Sequence


RARITY_MULTIPLIERS = {
    "common": 1.0,
    "uncommon": 1.5,
    "rare": 2.5,
    "epic": 4.0,
    "legendary": 10.0,
}
SIZE_MULTIPLIERS = {
    "tiny": 0.5,
    "small": 0.8,
    "medium": 1.0,
    "large": 1.5,
    "giant": 2.0,
}


class RandomSource(Protocol):
    def random(self) -> float: ...
    def choice(self, values: Sequence[str]) -> str: ...
    def uniform(self, lower: float, upper: float) -> float: ...


@dataclass(frozen=True, slots=True)
class FishSpeciesSpec:
    id: str
    base_value: int
    breed_time_hours: float
    compatible: tuple[str, ...] = ()
    legendary: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _token(self.id, "species id"))
        object.__setattr__(self, "base_value", _nonnegative_int(self.base_value, "species base value"))
        object.__setattr__(
            self,
            "breed_time_hours",
            _finite_number(self.breed_time_hours, "breed time hours", minimum=0),
        )
        compatible = tuple(_token(value, "compatible species") for value in self.compatible)
        if len(set(compatible)) != len(compatible):
            raise ValueError("compatible species must be unique")
        object.__setattr__(self, "compatible", compatible)
        if not isinstance(self.legendary, bool):
            raise TypeError("legendary must be a boolean")


@dataclass(frozen=True, slots=True)
class SpecialBreedSpec:
    id: str
    name: str
    parents: tuple[str, str]
    required_traits: Mapping[str, str] = field(default_factory=dict)
    rarity: str = "rare"
    base_value: int = 50

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _token(self.id, "special breed id"))
        object.__setattr__(self, "name", _text(self.name, "special breed name"))
        if len(self.parents) != 2:
            raise ValueError("special breed parents must contain exactly two species")
        object.__setattr__(
            self,
            "parents",
            tuple(_token(value, "special breed parent") for value in self.parents),
        )
        if not isinstance(self.required_traits, Mapping):
            raise TypeError("required traits must be a mapping")
        object.__setattr__(
            self,
            "required_traits",
            {
                _token(key, "required trait key"): _token(value, "required trait value")
                for key, value in self.required_traits.items()
            },
        )
        object.__setattr__(self, "rarity", _token(self.rarity, "special breed rarity"))
        object.__setattr__(
            self,
            "base_value",
            _nonnegative_int(self.base_value, "special breed value"),
        )


@dataclass(frozen=True, slots=True)
class BreedingParent:
    id: str
    species: str
    traits: Mapping[str, str]
    size: float = 50.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "parent fish id"))
        object.__setattr__(self, "species", _token(self.species, "parent species"))
        if not isinstance(self.traits, Mapping):
            raise TypeError("parent traits must be a mapping")
        object.__setattr__(
            self,
            "traits",
            {
                _token(key, "trait key"): _token(value, "trait value")
                for key, value in self.traits.items()
            },
        )
        object.__setattr__(self, "size", _finite_number(self.size, "parent size", minimum=0))


@dataclass(frozen=True, slots=True)
class BreedingJob:
    parent1: BreedingParent
    parent2: BreedingParent
    parent1_slot: int
    parent2_slot: int
    started_at: datetime
    complete_at: datetime
    status: str = "breeding"

    def __post_init__(self) -> None:
        _aware(self.started_at, "started_at")
        _aware(self.complete_at, "complete_at")
        if self.complete_at < self.started_at:
            raise ValueError("complete_at must not precede started_at")
        if self.parent1_slot == self.parent2_slot:
            raise ValueError("breeding parents must occupy distinct slots")
        if self.status not in {"breeding", "complete"}:
            raise ValueError("unsupported breeding job status")


@dataclass(frozen=True, slots=True)
class BreedingProgress:
    level: int = 1
    xp: int = 0
    total_bred: int = 0
    rare_discoveries: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", _positive_int(self.level, "breeding level"))
        object.__setattr__(self, "xp", _nonnegative_int(self.xp, "breeding xp"))
        object.__setattr__(self, "total_bred", _nonnegative_int(self.total_bred, "total bred"))
        if isinstance(self.rare_discoveries, (str, bytes)):
            raise TypeError("rare discoveries must be a collection")
        object.__setattr__(
            self,
            "rare_discoveries",
            frozenset(_token(v, "rare discovery") for v in self.rare_discoveries),
        )


@dataclass(frozen=True, slots=True)
class OffspringPlan:
    id: str
    species: str
    name: str
    traits: Mapping[str, str]
    size: float
    value: int
    parents: tuple[str, str]
    bred_at: datetime
    special_breed_id: str | None
    is_new_discovery: bool
    xp_reward: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "offspring id"))
        object.__setattr__(self, "species", _token(self.species, "offspring species"))
        object.__setattr__(self, "name", _text(self.name, "offspring name"))
        if not isinstance(self.traits, Mapping):
            raise TypeError("offspring traits must be a mapping")
        object.__setattr__(
            self,
            "traits",
            {
                _token(key, "offspring trait key"): _token(value, "offspring trait value")
                for key, value in self.traits.items()
            },
        )
        object.__setattr__(self, "size", _finite_number(self.size, "offspring size", minimum=0))
        object.__setattr__(self, "value", _nonnegative_int(self.value, "offspring value"))
        if len(self.parents) != 2:
            raise ValueError("offspring parents must contain exactly two species")
        object.__setattr__(
            self,
            "parents",
            tuple(_token(value, "offspring parent") for value in self.parents),
        )
        object.__setattr__(self, "bred_at", _aware(self.bred_at, "offspring bred_at"))
        if self.special_breed_id is not None:
            object.__setattr__(
                self,
                "special_breed_id",
                _token(self.special_breed_id, "special breed id"),
            )
        if not isinstance(self.is_new_discovery, bool):
            raise TypeError("is_new_discovery must be a boolean")
        object.__setattr__(self, "xp_reward", _nonnegative_int(self.xp_reward, "offspring xp reward"))


@dataclass(frozen=True, slots=True)
class SlotUpgradePlan:
    slot_type: str
    current_slots: int
    new_slot_count: int
    gem_cost: int
    max_slots: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "slot_type", _token(self.slot_type, "slot type"))
        object.__setattr__(self, "current_slots", _positive_int(self.current_slots, "current slots"))
        object.__setattr__(self, "new_slot_count", _positive_int(self.new_slot_count, "new slot count"))
        object.__setattr__(self, "gem_cost", _nonnegative_int(self.gem_cost, "gem cost"))
        object.__setattr__(self, "max_slots", _positive_int(self.max_slots, "max slots"))
        if self.new_slot_count != self.current_slots + 1:
            raise ValueError("slot upgrade must add exactly one slot")
        if self.new_slot_count > self.max_slots:
            raise ValueError("slot upgrade exceeds maximum")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _token(value: object, field_name: str) -> str:
    return _text(value, field_name).lower()


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


def _finite_number(value: object, field_name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    if minimum is not None and numeric < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    return numeric


def _aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def species_from_record(species_id: str, record: Mapping[str, Any]) -> FishSpeciesSpec:
    if not isinstance(record, Mapping):
        raise TypeError("species record must be a mapping")
    compatible_raw = record.get("compatible", ())
    if isinstance(compatible_raw, (str, bytes)) or not isinstance(compatible_raw, Sequence):
        raise TypeError("compatible species must be a sequence")
    compatible = tuple(_token(value, "compatible species") for value in compatible_raw)
    if len(set(compatible)) != len(compatible):
        raise ValueError("compatible species must be unique")
    legendary = record.get("legendary", False)
    if not isinstance(legendary, bool):
        raise TypeError("legendary must be a boolean")
    return FishSpeciesSpec(
        id=_token(species_id, "species id"),
        base_value=_nonnegative_int(record.get("base_value"), "species base value"),
        breed_time_hours=_finite_number(record.get("breed_time_hours"), "breed time hours", minimum=0),
        compatible=compatible,
        legendary=legendary,
    )


def special_breed_from_record(record: Mapping[str, Any]) -> SpecialBreedSpec:
    if not isinstance(record, Mapping):
        raise TypeError("special breed record must be a mapping")
    raw_parents = record.get("parents")
    if isinstance(raw_parents, (str, bytes)) or not isinstance(raw_parents, Sequence) or len(raw_parents) != 2:
        raise ValueError("special breed parents must contain exactly two species")
    raw_traits = record.get("required_traits", {})
    if not isinstance(raw_traits, Mapping):
        raise TypeError("required traits must be a mapping")
    return SpecialBreedSpec(
        id=_token(record.get("id"), "special breed id"),
        name=_text(record.get("name"), "special breed name"),
        parents=(
            _token(raw_parents[0], "special breed parent"),
            _token(raw_parents[1], "special breed parent"),
        ),
        required_traits={
            _token(key, "required trait key"): _token(value, "required trait value")
            for key, value in raw_traits.items()
        },
        rarity=_token(record.get("rarity", "rare"), "special breed rarity"),
        base_value=_nonnegative_int(record.get("value", 50), "special breed value"),
    )


def parent_from_record(record: Mapping[str, Any]) -> BreedingParent:
    if not isinstance(record, Mapping):
        raise TypeError("parent fish record must be a mapping")
    raw_traits = record.get("traits", {})
    if not isinstance(raw_traits, Mapping):
        raise TypeError("parent traits must be a mapping")
    traits = {
        _token(key, "trait key"): _token(value, "trait value")
        for key, value in raw_traits.items()
    }
    return BreedingParent(
        id=_text(record.get("id"), "parent fish id"),
        species=_token(record.get("species"), "parent species"),
        traits=traits,
        size=_finite_number(record.get("size", 50), "parent size", minimum=0),
    )


def compatible_species(first: FishSpeciesSpec, second: FishSpeciesSpec) -> bool:
    return (
        first.id == second.id
        or second.id in first.compatible
        or first.id in second.compatible
    )


def breed_time_hours(first: FishSpeciesSpec, second: FishSpeciesSpec) -> float:
    if not compatible_species(first, second):
        raise ValueError("fish species are not compatible for breeding")
    return max(first.breed_time_hours, second.breed_time_hours)


def start_breeding(
    parent1: BreedingParent,
    parent2: BreedingParent,
    *,
    parent1_slot: int,
    parent2_slot: int,
    species: Mapping[str, FishSpeciesSpec],
    now: datetime,
) -> BreedingJob:
    _nonnegative_int(parent1_slot, "parent1 slot")
    _nonnegative_int(parent2_slot, "parent2 slot")
    if parent1_slot == parent2_slot:
        raise ValueError("breeding parents must occupy distinct slots")
    now = _aware(now, "now")
    first = species.get(parent1.species)
    second = species.get(parent2.species)
    if first is None or second is None:
        raise KeyError("both parent species must have a species specification")
    hours = breed_time_hours(first, second)
    return BreedingJob(
        parent1=parent1,
        parent2=parent2,
        parent1_slot=parent1_slot,
        parent2_slot=parent2_slot,
        started_at=now,
        complete_at=now + timedelta(hours=hours),
    )


def refresh_breeding(job: BreedingJob, now: datetime) -> BreedingJob:
    now = _aware(now, "now")
    if job.status == "breeding" and now >= job.complete_at:
        return replace(job, status="complete")
    return job


def generate_traits(
    trait_domains: Mapping[str, Sequence[str]],
    parent1_traits: Mapping[str, str] | None,
    parent2_traits: Mapping[str, str] | None,
    *,
    rng: RandomSource,
    mutation_chance: float = 0.10,
) -> dict[str, str]:
    chance = _finite_number(mutation_chance, "mutation chance", minimum=0)
    if chance > 1:
        raise ValueError("mutation chance must not exceed 1")
    if parent1_traits is not None and not isinstance(parent1_traits, Mapping):
        raise TypeError("parent1 traits must be a mapping")
    if parent2_traits is not None and not isinstance(parent2_traits, Mapping):
        raise TypeError("parent2 traits must be a mapping")
    result: dict[str, str] = {}
    for raw_name, raw_values in trait_domains.items():
        name = _token(raw_name, "trait domain name")
        if isinstance(raw_values, (str, bytes)) or not isinstance(raw_values, Sequence) or not raw_values:
            raise ValueError(f"trait domain {name} must contain values")
        values = tuple(_token(value, f"trait {name} value") for value in raw_values)
        if len(set(values)) != len(values):
            raise ValueError(f"trait domain {name} values must be unique")
        first = _token(parent1_traits[name], name) if parent1_traits and name in parent1_traits else None
        second = _token(parent2_traits[name], name) if parent2_traits and name in parent2_traits else None
        draw = _finite_number(rng.random(), f"mutation draw {name}", minimum=0)
        if draw > 1:
            raise ValueError("random probability draws must not exceed 1")
        if draw < chance:
            result[name] = _token(rng.choice(values), f"mutated trait {name}")
        elif first is not None and second is not None:
            result[name] = _token(rng.choice((first, second)), f"inherited trait {name}")
        else:
            result[name] = _token(rng.choice(values), f"generated trait {name}")
    return result


def trait_value_multiplier(traits: Mapping[str, str]) -> float:
    rarity = _token(traits.get("rarity_gene", "common"), "rarity gene")
    size = _token(traits.get("size_gene", "medium"), "size gene")
    multiplier = RARITY_MULTIPLIERS.get(rarity, 1.0) * SIZE_MULTIPLIERS.get(size, 1.0)
    color = _token(traits.get("color", "none"), "color")
    pattern = _token(traits.get("pattern", "none"), "pattern")
    if color in {"rainbow", "gold"}:
        multiplier *= 1.5
    if pattern in {"iridescent", "rainbow"}:
        multiplier *= 1.3
    return multiplier


def calculate_fish_value(
    species: FishSpeciesSpec,
    traits: Mapping[str, str],
    *,
    base_value_override: int | None = None,
) -> int:
    base = species.base_value if base_value_override is None else _nonnegative_int(
        base_value_override, "base value override"
    )
    return int(base * trait_value_multiplier(traits))


def matching_special_breed(
    parent1_species: str,
    parent2_species: str,
    offspring_traits: Mapping[str, str],
    specials: Sequence[SpecialBreedSpec],
    *,
    rng: RandomSource,
    fallback_chance: float = 0.05,
) -> SpecialBreedSpec | None:
    fallback = _finite_number(fallback_chance, "special breed fallback chance", minimum=0)
    if fallback > 1:
        raise ValueError("special breed fallback chance must not exceed 1")
    parents = sorted((_token(parent1_species, "parent species"), _token(parent2_species, "parent species")))
    normalized_traits = {
        _token(key, "offspring trait key"): _token(value, "offspring trait value")
        for key, value in offspring_traits.items()
    }
    for special in specials:
        if parents != sorted(special.parents):
            continue
        exact = all(normalized_traits.get(key) == value for key, value in special.required_traits.items())
        if exact:
            return special
        draw = _finite_number(rng.random(), "special breed fallback draw", minimum=0)
        if draw > 1:
            raise ValueError("random probability draws must not exceed 1")
        if draw < fallback:
            return special
    return None


def breeding_xp_threshold(level: int) -> int:
    return _positive_int(level, "breeding level") * 150


def apply_breeding_reward(
    progress: BreedingProgress,
    *,
    special_breed: SpecialBreedSpec | None,
) -> BreedingProgress:
    reward = 60 if special_breed is not None else 10
    xp = progress.xp + reward
    level = progress.level
    while xp >= breeding_xp_threshold(level):
        xp -= breeding_xp_threshold(level)
        level += 1
    discoveries = set(progress.rare_discoveries)
    if special_breed is not None:
        discoveries.add(special_breed.id)
    return BreedingProgress(
        level=level,
        xp=xp,
        total_bred=progress.total_bred + 1,
        rare_discoveries=frozenset(discoveries),
    )


def offspring_plan(
    job: BreedingJob,
    *,
    trait_domains: Mapping[str, Sequence[str]],
    species: Mapping[str, FishSpeciesSpec],
    specials: Sequence[SpecialBreedSpec],
    known_discoveries: Sequence[str] = (),
    rng: RandomSource,
    id_factory: Callable[[], str],
    now: datetime,
) -> OffspringPlan:
    if job.status != "complete":
        raise ValueError("breeding job must be complete before offspring collection")
    now = _aware(now, "now")
    traits = generate_traits(
        trait_domains,
        job.parent1.traits,
        job.parent2.traits,
        rng=rng,
    )
    if job.parent1.species == job.parent2.species:
        offspring_species = job.parent1.species
    else:
        offspring_species = _token(
            rng.choice((job.parent1.species, job.parent2.species)),
            "offspring species",
        )
    special = matching_special_breed(
        job.parent1.species,
        job.parent2.species,
        traits,
        specials,
        rng=rng,
    )
    base_override: int | None = None
    if special is not None:
        offspring_species = special.id
        traits["rarity_gene"] = special.rarity
        base_override = special.base_value
    base_species = species.get(offspring_species)
    if base_species is None:
        if special is None:
            raise KeyError(f"missing offspring species specification: {offspring_species}")
        base_species = FishSpeciesSpec(
            id=special.id,
            base_value=special.base_value,
            breed_time_hours=0,
        )
    size_factor = _finite_number(rng.uniform(0.8, 1.2), "offspring size factor", minimum=0.8)
    if size_factor > 1.2:
        raise ValueError("offspring size factor must not exceed 1.2")
    size = ((job.parent1.size + job.parent2.size) / 2.0) * size_factor
    offspring_id = _text(id_factory(), "offspring id")
    known = {_token(value, "known discovery") for value in known_discoveries}
    return OffspringPlan(
        id=offspring_id,
        species=offspring_species,
        name=special.name if special is not None else offspring_species.replace("_", " ").title(),
        traits=dict(traits),
        size=size,
        value=calculate_fish_value(base_species, traits, base_value_override=base_override),
        parents=(job.parent1.species, job.parent2.species),
        bred_at=now,
        special_breed_id=special.id if special is not None else None,
        is_new_discovery=special is not None and special.id not in known,
        xp_reward=60 if special is not None else 10,
    )


def speed_up_cost(job: BreedingJob, now: datetime) -> int:
    if job.status != "breeding":
        raise ValueError("only active breeding jobs can be sped up")
    now = _aware(now, "now")
    remaining_hours = max(0.0, (job.complete_at - now).total_seconds() / 3600.0)
    return max(5, int(remaining_hours * 5))


def slot_upgrade_plan(slot_type: str, current_slots: int) -> SlotUpgradePlan:
    kind = _token(slot_type, "slot type")
    current = _positive_int(current_slots, "current slots")
    if kind == "breeding":
        maximum = 4
        cost = 200 * current
    elif kind == "parent":
        maximum = 8
        cost = 100 * current
    else:
        raise ValueError("slot type must be 'breeding' or 'parent'")
    if current >= maximum:
        raise ValueError("maximum slots reached")
    return SlotUpgradePlan(
        slot_type=kind,
        current_slots=current,
        new_slot_count=current + 1,
        gem_cost=cost,
        max_slots=maximum,
    )
