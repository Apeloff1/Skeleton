"""Quest progress as a :class:`GameSavePlane` section.

The section is a *view*, not an authority: it is pinned to the Director
world digest and the Director state digest it was derived from, which are
the same values :mod:`quest_campaign_save` writes as
``director_world_digest`` and ``final_state_sha256``.  On restore, pass the
state replayed by ``read_campaign_save`` (or any verified Director state) and
the section is rejected unless the digests match.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Mapping, Sequence

from skeleton.ai.game_builder.quest_fail_states import QuestFailure
from skeleton.ai.game_builder.quest_scene_engine import DirectorState, DirectorWorld
from skeleton.frontier.progression.quests import ObjectiveProgress, QuestProgressState
from skeleton.kernel.game_save_plane import GameSavePlane

SECTION = "quest_progress"
SCHEMA = "skeleton.game_builder.quest_progress_section.v1"
FAIL_KINDS = frozenset({"turn_limit", "flag", "escort_lost"})


class QuestProgressSaveError(ValueError):
    pass


def _safe_text(value: object, maximum: int) -> bool:
    return (type(value) is str and 1 <= len(value) <= maximum
            and not any(unicodedata.category(ch) in {"Cc", "Cf", "Zl", "Zp"}
                        for ch in value))


def _validate_failure_docs(failures: object) -> None:
    if type(failures) is not list or len(failures) > 4096:
        raise QuestProgressSaveError("invalid quest failure collection")
    seen: set[tuple[str, str]] = set()
    for failure in failures:
        if (type(failure) is not dict or set(failure) != {"quest", "kind", "reason"}
                or not _safe_text(failure["quest"], 128)
                or failure["kind"] not in FAIL_KINDS
                or not _safe_text(failure["reason"], 512)):
            raise QuestProgressSaveError("invalid quest failure evidence")
        identity = (failure["quest"], failure["kind"])
        if identity in seen:
            raise QuestProgressSaveError("duplicate quest failure evidence")
        seen.add(identity)


def _validate_campaign_receipt(value: str | None) -> None:
    if value is not None and (
        type(value) is not str or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise QuestProgressSaveError("invalid campaign receipt digest")


def quest_section(world: DirectorWorld, state: DirectorState,
                  quests: Sequence[QuestProgressState], *,
                  failures: Sequence[QuestFailure] = (),
                  campaign_receipt_sha256: str | None = None) -> dict[str, Any]:
    if state.world_digest != world.digest:
        raise QuestProgressSaveError("director state belongs to another world")
    _validate_campaign_receipt(campaign_receipt_sha256)
    if len(quests) > 4096 or len(failures) > 4096:
        raise QuestProgressSaveError("quest section exceeds bounded collection size")
    # Reject forged objects before reading their attributes. Otherwise an
    # untrusted section producer can escape the typed fail-closed boundary.
    if any(type(q) is not QuestProgressState for q in quests):
        raise QuestProgressSaveError("invalid quest progress object")
    quest_ids = [q.quest_id for q in quests]
    if any(not _safe_text(qid, 128) for qid in quest_ids):
        raise QuestProgressSaveError("invalid quest identity")
    if len(set(quest_ids)) != len(quest_ids):
        raise QuestProgressSaveError("duplicate quest identity in section")
    for quest in quests:
        if type(quest) is not QuestProgressState:
            raise QuestProgressSaveError("invalid quest progress object")
        _progress(quest.as_dict())
    if any(type(failure) is not QuestFailure for failure in failures):
        raise QuestProgressSaveError("invalid quest failure object")
    failure_docs = [{"quest": f.quest, "kind": f.kind, "reason": f.reason}
                    for f in failures]
    _validate_failure_docs(failure_docs)
    return {
        "schema": SCHEMA,
        "project": world.project_id,
        "director_world_digest": world.digest,
        "final_state_sha256": state.digest,
        "campaign_receipt_sha256": campaign_receipt_sha256,
        "quests": {q.quest_id: q.as_dict() for q in sorted(quests, key=lambda q: q.quest_id)},
        "failures": failure_docs,
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
    if not isinstance(raw, Mapping) or set(raw) != {"quest_id", "status", "objectives_progress"}:
        raise QuestProgressSaveError("invalid quest progress shape")
    quest_id, status = raw["quest_id"], raw["status"]
    if not _safe_text(quest_id, 128) or status not in ("active", "completed", "failed"):
        raise QuestProgressSaveError("invalid quest progress identity or status")
    progress = raw["objectives_progress"]
    if not isinstance(progress, Mapping) or len(progress) > 1024:
        raise QuestProgressSaveError("invalid objective progress collection")
    objectives: dict[str, ObjectiveProgress] = {}
    for key, value in progress.items():
        if (type(key) is not str or not key or len(key) > 6 or not key.isascii()
                or not key.isdecimal() or (len(key) > 1 and key[0] == "0")
                or not isinstance(value, Mapping)):
            raise QuestProgressSaveError("invalid objective progress key")
        if set(value) != {"current", "target", "completed"}:
            raise QuestProgressSaveError("invalid objective progress shape")
        current, target, completed = value["current"], value["target"], value["completed"]
        if (type(current) is not int or type(target) is not int or type(completed) is not bool
                or target < 1 or current < 0 or current > target or completed != (current == target)):
            raise QuestProgressSaveError("invalid objective progress counters")
        objectives[key] = ObjectiveProgress(current, target, completed)
    if status != "failed" and (status == "completed") != all(p.completed for p in objectives.values()):
        raise QuestProgressSaveError("quest status disagrees with objective completion")
    return QuestProgressState(quest_id, status, objectives)


def restore_quest_progress(plane: GameSavePlane, slot: str, world: DirectorWorld, *,
                           verified_state: DirectorState | None = None,
                           campaign_receipt_sha256: str | None = None,
                           sequence: int | None = None) -> dict[str, QuestProgressState]:
    # A save section is only a view. Require independently replayed Director
    # state or a verified campaign receipt before accepting stored progress.
    if verified_state is None and campaign_receipt_sha256 is None:
        raise QuestProgressSaveError("quest restore requires verified Director state or campaign receipt")
    if verified_state is not None and (
        not isinstance(verified_state, DirectorState)
        or verified_state.world_digest != world.digest
    ):
        raise QuestProgressSaveError("verified director state belongs to another world")
    _validate_campaign_receipt(campaign_receipt_sha256)
    sections, _ = plane.restore(slot, sequence=sequence)
    section = sections.get(SECTION)
    if section is None:
        raise QuestProgressSaveError("save has no quest progress section")
    if not isinstance(section, Mapping) or set(section) != {
        "schema", "project", "director_world_digest", "final_state_sha256",
        "campaign_receipt_sha256", "quests", "failures",
    }:
        raise QuestProgressSaveError("invalid quest progress section shape")
    _validate_failure_docs(section["failures"])
    if section.get("schema") != SCHEMA:
        raise QuestProgressSaveError("unknown quest progress schema")
    if section.get("project") != world.project_id:
        raise QuestProgressSaveError("quest progress belongs to another project")
    if section.get("director_world_digest") != world.digest:
        raise QuestProgressSaveError("quest progress belongs to another world")
    if verified_state is not None and section.get("final_state_sha256") != verified_state.digest:
        raise QuestProgressSaveError("quest progress does not match the verified director state")
    if (campaign_receipt_sha256 is not None
            and section.get("campaign_receipt_sha256") != campaign_receipt_sha256):
        raise QuestProgressSaveError("quest progress does not match the campaign save receipt")
    quests = section.get("quests")
    if not isinstance(quests, Mapping) or len(quests) > 4096:
        raise QuestProgressSaveError("invalid quest progress collection")
    restored = {qid: _progress(raw) for qid, raw in quests.items()}
    if any(type(qid) is not str or qid != state.quest_id for qid, state in restored.items()):
        raise QuestProgressSaveError("quest progress key does not match quest identity")
    return restored


__all__ = ["SCHEMA", "SECTION", "QuestProgressSaveError", "quest_section",
           "restore_quest_progress", "save_quest_progress"]
