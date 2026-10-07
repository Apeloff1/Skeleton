"""Pure quest progression policy from the shared Lorebuffa/Openworld lineage.

Both sources use ``backend/quest_system.py`` blob
``c572dcc8919d342a8febb224e0131047b47c2644``. The 400-entry catalog, FastAPI
routes and MongoDB mutations remain source-owned; only portable progression and
reward planning rules are promoted here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class QuestSpec:
    id: str
    name: str
    quest_type: str
    objectives: tuple[Mapping[str, Any], ...]
    rewards: Mapping[str, Any]
    prerequisite: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ObjectiveProgress:
    current: int
    target: int
    completed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "current": self.current,
            "target": self.target,
            "completed": self.completed,
        }


@dataclass(frozen=True, slots=True)
class QuestProgressState:
    quest_id: str
    status: str
    objectives: Mapping[str, ObjectiveProgress]

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "quest_id": self.quest_id,
            "status": self.status,
            "objectives_progress": {
                key: value.as_dict() for key, value in self.objectives.items()
            },
        }


@dataclass(frozen=True, slots=True)
class RewardPlan:
    increments: Mapping[str, int] = field(default_factory=dict)
    items: tuple[str, ...] = ()
    titles: tuple[str, ...] = ()
    signals: Mapping[str, Any] = field(default_factory=dict)


def quest_from_record(record: Mapping[str, Any]) -> QuestSpec:
    quest_id = str(record.get("id") or "").strip()
    name = str(record.get("name") or "").strip()
    quest_type = str(record.get("type") or "").strip().lower()
    if not quest_id or not name or not quest_type:
        raise ValueError("quest requires non-empty id, name and type")

    raw_objectives = record.get("objectives")
    if not isinstance(raw_objectives, Sequence) or isinstance(raw_objectives, (str, bytes)):
        raise TypeError("quest objectives must be a sequence")
    objectives: list[Mapping[str, Any]] = []
    for index, objective in enumerate(raw_objectives):
        if not isinstance(objective, Mapping):
            raise TypeError(f"quest objective {index} must be a mapping")
        normalized = dict(objective)
        try:
            target = int(normalized.get("count", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"quest objective {index} count must be an integer") from exc
        if target < 1:
            raise ValueError(f"quest objective {index} count must be positive")
        normalized["count"] = target
        objectives.append(normalized)
    if not objectives:
        raise ValueError("quest requires at least one objective")

    rewards = record.get("rewards") or {}
    if not isinstance(rewards, Mapping):
        raise TypeError("quest rewards must be a mapping")

    prerequisite = record.get("prerequisite")
    if prerequisite is not None:
        prerequisite = str(prerequisite).strip() or None
        if prerequisite == quest_id:
            raise ValueError("quest cannot require itself")

    consumed = {
        "id",
        "name",
        "type",
        "objectives",
        "rewards",
        "prerequisite",
    }
    metadata = {key: value for key, value in record.items() if key not in consumed}
    return QuestSpec(
        id=quest_id,
        name=name,
        quest_type=quest_type,
        objectives=tuple(objectives),
        rewards=dict(rewards),
        prerequisite=prerequisite,
        metadata=metadata,
    )


def available_quests(
    quests: Sequence[QuestSpec],
    completed_quest_ids: Sequence[str],
) -> tuple[QuestSpec, ...]:
    """Filter source-style available quests by completion and prerequisite."""

    completed = {str(quest_id).strip() for quest_id in completed_quest_ids}
    seen: set[str] = set()
    available: list[QuestSpec] = []
    for quest in quests:
        if quest.id in seen:
            raise ValueError(f"duplicate quest id: {quest.id}")
        seen.add(quest.id)
        if quest.id in completed:
            continue
        if quest.prerequisite and quest.prerequisite not in completed:
            continue
        available.append(quest)
    return tuple(available)


def initialize_progress(quest: QuestSpec) -> QuestProgressState:
    objectives = {
        str(index): ObjectiveProgress(current=0, target=int(objective["count"]), completed=False)
        for index, objective in enumerate(quest.objectives)
    }
    return QuestProgressState(
        quest_id=quest.id,
        status="in_progress",
        objectives=objectives,
    )


def update_objective_progress(
    state: QuestProgressState,
    objective_id: str,
    progress: int,
) -> QuestProgressState:
    """Advance one objective monotonically and clamp it to the target."""

    if state.completed:
        return state
    objective_id = objective_id.strip()
    if objective_id not in state.objectives:
        raise KeyError(f"unknown quest objective: {objective_id}")
    try:
        progress = int(progress)
    except (TypeError, ValueError) as exc:
        raise ValueError("quest progress must be an integer") from exc
    if progress < 0:
        raise ValueError("quest progress must not be negative")

    objectives = dict(state.objectives)
    previous = objectives[objective_id]
    current = max(previous.current, min(progress, previous.target))
    objectives[objective_id] = ObjectiveProgress(
        current=current,
        target=previous.target,
        completed=current >= previous.target,
    )
    completed = all(objective.completed for objective in objectives.values())
    return QuestProgressState(
        quest_id=state.quest_id,
        status="completed" if completed else "in_progress",
        objectives=objectives,
    )


def reward_plan(rewards: Mapping[str, Any]) -> RewardPlan:
    """Translate source rewards into mutation-free portable effects."""

    increments: dict[str, int] = {}
    for key in ("gold", "xp"):
        if key not in rewards:
            continue
        try:
            value = int(rewards[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"quest reward {key!r} must be an integer") from exc
        if value < 0:
            raise ValueError(f"quest reward {key!r} must not be negative")
        increments[key] = value

    items: list[str] = []
    raw_item = rewards.get("item")
    if raw_item is not None:
        if isinstance(raw_item, Sequence) and not isinstance(raw_item, (str, bytes)):
            items.extend(str(item).strip() for item in raw_item if str(item).strip())
        else:
            item = str(raw_item).strip()
            if item:
                items.append(item)

    titles: list[str] = []
    raw_title = rewards.get("title")
    if raw_title is not None:
        if isinstance(raw_title, Sequence) and not isinstance(raw_title, (str, bytes)):
            titles.extend(str(title).strip() for title in raw_title if str(title).strip())
        else:
            title = str(raw_title).strip()
            if title:
                titles.append(title)

    signals = {
        key: value
        for key, value in rewards.items()
        if key not in {"gold", "xp", "item", "title"}
    }
    return RewardPlan(
        increments=increments,
        items=tuple(items),
        titles=tuple(titles),
        signals=signals,
    )


def select_quests_by_type(
    quests: Sequence[QuestSpec],
    quest_type: str,
    *,
    limit: int,
) -> tuple[QuestSpec, ...]:
    """Preserve deterministic daily/weekly selection without source catalog copy."""

    quest_type = quest_type.strip().lower()
    if not quest_type:
        raise ValueError("quest_type must not be empty")
    if limit < 1:
        return ()
    return tuple(quest for quest in quests if quest.quest_type == quest_type)[:limit]
