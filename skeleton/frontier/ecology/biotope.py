"""Dependency-free biotope progression policy promoted from Lorebuffa/Openworld.

The source repositories carry an exact-shared ``backend/biotope_routes.py``
implementation. FastAPI routes, MongoDB access, static source catalogs and
leaderboard persistence remain source-owned. This module promotes only the
portable progression semantics: level-gated biotope/stage unlocks, sequential
stage progression, active-stage selection, per-biotope mastery XP and bonuses.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Iterable, Mapping


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be non-empty and normalized")
    return value


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


def _text_set(values: Iterable[str], field_name: str) -> frozenset[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result: set[str] = set()
    for value in values:
        result.add(_text(value, f"{field_name} entry"))
    return frozenset(result)


def _int_map(
    values: Mapping[str, int],
    field_name: str,
    *,
    positive: bool = False,
) -> Mapping[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, int] = {}
    validator = _positive_int if positive else _nonnegative_int
    for raw_key, raw_value in values.items():
        key = _text(raw_key, f"{field_name} key")
        if key in normalized:
            raise ValueError(f"duplicate {field_name} key: {key}")
        normalized[key] = validator(raw_value, f"{field_name}[{key!r}]")
    return MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class BiotopeSpec:
    id: str
    unlock_level: int
    required_boat: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "biotope id"))
        object.__setattr__(
            self,
            "unlock_level",
            _positive_int(self.unlock_level, "biotope unlock_level"),
        )
        if not isinstance(self.required_boat, bool):
            raise TypeError("biotope required_boat must be a boolean")


@dataclass(frozen=True, slots=True)
class BiotopeStageSpec:
    id: str
    biotope_id: str
    stage_number: int
    unlock_level: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "biotope stage id"))
        object.__setattr__(
            self,
            "biotope_id",
            _text(self.biotope_id, "biotope stage biotope_id"),
        )
        object.__setattr__(
            self,
            "stage_number",
            _positive_int(self.stage_number, "biotope stage stage_number"),
        )
        object.__setattr__(
            self,
            "unlock_level",
            _positive_int(self.unlock_level, "biotope stage unlock_level"),
        )


@dataclass(frozen=True, slots=True)
class BiotopeBonus:
    catch_rate: float
    rare_chance: float
    xp_bonus: float
    coin_bonus: float


@dataclass(frozen=True, slots=True)
class BiotopeProgress:
    unlocked_biotopes: frozenset[str]
    unlocked_stages: frozenset[str]
    current_biotope: str | None
    current_stage: str | None
    biotope_xp: Mapping[str, int]
    biotope_level: Mapping[str, int]
    fish_caught_by_biotope: Mapping[str, int]

    def __post_init__(self) -> None:
        unlocked_biotopes = _text_set(self.unlocked_biotopes, "unlocked_biotopes")
        unlocked_stages = _text_set(self.unlocked_stages, "unlocked_stages")
        object.__setattr__(self, "unlocked_biotopes", unlocked_biotopes)
        object.__setattr__(self, "unlocked_stages", unlocked_stages)

        current_biotope = self.current_biotope
        if current_biotope is not None:
            current_biotope = _text(current_biotope, "current_biotope")
            if current_biotope not in unlocked_biotopes:
                raise ValueError("current_biotope must be unlocked")
        object.__setattr__(self, "current_biotope", current_biotope)

        current_stage = self.current_stage
        if current_stage is not None:
            current_stage = _text(current_stage, "current_stage")
            if current_stage not in unlocked_stages:
                raise ValueError("current_stage must be unlocked")
        object.__setattr__(self, "current_stage", current_stage)

        object.__setattr__(
            self,
            "biotope_xp",
            _int_map(self.biotope_xp, "biotope_xp"),
        )
        object.__setattr__(
            self,
            "biotope_level",
            _int_map(self.biotope_level, "biotope_level", positive=True),
        )
        object.__setattr__(
            self,
            "fish_caught_by_biotope",
            _int_map(self.fish_caught_by_biotope, "fish_caught_by_biotope"),
        )

        tracked = (
            set(self.biotope_xp)
            | set(self.biotope_level)
            | set(self.fish_caught_by_biotope)
        )
        if not tracked.issubset(unlocked_biotopes):
            raise ValueError("biotope progress maps may only track unlocked biotopes")


@dataclass(frozen=True, slots=True)
class BiotopeCatchPlan:
    progress: BiotopeProgress
    biotope_id: str
    xp_earned: int
    levels_gained: int
    bonus: BiotopeBonus


def initial_progress(
    *,
    default_biotope_id: str = "freshwater_lake",
    default_stage_id: str = "pond",
) -> BiotopeProgress:
    biotope_id = _text(default_biotope_id, "default_biotope_id")
    stage_id = _text(default_stage_id, "default_stage_id")
    return BiotopeProgress(
        unlocked_biotopes=frozenset({biotope_id}),
        unlocked_stages=frozenset({stage_id}),
        current_biotope=biotope_id,
        current_stage=stage_id,
        biotope_xp={biotope_id: 0},
        biotope_level={biotope_id: 1},
        fish_caught_by_biotope={biotope_id: 0},
    )


def calculate_biotope_bonus(level: int) -> BiotopeBonus:
    mastery_level = _positive_int(level, "biotope level")
    return BiotopeBonus(
        catch_rate=1.0 + mastery_level * 0.02,
        rare_chance=1.0 + mastery_level * 0.03,
        xp_bonus=1.0 + mastery_level * 0.01,
        coin_bonus=1.0 + mastery_level * 0.015,
    )


def _catalog_by_id(
    specs: Iterable[BiotopeStageSpec],
) -> dict[str, BiotopeStageSpec]:
    if isinstance(specs, (str, bytes)):
        raise TypeError("biotope stages must be an iterable of BiotopeStageSpec")
    result: dict[str, BiotopeStageSpec] = {}
    for spec in specs:
        if not isinstance(spec, BiotopeStageSpec):
            raise TypeError("biotope stages must contain BiotopeStageSpec values")
        if spec.id in result:
            raise ValueError(f"duplicate biotope stage id: {spec.id}")
        result[spec.id] = spec
    return result


def _stages_for_biotope(
    biotope_id: str,
    specs: Iterable[BiotopeStageSpec],
) -> tuple[BiotopeStageSpec, ...]:
    catalog = _catalog_by_id(specs)
    stages = tuple(
        sorted(
            (spec for spec in catalog.values() if spec.biotope_id == biotope_id),
            key=lambda spec: (spec.stage_number, spec.id),
        )
    )
    seen_numbers: set[int] = set()
    for stage in stages:
        if stage.stage_number in seen_numbers:
            raise ValueError(
                f"duplicate stage number {stage.stage_number} for biotope {biotope_id}"
            )
        seen_numbers.add(stage.stage_number)
    expected_numbers = set(range(1, len(stages) + 1))
    if seen_numbers != expected_numbers:
        raise ValueError(
            f"stage progression for biotope {biotope_id} must be contiguous and start at 1"
        )
    return stages


def can_unlock_biotope(
    progress: BiotopeProgress,
    spec: BiotopeSpec,
    *,
    player_level: int,
    has_boat: bool = False,
) -> bool:
    if not isinstance(progress, BiotopeProgress):
        raise TypeError("progress must be BiotopeProgress")
    if not isinstance(spec, BiotopeSpec):
        raise TypeError("spec must be BiotopeSpec")
    level = _positive_int(player_level, "player_level")
    if not isinstance(has_boat, bool):
        raise TypeError("has_boat must be a boolean")
    return (
        spec.id not in progress.unlocked_biotopes
        and level >= spec.unlock_level
        and (not spec.required_boat or has_boat)
    )


def unlock_biotope(
    progress: BiotopeProgress,
    spec: BiotopeSpec,
    *,
    stages: Iterable[BiotopeStageSpec],
    player_level: int,
    has_boat: bool = False,
) -> BiotopeProgress:
    if spec.id in progress.unlocked_biotopes:
        raise ValueError("biotope already unlocked")
    if not can_unlock_biotope(
        progress,
        spec,
        player_level=player_level,
        has_boat=has_boat,
    ):
        if spec.required_boat and not has_boat:
            raise PermissionError("biotope requires a boat")
        raise PermissionError(f"biotope requires player level {spec.unlock_level}")

    candidates = _stages_for_biotope(spec.id, stages)
    first_stage = next((stage for stage in candidates if stage.stage_number == 1), None)
    if first_stage is None:
        raise ValueError("biotope must define exactly one stage 1 before it can be unlocked")

    xp = dict(progress.biotope_xp)
    levels = dict(progress.biotope_level)
    catches = dict(progress.fish_caught_by_biotope)
    xp[spec.id] = 0
    levels[spec.id] = 1
    catches[spec.id] = 0
    return replace(
        progress,
        unlocked_biotopes=progress.unlocked_biotopes | {spec.id},
        unlocked_stages=progress.unlocked_stages | {first_stage.id},
        biotope_xp=xp,
        biotope_level=levels,
        fish_caught_by_biotope=catches,
    )


def can_unlock_stage(
    progress: BiotopeProgress,
    stage: BiotopeStageSpec,
    *,
    stages: Iterable[BiotopeStageSpec],
    player_level: int,
) -> bool:
    if not isinstance(progress, BiotopeProgress):
        raise TypeError("progress must be BiotopeProgress")
    if not isinstance(stage, BiotopeStageSpec):
        raise TypeError("stage must be BiotopeStageSpec")
    level = _positive_int(player_level, "player_level")
    candidates = _stages_for_biotope(stage.biotope_id, stages)
    catalog_stage = next((candidate for candidate in candidates if candidate.id == stage.id), None)
    if catalog_stage is None or catalog_stage != stage:
        raise ValueError("stage must match the supplied biotope stage catalog")
    if stage.id in progress.unlocked_stages:
        return False
    if stage.biotope_id not in progress.unlocked_biotopes:
        return False
    if level < stage.unlock_level:
        return False
    if stage.stage_number == 1:
        return True

    previous = next(
        (
            candidate
            for candidate in candidates
            if candidate.stage_number == stage.stage_number - 1
        ),
        None,
    )
    if previous is None:
        raise ValueError("stage progression must be contiguous")
    return previous.id in progress.unlocked_stages


def unlock_stage(
    progress: BiotopeProgress,
    stage: BiotopeStageSpec,
    *,
    stages: Iterable[BiotopeStageSpec],
    player_level: int,
) -> BiotopeProgress:
    if stage.id in progress.unlocked_stages:
        raise ValueError("stage already unlocked")
    if stage.biotope_id not in progress.unlocked_biotopes:
        raise PermissionError("unlock biotope first")
    if not can_unlock_stage(
        progress,
        stage,
        stages=stages,
        player_level=player_level,
    ):
        level = _positive_int(player_level, "player_level")
        if level < stage.unlock_level:
            raise PermissionError(f"stage requires player level {stage.unlock_level}")
        raise PermissionError("unlock previous stage first")
    return replace(
        progress,
        unlocked_stages=progress.unlocked_stages | {stage.id},
    )


def enter_stage(
    progress: BiotopeProgress,
    stage: BiotopeStageSpec,
    *,
    stages: Iterable[BiotopeStageSpec],
) -> BiotopeProgress:
    if not isinstance(progress, BiotopeProgress):
        raise TypeError("progress must be BiotopeProgress")
    if not isinstance(stage, BiotopeStageSpec):
        raise TypeError("stage must be BiotopeStageSpec")

    catalog = _catalog_by_id(stages)
    candidates = _stages_for_biotope(stage.biotope_id, catalog.values())
    catalog_stage = next(
        (candidate for candidate in candidates if candidate.id == stage.id),
        None,
    )
    if catalog_stage is None or catalog_stage != stage:
        raise ValueError("stage must match the supplied biotope stage catalog")

    if stage.biotope_id not in progress.unlocked_biotopes:
        raise PermissionError("stage biotope is not unlocked")
    if stage.id not in progress.unlocked_stages:
        raise PermissionError("stage is not unlocked")
    return replace(
        progress,
        current_biotope=stage.biotope_id,
        current_stage=stage.id,
    )


def record_catch(
    progress: BiotopeProgress,
    biotope_id: str,
    *,
    xp_earned: int = 10,
) -> BiotopeCatchPlan:
    if not isinstance(progress, BiotopeProgress):
        raise TypeError("progress must be BiotopeProgress")
    target = _text(biotope_id, "biotope_id")
    gained = _nonnegative_int(xp_earned, "xp_earned")
    if target not in progress.unlocked_biotopes:
        raise PermissionError("cannot record a catch for a locked biotope")

    xp = dict(progress.biotope_xp)
    levels = dict(progress.biotope_level)
    catches = dict(progress.fish_caught_by_biotope)
    current_xp = xp.get(target, 0) + gained
    current_level = levels.get(target, 1)
    levels_gained = 0

    # The source checks one threshold per request. The promoted pure policy
    # drains all crossed thresholds so unusually large valid XP awards cannot
    # leave an internally stale mastery level.
    while current_xp >= current_level * 100:
        current_xp -= current_level * 100
        current_level += 1
        levels_gained += 1

    xp[target] = current_xp
    levels[target] = current_level
    catches[target] = catches.get(target, 0) + 1
    updated = replace(
        progress,
        biotope_xp=xp,
        biotope_level=levels,
        fish_caught_by_biotope=catches,
    )
    return BiotopeCatchPlan(
        progress=updated,
        biotope_id=target,
        xp_earned=gained,
        levels_gained=levels_gained,
        bonus=calculate_biotope_bonus(current_level),
    )


def unlockable_biotopes(
    progress: BiotopeProgress,
    specs: Iterable[BiotopeSpec],
    *,
    player_level: int,
    has_boat: bool = False,
) -> tuple[BiotopeSpec, ...]:
    if isinstance(specs, (str, bytes)):
        raise TypeError("biotopes must be an iterable of BiotopeSpec")
    catalog: dict[str, BiotopeSpec] = {}
    for spec in specs:
        if not isinstance(spec, BiotopeSpec):
            raise TypeError("biotopes must contain BiotopeSpec values")
        if spec.id in catalog:
            raise ValueError(f"duplicate biotope id: {spec.id}")
        catalog[spec.id] = spec
    return tuple(
        sorted(
            (
                spec
                for spec in catalog.values()
                if can_unlock_biotope(
                    progress,
                    spec,
                    player_level=player_level,
                    has_boat=has_boat,
                )
            ),
            key=lambda spec: (spec.unlock_level, spec.id),
        )
    )


def unlockable_stages(
    progress: BiotopeProgress,
    stages: Iterable[BiotopeStageSpec],
    *,
    player_level: int,
) -> tuple[BiotopeStageSpec, ...]:
    catalog = _catalog_by_id(stages)
    result: list[BiotopeStageSpec] = []
    for stage in catalog.values():
        if can_unlock_stage(
            progress,
            stage,
            stages=catalog.values(),
            player_level=player_level,
        ):
            result.append(stage)
    return tuple(
        sorted(result, key=lambda stage: (stage.biotope_id, stage.stage_number, stage.id))
    )
