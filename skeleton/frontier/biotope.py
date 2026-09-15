"""Pure biotope/stage/mastery policy from exact shared Lorebuffa/Openworld lineage.

Both source repositories carry the identical ``backend/biotope_routes.py`` blob
``b79a167a3b568477e7db1fa95d64fc3949171a7e``. Source biotope/stage catalogs,
FastAPI/Pydantic, MongoDB/Motor and player persistence remain source-owned.

This module promotes only portable policy: record normalization, unlock/access
requirements, active-stage selection, mastery progression and deterministic
bonus scaling. Declared boat requirements are enforced here even though the
source route omitted that check, and large XP awards may advance more than one
mastery level without an unbounded loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import isfinite, isqrt
from typing import Any, Mapping, Sequence


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if normalized != value:
        raise ValueError(f"{field_name} must be normalized")
    return value


def _token(value: object, field_name: str) -> str:
    return _text(value, field_name).lower()


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _finite_nonnegative(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    if numeric < 0:
        raise ValueError(f"{field_name} must not be negative")
    return numeric


def _tokens(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in value:
        token = _token(raw, field_name)
        if token in seen:
            raise ValueError(f"duplicate {field_name}: {token}")
        seen.add(token)
        normalized.append(token)
    return tuple(normalized)


def _multipliers(value: object, field_name: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, float] = {}
    for raw_key, raw_value in value.items():
        key = _token(raw_key, f"{field_name} key")
        if key in normalized:
            raise ValueError(f"duplicate {field_name} key: {key}")
        normalized[key] = _finite_nonnegative(raw_value, f"{field_name} {key}")
    return normalized


@dataclass(frozen=True, slots=True)
class BiotopeSpec:
    id: str
    name: str
    salinity: str
    environments: tuple[str, ...]
    best_times: tuple[str, ...]
    weather_effects: Mapping[str, float]
    unlock_level: int
    required_boat: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _token(self.id, "biotope id"))
        object.__setattr__(self, "name", _text(self.name, "biotope name"))
        object.__setattr__(self, "salinity", _token(self.salinity, "biotope salinity"))
        object.__setattr__(
            self, "environments", _tokens(self.environments, "biotope environment")
        )
        object.__setattr__(self, "best_times", _tokens(self.best_times, "biotope best time"))
        object.__setattr__(
            self,
            "weather_effects",
            _multipliers(self.weather_effects, "biotope weather effect"),
        )
        object.__setattr__(
            self, "unlock_level", _positive_int(self.unlock_level, "biotope unlock level")
        )
        if not isinstance(self.required_boat, bool):
            raise TypeError("biotope required_boat must be boolean")


@dataclass(frozen=True, slots=True)
class BiotopeStageSpec:
    id: str
    name: str
    biotope_id: str
    stage_number: int
    unlock_level: int
    difficulty: int
    fish_pool: tuple[str, ...] = ()
    rare_pool: tuple[str, ...] = ()
    legendary_pool: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _token(self.id, "biotope stage id"))
        object.__setattr__(self, "name", _text(self.name, "biotope stage name"))
        object.__setattr__(
            self, "biotope_id", _token(self.biotope_id, "biotope stage biotope id")
        )
        object.__setattr__(
            self, "stage_number", _positive_int(self.stage_number, "biotope stage number")
        )
        object.__setattr__(
            self, "unlock_level", _positive_int(self.unlock_level, "biotope stage unlock level")
        )
        object.__setattr__(
            self, "difficulty", _positive_int(self.difficulty, "biotope stage difficulty")
        )
        object.__setattr__(self, "fish_pool", _tokens(self.fish_pool, "stage fish"))
        object.__setattr__(self, "rare_pool", _tokens(self.rare_pool, "stage rare fish"))
        object.__setattr__(
            self, "legendary_pool", _tokens(self.legendary_pool, "stage legendary fish")
        )
        all_fish = (*self.fish_pool, *self.rare_pool, *self.legendary_pool)
        if len(all_fish) != len(set(all_fish)):
            raise ValueError("fish identities must not overlap between stage rarity pools")


@dataclass(frozen=True, slots=True)
class BiotopeMastery:
    level: int = 1
    xp: int = 0
    catches: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", _positive_int(self.level, "biotope mastery level"))
        object.__setattr__(self, "xp", _nonnegative_int(self.xp, "biotope mastery xp"))
        object.__setattr__(
            self, "catches", _nonnegative_int(self.catches, "biotope mastery catches")
        )
        if self.xp >= mastery_xp_threshold(self.level):
            raise ValueError("biotope mastery xp must be below the current level threshold")


@dataclass(frozen=True, slots=True)
class BiotopeProgress:
    unlocked_biotopes: frozenset[str]
    unlocked_stages: frozenset[str]
    current_biotope: str
    current_stage: str
    mastery: Mapping[str, BiotopeMastery] = field(default_factory=dict)
    favorite_biotope: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.unlocked_biotopes, (str, bytes)):
            raise TypeError("unlocked_biotopes must be a collection")
        if isinstance(self.unlocked_stages, (str, bytes)):
            raise TypeError("unlocked_stages must be a collection")
        biotopes = frozenset(
            _token(value, "unlocked biotope") for value in self.unlocked_biotopes
        )
        stages = frozenset(_token(value, "unlocked stage") for value in self.unlocked_stages)
        if not biotopes:
            raise ValueError("at least one biotope must be unlocked")
        if not stages:
            raise ValueError("at least one stage must be unlocked")
        current_biotope = _token(self.current_biotope, "current biotope")
        current_stage = _token(self.current_stage, "current stage")
        if current_biotope not in biotopes:
            raise ValueError("current biotope must be unlocked")
        if current_stage not in stages:
            raise ValueError("current stage must be unlocked")
        if not isinstance(self.mastery, Mapping):
            raise TypeError("biotope mastery must be a mapping")
        mastery: dict[str, BiotopeMastery] = {}
        for raw_id, raw_state in self.mastery.items():
            biotope_id = _token(raw_id, "mastery biotope id")
            if biotope_id in mastery:
                raise ValueError(f"duplicate mastery biotope id: {biotope_id}")
            if not isinstance(raw_state, BiotopeMastery):
                raise TypeError("mastery values must be BiotopeMastery")
            mastery[biotope_id] = raw_state
        for biotope_id in biotopes:
            mastery.setdefault(biotope_id, BiotopeMastery())
        favorite = self.favorite_biotope
        if favorite is not None:
            favorite = _token(favorite, "favorite biotope")
            if favorite not in biotopes:
                raise ValueError("favorite biotope must be unlocked")
        object.__setattr__(self, "unlocked_biotopes", biotopes)
        object.__setattr__(self, "unlocked_stages", stages)
        object.__setattr__(self, "current_biotope", current_biotope)
        object.__setattr__(self, "current_stage", current_stage)
        object.__setattr__(self, "mastery", mastery)
        object.__setattr__(self, "favorite_biotope", favorite)


@dataclass(frozen=True, slots=True)
class BiotopeBonuses:
    catch_rate: float
    rare_chance: float
    xp_multiplier: float
    coin_multiplier: float

    def __post_init__(self) -> None:
        for field_name in ("catch_rate", "rare_chance", "xp_multiplier", "coin_multiplier"):
            object.__setattr__(
                self,
                field_name,
                _finite_nonnegative(getattr(self, field_name), f"biotope {field_name}"),
            )

    def as_external_bonuses(self) -> Mapping[str, float]:
        return {
            "catch_rate": self.catch_rate,
            "rare_chance": self.rare_chance,
            "xp_multiplier": self.xp_multiplier,
            "coin_multiplier": self.coin_multiplier,
        }


@dataclass(frozen=True, slots=True)
class BiotopeUnlockPlan:
    progress: BiotopeProgress
    biotope_id: str
    auto_unlocked_stage_id: str | None = None


@dataclass(frozen=True, slots=True)
class StageUnlockPlan:
    progress: BiotopeProgress
    stage_id: str


@dataclass(frozen=True, slots=True)
class BiotopeCatchResult:
    progress: BiotopeProgress
    biotope_id: str
    mastery: BiotopeMastery
    xp_earned: int
    levels_gained: int


def biotope_from_record(record: Mapping[str, Any]) -> BiotopeSpec:
    if not isinstance(record, Mapping):
        raise TypeError("biotope record must be a mapping")
    environments = record.get("environments", ())
    best_times = record.get("best_times", ())
    weather_effects = record.get("weather_effects", {})
    required_boat = record.get("required_boat", False)
    if not isinstance(required_boat, bool):
        raise TypeError("biotope required_boat must be boolean")
    return BiotopeSpec(
        id=_token(record.get("id"), "biotope id"),
        name=_text(record.get("name"), "biotope name"),
        salinity=_token(record.get("salinity", "unknown"), "biotope salinity"),
        environments=_tokens(environments, "biotope environment"),
        best_times=_tokens(best_times, "biotope best time"),
        weather_effects=_multipliers(weather_effects, "biotope weather effect"),
        unlock_level=_positive_int(record.get("unlock_level", 1), "biotope unlock level"),
        required_boat=required_boat,
    )


def stage_from_record(record: Mapping[str, Any]) -> BiotopeStageSpec:
    if not isinstance(record, Mapping):
        raise TypeError("biotope stage record must be a mapping")
    return BiotopeStageSpec(
        id=_token(record.get("id"), "biotope stage id"),
        name=_text(record.get("name"), "biotope stage name"),
        biotope_id=_token(record.get("biotope"), "biotope stage biotope id"),
        stage_number=_positive_int(record.get("stage_number"), "biotope stage number"),
        unlock_level=_positive_int(record.get("unlock_level", 1), "biotope stage unlock level"),
        difficulty=_positive_int(record.get("difficulty", 1), "biotope stage difficulty"),
        fish_pool=_tokens(record.get("fish_pool", ()), "stage fish"),
        rare_pool=_tokens(record.get("rare_pool", ()), "stage rare fish"),
        legendary_pool=_tokens(record.get("legendary_pool", ()), "stage legendary fish"),
    )


def initial_biotope_progress(
    *,
    starter_biotope_id: str,
    starter_stage_id: str,
) -> BiotopeProgress:
    biotope_id = _token(starter_biotope_id, "starter biotope id")
    stage_id = _token(starter_stage_id, "starter stage id")
    return BiotopeProgress(
        unlocked_biotopes=frozenset({biotope_id}),
        unlocked_stages=frozenset({stage_id}),
        current_biotope=biotope_id,
        current_stage=stage_id,
        mastery={biotope_id: BiotopeMastery()},
    )


def mastery_xp_threshold(level: int) -> int:
    return _positive_int(level, "biotope mastery level") * 100


def mastery_bonuses(level: int) -> BiotopeBonuses:
    value = _positive_int(level, "biotope mastery level")
    return BiotopeBonuses(
        catch_rate=1.0 + value * 0.02,
        rare_chance=1.0 + value * 0.03,
        xp_multiplier=1.0 + value * 0.01,
        coin_multiplier=1.0 + value * 0.015,
    )


def weather_multiplier(spec: BiotopeSpec, weather: str) -> float:
    if not isinstance(spec, BiotopeSpec):
        raise TypeError("spec must be BiotopeSpec")
    condition = _token(weather, "weather")
    return spec.weather_effects.get(condition, 1.0)


def biotope_unlock_requirements(
    spec: BiotopeSpec,
    progress: BiotopeProgress,
    *,
    user_level: int,
    has_boat: bool = False,
) -> tuple[str, ...]:
    if not isinstance(spec, BiotopeSpec):
        raise TypeError("spec must be BiotopeSpec")
    if not isinstance(progress, BiotopeProgress):
        raise TypeError("progress must be BiotopeProgress")
    level = _positive_int(user_level, "user level")
    if not isinstance(has_boat, bool):
        raise TypeError("has_boat must be boolean")
    missing: list[str] = []
    if spec.id in progress.unlocked_biotopes:
        missing.append("already_unlocked")
    if level < spec.unlock_level:
        missing.append(f"level:{spec.unlock_level}")
    if spec.required_boat and not has_boat:
        missing.append("boat")
    return tuple(missing)


def can_unlock_biotope(
    spec: BiotopeSpec,
    progress: BiotopeProgress,
    *,
    user_level: int,
    has_boat: bool = False,
) -> bool:
    return not biotope_unlock_requirements(
        spec, progress, user_level=user_level, has_boat=has_boat
    )


def stage_unlock_requirements(
    stage: BiotopeStageSpec,
    progress: BiotopeProgress,
    *,
    user_level: int,
) -> tuple[str, ...]:
    if not isinstance(stage, BiotopeStageSpec):
        raise TypeError("stage must be BiotopeStageSpec")
    if not isinstance(progress, BiotopeProgress):
        raise TypeError("progress must be BiotopeProgress")
    level = _positive_int(user_level, "user level")
    missing: list[str] = []
    if stage.id in progress.unlocked_stages:
        missing.append("already_unlocked")
    if stage.biotope_id not in progress.unlocked_biotopes:
        missing.append(f"biotope:{stage.biotope_id}")
    if level < stage.unlock_level:
        missing.append(f"level:{stage.unlock_level}")
    return tuple(missing)


def can_unlock_stage(
    stage: BiotopeStageSpec,
    progress: BiotopeProgress,
    *,
    user_level: int,
) -> bool:
    return not stage_unlock_requirements(stage, progress, user_level=user_level)


def unlockable_biotopes(
    specs: Sequence[BiotopeSpec],
    progress: BiotopeProgress,
    *,
    user_level: int,
    has_boat: bool = False,
) -> tuple[BiotopeSpec, ...]:
    if isinstance(specs, (str, bytes)) or not isinstance(specs, Sequence):
        raise TypeError("biotope specs must be a sequence")
    seen: set[str] = set()
    result: list[BiotopeSpec] = []
    for spec in specs:
        if not isinstance(spec, BiotopeSpec):
            raise TypeError("biotope specs must contain BiotopeSpec values")
        if spec.id in seen:
            raise ValueError(f"duplicate biotope spec id: {spec.id}")
        seen.add(spec.id)
        if can_unlock_biotope(spec, progress, user_level=user_level, has_boat=has_boat):
            result.append(spec)
    return tuple(result)


def unlockable_stages(
    stages: Sequence[BiotopeStageSpec],
    progress: BiotopeProgress,
    *,
    user_level: int,
) -> tuple[BiotopeStageSpec, ...]:
    if isinstance(stages, (str, bytes)) or not isinstance(stages, Sequence):
        raise TypeError("biotope stages must be a sequence")
    seen: set[str] = set()
    result: list[BiotopeStageSpec] = []
    for stage in stages:
        if not isinstance(stage, BiotopeStageSpec):
            raise TypeError("biotope stages must contain BiotopeStageSpec values")
        if stage.id in seen:
            raise ValueError(f"duplicate biotope stage id: {stage.id}")
        seen.add(stage.id)
        if can_unlock_stage(stage, progress, user_level=user_level):
            result.append(stage)
    return tuple(result)


def unlock_biotope(
    progress: BiotopeProgress,
    spec: BiotopeSpec,
    *,
    user_level: int,
    has_boat: bool = False,
    first_stage: BiotopeStageSpec | None = None,
) -> BiotopeUnlockPlan:
    requirements = biotope_unlock_requirements(
        spec, progress, user_level=user_level, has_boat=has_boat
    )
    if requirements:
        raise ValueError("biotope unlock requirements not met: " + ",".join(requirements))
    stages = set(progress.unlocked_stages)
    auto_stage_id: str | None = None
    if first_stage is not None:
        if not isinstance(first_stage, BiotopeStageSpec):
            raise TypeError("first_stage must be BiotopeStageSpec")
        if first_stage.biotope_id != spec.id or first_stage.stage_number != 1:
            raise ValueError("first_stage must be stage 1 of the unlocked biotope")
        if _positive_int(user_level, "user level") < first_stage.unlock_level:
            raise ValueError(f"first stage requires level {first_stage.unlock_level}")
        stages.add(first_stage.id)
        auto_stage_id = first_stage.id
    mastery = dict(progress.mastery)
    mastery.setdefault(spec.id, BiotopeMastery())
    next_progress = replace(
        progress,
        unlocked_biotopes=progress.unlocked_biotopes | {spec.id},
        unlocked_stages=frozenset(stages),
        mastery=mastery,
    )
    return BiotopeUnlockPlan(next_progress, spec.id, auto_stage_id)


def unlock_stage(
    progress: BiotopeProgress,
    stage: BiotopeStageSpec,
    *,
    user_level: int,
) -> StageUnlockPlan:
    requirements = stage_unlock_requirements(stage, progress, user_level=user_level)
    if requirements:
        raise ValueError("stage unlock requirements not met: " + ",".join(requirements))
    next_progress = replace(
        progress,
        unlocked_stages=progress.unlocked_stages | {stage.id},
    )
    return StageUnlockPlan(next_progress, stage.id)


def enter_stage(progress: BiotopeProgress, stage: BiotopeStageSpec) -> BiotopeProgress:
    if not isinstance(progress, BiotopeProgress):
        raise TypeError("progress must be BiotopeProgress")
    if not isinstance(stage, BiotopeStageSpec):
        raise TypeError("stage must be BiotopeStageSpec")
    if stage.biotope_id not in progress.unlocked_biotopes:
        raise ValueError("stage biotope is not unlocked")
    if stage.id not in progress.unlocked_stages:
        raise ValueError("stage is not unlocked")
    return replace(
        progress,
        current_biotope=stage.biotope_id,
        current_stage=stage.id,
    )


def set_favorite_biotope(progress: BiotopeProgress, biotope_id: str) -> BiotopeProgress:
    if not isinstance(progress, BiotopeProgress):
        raise TypeError("progress must be BiotopeProgress")
    target = _token(biotope_id, "favorite biotope")
    if target not in progress.unlocked_biotopes:
        raise ValueError("favorite biotope must be unlocked")
    return replace(progress, favorite_biotope=target)


def _mastery_after_xp(mastery: BiotopeMastery, xp_earned: int) -> tuple[BiotopeMastery, int]:
    earned = _nonnegative_int(xp_earned, "biotope xp earned")
    available = mastery.xp + earned
    level = mastery.level
    threshold_units = available // 100
    coefficient = 2 * level - 1
    discriminant = coefficient * coefficient + 8 * threshold_units
    levels = max(0, (-coefficient + isqrt(discriminant)) // 2)
    consumed = 100 * levels * (2 * level + levels - 1) // 2
    remaining = available - consumed
    next_level = level + levels
    while remaining >= mastery_xp_threshold(next_level):
        remaining -= mastery_xp_threshold(next_level)
        next_level += 1
        levels += 1
    return (
        BiotopeMastery(level=next_level, xp=remaining, catches=mastery.catches + 1),
        levels,
    )


def record_biotope_catch(
    progress: BiotopeProgress,
    biotope_id: str,
    *,
    xp_earned: int = 10,
) -> BiotopeCatchResult:
    if not isinstance(progress, BiotopeProgress):
        raise TypeError("progress must be BiotopeProgress")
    target = _token(biotope_id, "catch biotope id")
    if target not in progress.unlocked_biotopes:
        raise ValueError("catch biotope must be unlocked")
    current = progress.mastery.get(target, BiotopeMastery())
    updated, levels = _mastery_after_xp(current, xp_earned)
    mastery = dict(progress.mastery)
    mastery[target] = updated
    next_progress = replace(progress, mastery=mastery)
    return BiotopeCatchResult(
        progress=next_progress,
        biotope_id=target,
        mastery=updated,
        xp_earned=_nonnegative_int(xp_earned, "biotope xp earned"),
        levels_gained=levels,
    )
