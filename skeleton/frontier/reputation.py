"""Pure reputation policy from the shared Lorebuffa/Openworld lineage.

Both source repositories use ``backend/reputation_system.py`` blob
``1ee119789969f963d258128ff544ea81bfd86526``. The faction catalog, FastAPI
routes and MongoDB mutations remain source-owned. The source level ranges have
inclusive overlapping edges; the promoted policy resolves them by treating
``min_rep`` thresholds as canonical lower bounds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True, order=True)
class ReputationLevel:
    min_rep: int
    rank: int
    name: str = field(compare=False)
    color: str = field(default="", compare=False)


DEFAULT_REPUTATION_LEVELS: tuple[ReputationLevel, ...] = (
    ReputationLevel(min_rep=-1000, rank=-3, name="Hated", color="#8b0000"),
    ReputationLevel(min_rep=-500, rank=-2, name="Hostile", color="#dc143c"),
    ReputationLevel(min_rep=-200, rank=-1, name="Unfriendly", color="#ff6347"),
    ReputationLevel(min_rep=0, rank=0, name="Neutral", color="#808080"),
    ReputationLevel(min_rep=500, rank=1, name="Friendly", color="#90ee90"),
    ReputationLevel(min_rep=3000, rank=2, name="Honored", color="#32cd32"),
    ReputationLevel(min_rep=9000, rank=3, name="Revered", color="#228b22"),
    ReputationLevel(min_rep=21000, rank=4, name="Exalted", color="#ffd700"),
)


@dataclass(frozen=True, slots=True)
class FactionSpec:
    id: str
    name: str
    benefits: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    allies: tuple[str, ...] = ()
    enemies: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReputationDelta:
    faction_id: str
    amount: int
    effect_type: str


@dataclass(frozen=True, slots=True)
class ReputationChangeResult:
    old_reputation: int
    new_reputation: int
    old_level: ReputationLevel
    new_level: ReputationLevel
    level_changed: bool
    new_benefits: tuple[str, ...]
    spillover: tuple[ReputationDelta, ...]


def _strings(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be a sequence")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip().lower()
        if text and text not in seen:
            seen.add(text)
            normalized.append(text)
    return tuple(normalized)


def faction_from_record(record: Mapping[str, Any]) -> FactionSpec:
    faction_id = str(record.get("id") or "").strip().lower()
    name = str(record.get("name") or "").strip()
    if not faction_id or not name:
        raise ValueError("faction requires non-empty id and name")

    allies = _strings(record.get("allies"), field_name="allies")
    enemies = _strings(record.get("enemies"), field_name="enemies")
    if faction_id in allies or faction_id in enemies:
        raise ValueError("faction cannot be allied with or hostile to itself")
    overlap = sorted(set(allies).intersection(enemies))
    if overlap:
        raise ValueError(f"faction allies and enemies overlap: {', '.join(overlap)}")

    raw_benefits = record.get("benefits") or {}
    if not isinstance(raw_benefits, Mapping):
        raise TypeError("faction benefits must be a mapping")
    benefits: dict[str, tuple[str, ...]] = {}
    for level_name, values in raw_benefits.items():
        normalized_level = str(level_name).strip().lower()
        if not normalized_level:
            raise ValueError("faction benefit level must not be empty")
        benefits[normalized_level] = _strings(
            values,
            field_name=f"benefits.{normalized_level}",
        )

    consumed = {"id", "name", "benefits", "allies", "enemies"}
    metadata = {key: value for key, value in record.items() if key not in consumed}
    return FactionSpec(
        id=faction_id,
        name=name,
        benefits=benefits,
        allies=allies,
        enemies=enemies,
        metadata=metadata,
    )


def _validated_levels(
    levels: Sequence[ReputationLevel],
) -> tuple[ReputationLevel, ...]:
    if not levels:
        raise ValueError("reputation levels must not be empty")
    ordered = tuple(sorted(levels, key=lambda level: level.min_rep))
    if len({level.min_rep for level in ordered}) != len(ordered):
        raise ValueError("reputation level min_rep thresholds must be unique")
    if len({level.rank for level in ordered}) != len(ordered):
        raise ValueError("reputation level ranks must be unique")
    if any(not level.name.strip() for level in ordered):
        raise ValueError("reputation level names must not be empty")
    if len({level.name.casefold() for level in ordered}) != len(ordered):
        raise ValueError("reputation level names must be unique")
    ranks = [level.rank for level in ordered]
    if ranks != sorted(ranks):
        raise ValueError("reputation level ranks must increase with min_rep")
    return ordered


def reputation_level(
    score: int,
    *,
    levels: Sequence[ReputationLevel] = DEFAULT_REPUTATION_LEVELS,
) -> ReputationLevel:
    """Resolve the greatest lower-bound reputation threshold for ``score``."""

    try:
        score = int(score)
    except (TypeError, ValueError) as exc:
        raise ValueError("reputation score must be an integer") from exc
    ordered = _validated_levels(levels)
    selected = ordered[0]
    for level in ordered:
        if score < level.min_rep:
            break
        selected = level
    return selected


def next_reputation_level(
    score: int,
    *,
    levels: Sequence[ReputationLevel] = DEFAULT_REPUTATION_LEVELS,
) -> dict[str, Any] | None:
    current = reputation_level(score, levels=levels)
    ordered = _validated_levels(levels)
    index = ordered.index(current)
    if index >= len(ordered) - 1:
        return None
    next_level = ordered[index + 1]
    numeric_score = int(score)
    return {
        "name": next_level.name,
        "required": next_level.min_rep,
        "needed": max(0, next_level.min_rep - numeric_score),
    }


def current_benefits(
    faction: FactionSpec,
    level_name: str,
    *,
    cumulative_order: Sequence[str] = ("friendly", "honored", "revered", "exalted"),
) -> tuple[str, ...]:
    """Return source-compatible cumulative benefits through the current tier."""

    normalized = level_name.strip().lower()
    order = tuple(str(level).strip().lower() for level in cumulative_order)
    if any(not level for level in order):
        raise ValueError("benefit level order must not contain empty values")
    if len(set(order)) != len(order):
        raise ValueError("benefit level order must not contain duplicates")
    if normalized not in order:
        return ()

    benefits: list[str] = []
    seen: set[str] = set()
    through = order.index(normalized)
    for level in order[: through + 1]:
        for benefit in faction.benefits.get(level, ()):
            if benefit not in seen:
                seen.add(benefit)
                benefits.append(benefit)
    return tuple(benefits)


def calculate_spillover(faction: FactionSpec, amount: int) -> tuple[ReputationDelta, ...]:
    """Calculate mutation-free ally/enemy spillover using source percentages."""

    try:
        amount = int(amount)
    except (TypeError, ValueError) as exc:
        raise ValueError("reputation amount must be an integer") from exc
    if amount == 0:
        return ()

    deltas: list[ReputationDelta] = []
    if amount > 0:
        ally_amount = int(amount * 0.25)
        if ally_amount > 0:
            deltas.extend(
                ReputationDelta(ally, ally_amount, "ally_bonus")
                for ally in faction.allies
            )
        enemy_amount = int(amount * -0.5)
        if enemy_amount:
            deltas.extend(
                ReputationDelta(enemy, enemy_amount, "enemy_penalty")
                for enemy in faction.enemies
            )
    else:
        ally_loss = int(amount * 0.25)
        if ally_loss:
            deltas.extend(
                ReputationDelta(ally, ally_loss, "ally_sympathy")
                for ally in faction.allies
            )
    return tuple(deltas)


def apply_reputation_change(
    faction: FactionSpec,
    current_score: int,
    amount: int,
    *,
    levels: Sequence[ReputationLevel] = DEFAULT_REPUTATION_LEVELS,
) -> ReputationChangeResult:
    try:
        current_score = int(current_score)
        amount = int(amount)
    except (TypeError, ValueError) as exc:
        raise ValueError("reputation score and amount must be integers") from exc

    old_level = reputation_level(current_score, levels=levels)
    new_score = current_score + amount
    new_level = reputation_level(new_score, levels=levels)
    changed = old_level.name != new_level.name
    return ReputationChangeResult(
        old_reputation=current_score,
        new_reputation=new_score,
        old_level=old_level,
        new_level=new_level,
        level_changed=changed,
        new_benefits=(
            current_benefits(faction, new_level.name) if changed else ()
        ),
        spillover=calculate_spillover(faction, amount),
    )


def standing_summary(
    reputation_by_faction: Mapping[str, int],
    faction_ids: Sequence[str],
    *,
    levels: Sequence[ReputationLevel] = DEFAULT_REPUTATION_LEVELS,
) -> dict[str, Any]:
    """Build source-style standings while counting untracked factions Neutral."""

    canonical_ids: list[str] = []
    known: set[str] = set()
    for value in faction_ids:
        faction_id = str(value).strip().lower()
        if not faction_id:
            raise ValueError("faction id must not be empty")
        if faction_id in known:
            raise ValueError(f"duplicate faction id: {faction_id}")
        known.add(faction_id)
        canonical_ids.append(faction_id)

    canonical_reputation: dict[str, int] = {}
    for raw_id, score in reputation_by_faction.items():
        faction_id = str(raw_id).strip().lower()
        if not faction_id:
            raise ValueError("reputation faction id must not be empty")
        if faction_id in canonical_reputation:
            raise ValueError(f"duplicate reputation faction id: {faction_id}")
        canonical_reputation[faction_id] = int(score)

    unknown = sorted(set(canonical_reputation).difference(known))
    if unknown:
        raise KeyError(f"unknown reputation factions: {', '.join(unknown)}")

    ordered_levels = _validated_levels(levels)
    standings = {level.name.lower(): 0 for level in ordered_levels}
    best: dict[str, Any] | None = None
    worst: dict[str, Any] | None = None

    for faction_id in canonical_ids:
        if faction_id not in canonical_reputation:
            standings["neutral"] = standings.get("neutral", 0) + 1
            continue
        score = canonical_reputation[faction_id]
        level = reputation_level(score, levels=ordered_levels)
        standings[level.name.lower()] = standings.get(level.name.lower(), 0) + 1
        candidate = {
            "faction": faction_id,
            "reputation": score,
            "level": level.name,
        }
        if best is None or score > best["reputation"]:
            best = candidate
        if worst is None or score < worst["reputation"]:
            worst = candidate

    return {
        "total_factions": len(canonical_ids),
        "standings": standings,
        "best_standing": best,
        "worst_standing": worst,
    }
