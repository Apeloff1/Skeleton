"""Transactional championship choice authoring with replay-checked previews."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_salvage_season_choices import (
    MAX_BOARD_BYTES, build_season_choice, validate_season_choices,
)

SCHEMA = "skeleton.game.harbor.salvage-season-choice-revision.v1"
MAX_REVISION_BYTES = 262144
MAX_EDITS = 24
FIELDS = {"schema", "save", "before", "edits", "after", "before_digest",
          "after_digest", "preview_choice", "preview_before",
          "preview_after", "revision_digest"}


def edit_season_choices(save: Any, board: Any, edits: Any, *,
                        expected_board_digest: str,
                        preview_choice: str | None = None) -> dict[str, Any]:
    before = validate_season_choices(board, save)
    if type(expected_board_digest) is not str or digest(before) != expected_board_digest:
        raise HarborError("stale salvage choice board CAS lease")
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
        raise HarborError("salvage choice edit budget exceeded")
    after = deepcopy(before)
    for edit in edits:
        _keys(edit, {"op", "id", "field", "value"}, "salvage choice edit")
        if edit["op"] != "set-choice":
            raise HarborError("unsupported salvage choice edit")
        name = _identifier(edit["id"], "salvage choice id")
        choice = next((c for c in after["choices"] if c["id"] == name), None)
        if choice is None or edit["field"] not in {"min_score", "cost", "reputation", "epilogue"}:
            raise HarborError("unknown salvage choice field")
        choice[edit["field"]] = deepcopy(edit["value"])
        validate_season_choices(after, save)
    preview_before = None
    preview_after = None
    if preview_choice is not None:
        preview_before = build_season_choice(save, before, preview_choice)["outcome"]
        preview_after = build_season_choice(save, after, preview_choice)["outcome"]
    revision = {"schema": SCHEMA, "save": deepcopy(save), "before": before,
                "edits": deepcopy(edits), "after": after,
                "before_digest": digest(before), "after_digest": digest(after),
                "preview_choice": preview_choice, "preview_before": preview_before,
                "preview_after": preview_after}
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("salvage choice revision oversized")
    return revision


def verify_season_choice_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "salvage choice revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized salvage choice revision")
    if revision["revision_digest"] != digest({k: v for k, v in revision.items()
                                               if k != "revision_digest"}):
        raise HarborError("salvage choice revision digest mismatch")
    rebuilt = edit_season_choices(revision["save"], revision["before"], revision["edits"],
                                  expected_board_digest=revision["before_digest"],
                                  preview_choice=revision["preview_choice"])
    if rebuilt != revision:
        raise HarborError("salvage choice revision replay mismatch")
    return deepcopy(revision["after"])
