"""Quest progress as a :class:`GameSavePlane` section.

The section is a *view*, not an authority: it is pinned to the Director
world digest and the Director state digest it was derived from, which are
the same values :mod:`quest_campaign_save` writes as
``director_world_digest`` and ``final_state_sha256``.  On restore, pass the
state replayed by ``read_campaign_save`` (or any verified Director state) and
the section is rejected unless the digests match.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from skeleton.ai.game_builder.quest_fail_states import QuestFailure
from skeleton.ai.game_builder.quest_scene_engine import DirectorState, DirectorWorld
from skeleton.frontier.progression.quests import ObjectiveProgress, QuestProgressState
from skeleton.kernel.game_save_plane import GameSavePlane

SECTION = "quest_progress"
SCHEMA = "skeleton.game_builder.quest_progress_section.v1"


class QuestProgressSaveError(ValueError):
    pass


def quest_section(world: DirectorWorld, state: DirectorState,
                  quests: Sequence[QuestProgressState], *,
                  failures: Sequence[QuestFailure] = (),
                  campaign_receipt_sha256: str | None = None) -> dict[str, Any]:
    if state.world_digest != world.digest:
        raise QuestProgressSaveError("director state belongs to another world")
    return {
        "schema": SCHEMA,
        "project": world.project_id,
        "director_world_digest": world.digest,
        "final_state_sha256": state.digest,
        "campaign_receipt_sha256": campaign_receipt_sha256,
        "quests": {q.quest_id: q.as_dict() for q in sorted(quests, key=lambda q: q.quest_id)},
        "failures": [{"quest": f.quest, "kind": f.kind, "reason": f.reason} for f in failures],
    }


def save_quest_progress(plane: GameSavePlane, slot: str, sequence: int,
                        section: Mapping[str, Any], *,
                        other_sections: Mapping[str, Mapping[str, Any]] | None = None,
                        receipts: Any = None):
    sections = dict(other_sections or {})
    if SECTION in sections:
        raise QuestProgressSaveError(f"{SECTION!r} supplied twice")
    sections[SECTION] = dict(section)
    return plane.save(slot, sequence, sections, receipts=receipts)


def _progress(raw: Mapping[str, Any]) -> QuestProgressState:
    objectives = {k: ObjectiveProgress(int(v["current"]), int(v["target"]), bool(v["completed"]))
                  for k, v in raw["objectives_progress"].items()}
    return QuestProgressState(str(raw["quest_id"]), str(raw["status"]), objectives)


def restore_quest_progress(plane: GameSavePlane, slot: str, world: DirectorWorld, *,
                           verified_state: DirectorState | None = None,
                           campaign_receipt_sha256: str | None = None,
                           sequence: int | None = None) -> dict[str, QuestProgressState]:
    sections, _ = plane.restore(slot, sequence=sequence)
    section = sections.get(SECTION)
    if section is None:
        raise QuestProgressSaveError("save has no quest progress section")
    if section.get("schema") != SCHEMA:
        raise QuestProgressSaveError("unknown quest progress schema")
    if section.get("director_world_digest") != world.digest:
        raise QuestProgressSaveError("quest progress belongs to another world")
    if verified_state is not None and section.get("final_state_sha256") != verified_state.digest:
        raise QuestProgressSaveError("quest progress does not match the verified director state")
    if (campaign_receipt_sha256 is not None
            and section.get("campaign_receipt_sha256") != campaign_receipt_sha256):
        raise QuestProgressSaveError("quest progress does not match the campaign save receipt")
    return {qid: _progress(raw) for qid, raw in section["quests"].items()}


__all__ = ["SCHEMA", "SECTION", "QuestProgressSaveError", "quest_section",
           "restore_quest_progress", "save_quest_progress"]
