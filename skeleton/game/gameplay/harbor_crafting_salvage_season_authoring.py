"""CAS-guarded championship authoring and source-replayed preview validation."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_salvage_authoring import edit_salvage
from .harbor_crafting_salvage_season import (
    MAX_SEASON_BOARD_BYTES, validate_salvage_season, verify_salvage_season,
    start_salvage_season, append_salvage_round,
)

SCHEMA = "skeleton.game.harbor.salvage-season-revision.v1"
MAX_REVISION_BYTES = MAX_SEASON_BOARD_BYTES * 4
MAX_EDITS = 24
FIELDS = {"schema", "source", "before", "edits", "after", "before_digest",
          "after_digest", "preview_round_actions", "preview_before",
          "preview_after", "revision_digest"}


def edit_season(source: Any, board: Any, edits: Any, *,
                expected_board_digest: str, preview_round_actions: Any = None) -> dict[str, Any]:
    before = validate_salvage_season(board, source)
    if type(expected_board_digest) is not str or expected_board_digest != digest(before):
        raise HarborError("stale salvage season board CAS lease")
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
        raise HarborError("salvage season edit budget exceeded")
    after = deepcopy(before)
    for edit in edits:
        if not isinstance(edit, dict) or type(edit.get("op")) is not str:
            raise HarborError("invalid salvage season edit")
        if edit["op"] == "set-round":
            _keys(edit, {"op", "id", "field", "value"}, "salvage season round edit")
            name = _identifier(edit["id"], "salvage round id")
            item = next((r for r in after["rounds"] if r["id"] == name), None)
            if item is None or edit["field"] not in {"points", "min_reward", "min_hull"}:
                raise HarborError("unknown salvage round or field")
            item[edit["field"]] = edit["value"]
        elif edit["op"] == "edit-board":
            _keys(edit, {"op", "id", "edits"}, "salvage season nested edit")
            name = _identifier(edit["id"], "salvage round id")
            item = next((r for r in after["rounds"] if r["id"] == name), None)
            if item is None:
                raise HarborError("unknown salvage round")
            revision = edit_salvage(source, item["board"], edit["edits"],
                                    expected_board_digest=digest(item["board"]))
            item["board"] = revision["after"]
        else:
            raise HarborError("unsupported salvage season edit")
        validate_salvage_season(after, source)
    preview_before = None
    preview_after = None
    if preview_round_actions is not None:
        if not isinstance(preview_round_actions, list):
            raise HarborError("invalid salvage season preview")
        def replay(candidate):
            save = start_salvage_season(source, candidate)
            for actions in preview_round_actions:
                save = append_salvage_round(save, actions, expected_tip=save["tip"])
            return verify_salvage_season(save)
        preview_before = replay(before)
        preview_after = replay(after)
    revision = {"schema": SCHEMA, "source": deepcopy(source), "before": before,
                "edits": deepcopy(edits), "after": after,
                "before_digest": digest(before), "after_digest": digest(after),
                "preview_round_actions": deepcopy(preview_round_actions),
                "preview_before": preview_before, "preview_after": preview_after}
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("salvage season revision oversized")
    return revision


def verify_season_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "salvage season revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("invalid salvage season revision")
    if revision["revision_digest"] != digest({k: v for k, v in revision.items()
                                               if k != "revision_digest"}):
        raise HarborError("salvage season revision digest mismatch")
    rebuilt = edit_season(revision["source"], revision["before"], revision["edits"],
                          expected_board_digest=revision["before_digest"],
                          preview_round_actions=revision["preview_round_actions"])
    if rebuilt != revision:
        raise HarborError("salvage season revision replay mismatch")
    return deepcopy(revision["after"])
