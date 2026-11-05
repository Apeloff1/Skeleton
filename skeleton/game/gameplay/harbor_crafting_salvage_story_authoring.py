"""CAS-guarded original story authoring with earned replay preview."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_salvage_quest_events import (
    MAX_BOARD_BYTES, build_salvage_story, validate_story_board,
)

SCHEMA = "skeleton.game.harbor.salvage-story-revision.v1"
MAX_BYTES = 262144
MAX_EDITS = 24
FIELDS = {"schema", "report", "before", "edits", "after", "before_digest",
          "after_digest", "preview_before", "preview_after", "revision_digest"}


def edit_salvage_story(report: Any, board: Any, edits: Any, *,
                       expected_board_digest: str,
                       preview: bool = False) -> dict[str, Any]:
    before = validate_story_board(board, report)
    if type(expected_board_digest) is not str or digest(before) != expected_board_digest:
        raise HarborError("stale salvage story board CAS lease")
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
        raise HarborError("salvage story edit budget exceeded")
    after = deepcopy(before)
    for edit in edits:
        _keys(edit, {"op", "id", "field", "value"}, "salvage story edit")
        if edit["op"] != "set-quest":
            raise HarborError("unsupported salvage story edit")
        name = _identifier(edit["id"], "salvage story quest id")
        quest = next((q for q in after["quests"] if q["id"] == name), None)
        if quest is None or edit["field"] not in {"kind", "target", "requires", "reward", "story"}:
            raise HarborError("unknown salvage story quest field")
        quest[edit["field"]] = deepcopy(edit["value"])
        validate_story_board(after, report)
    preview_before = None
    preview_after = None
    if type(preview) is not bool:
        raise HarborError("invalid salvage story preview flag")
    if preview:
        preview_before = build_salvage_story(report, before)["state"]
        preview_after = build_salvage_story(report, after)["state"]
    revision = {"schema": SCHEMA, "report": deepcopy(report), "before": before,
                "edits": deepcopy(edits), "after": after,
                "before_digest": digest(before), "after_digest": digest(after),
                "preview_before": preview_before, "preview_after": preview_after}
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_BYTES:
        raise HarborError("salvage story revision oversized")
    return revision


def verify_salvage_story_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "salvage story revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_BYTES:
        raise HarborError("unsupported or oversized salvage story revision")
    if revision["revision_digest"] != digest({k: v for k, v in revision.items()
                                               if k != "revision_digest"}):
        raise HarborError("salvage story revision digest mismatch")
    rebuilt = edit_salvage_story(revision["report"], revision["before"],
                                 revision["edits"],
                                 expected_board_digest=revision["before_digest"],
                                 preview=revision["preview_before"] is not None)
    if rebuilt != revision:
        raise HarborError("salvage story authoring replay mismatch")
    return deepcopy(revision["after"])
