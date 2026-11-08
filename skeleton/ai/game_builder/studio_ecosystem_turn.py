"""One authoritative, replayable studio narrative turn, no phantom gameplay."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .studio_ecosystem_quest import (
    QuestSession, StudioQuestError, step_quest, verify_quest_session,
    quest_progress,
)
from .studio_ecosystem_scene import inspect_object_intent, scene_catalog
from .studio_ecosystem_social import replay_factions


@dataclass(frozen=True, slots=True)
class StoryTurn:
    previous_quest_digest: str
    quest: QuestSession
    intent: dict[str, object]
    social_receipt: dict[str, object]
    progress: dict[str, object]


def apply_story_turn(documents: Mapping[str, Any], session: QuestSession, *,
                     scene_id: str, object_id: str, stage: str, alternative: str,
                     social_history: Sequence[str] = (), authorized: bool) -> StoryTurn:
    """Require a real source scene and current stage before advancing replay."""
    if not authorized:
        raise PermissionError("story execution requires operator authorization")
    verify_quest_session(session, documents)
    scene = next((e for e in scene_catalog(documents) if e["scene_id"] == scene_id), None)
    if scene is None or scene["quest_stage"] != stage:
        raise StudioQuestError("selected scene does not own quest stage")
    intent = inspect_object_intent(session, documents, scene_id=scene_id,
                                   object_id=object_id, authorized=True)
    nxt = step_quest(session, documents, stage=stage, alternative=alternative,
                     authorized=True)
    # Social decisions are a separate authored vocabulary; a quest choice
    # must not automatically grant an unrelated reputation effect.
    social = replay_factions(documents, list(social_history), authorized=True)
    return StoryTurn(session.digest, nxt, intent, social, quest_progress(nxt, documents))


def verify_story_turn(documents: Mapping[str, Any], previous: QuestSession, turn: StoryTurn,
                      *, scene_id: str, object_id: str, stage: str, alternative: str,
                      social_history: Sequence[str] = ()) -> None:
    if not isinstance(turn, StoryTurn):
        raise StudioQuestError("invalid story turn receipt")
    expected = apply_story_turn(documents, previous, scene_id=scene_id,
                                object_id=object_id, stage=stage,
                                alternative=alternative, social_history=social_history,
                                authorized=True)
    if turn != expected:
        raise StudioQuestError("story turn does not reproduce source replay")
