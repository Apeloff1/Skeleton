"""CAS-protected cross-round quest editor with independent replayed previews."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _integer, _keys, canonical, digest
from .harbor_crafting_convoy_league_quests import (
    MAX_BOARD_BYTES, MAX_REPORT_BYTES, build_league_quest_report,
    validate_league_quests, verify_league_quest_report,
)
from .harbor_crafting_convoy_league import verify_league

SCHEMA = "skeleton.game.harbor.convoy-league-quest-revision.v1"
MAX_REVISION_BYTES = MAX_BOARD_BYTES * 2 + MAX_REPORT_BYTES * 2 + 8192
FIELDS = {
    "schema", "save", "before", "edits", "after",
    "before_preview", "after_preview", "revision_digest",
}
EDIT_FIELDS = {"kind", "target", "value"}
KINDS = {"points", "required", "minimum-points"}


def edit_league_quests(save: Any, board: Any, edits: Any, *,
                       expected_digest: str, preview: bool = False) -> dict[str, Any]:
    verify_league(save)
    before = validate_league_quests(board, save)
    if type(expected_digest) is not str or digest(before) != expected_digest:
        raise HarborError("stale league quest board lease")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 16:
        raise HarborError("invalid league quest edit count")
    after = deepcopy(before)
    seen: set[tuple[str, str]] = set()
    for edit in edits:
        _keys(edit, EDIT_FIELDS, "league quest edit")
        kind, target, value = edit["kind"], edit["target"], edit["value"]
        if type(kind) is not str or kind not in KINDS or type(target) is not str:
            raise HarborError("unsupported league quest edit")
        if (kind, target) in seen:
            raise HarborError("duplicate league quest edit")
        seen.add((kind, target))
        if kind == "minimum-points":
            if target != "board":
                raise HarborError("league quest board edit target mismatch")
            _integer(value, 1, 2400, "league quest minimum points")
            after["minimum_points"] = value
        else:
            objective = next(
                (item for item in after["objectives"] if item["id"] == target), None,
            )
            if objective is None:
                raise HarborError("unknown league quest edit target")
            if kind == "points":
                _integer(value, 0, 100, "league quest points")
            elif type(value) is not bool:
                raise HarborError("invalid league quest required flag")
            objective[kind] = value
    validate_league_quests(after, save)
    before_preview = build_league_quest_report(save, before) if preview else None
    after_preview = build_league_quest_report(save, after) if preview else None
    result = {
        "schema": SCHEMA, "save": deepcopy(save), "before": before,
        "edits": deepcopy(edits), "after": after,
        "before_preview": before_preview, "after_preview": after_preview,
    }
    result["revision_digest"] = digest(result)
    if len(canonical(result)) > MAX_REVISION_BYTES:
        raise HarborError("league quest revision exceeds byte budget")
    return result


def verify_league_quest_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "league quest revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized league quest revision")
    if revision["revision_digest"] != digest({
        key: value for key, value in revision.items() if key != "revision_digest"
    }):
        raise HarborError("league quest revision digest mismatch")
    rebuilt = edit_league_quests(
        revision["save"], revision["before"], revision["edits"],
        expected_digest=digest(revision["before"]),
        preview=revision["before_preview"] is not None,
    )
    if rebuilt != revision:
        raise HarborError("league quest revision replay mismatch")
    return {
        "verified": True, "board_digest": digest(rebuilt["after"]),
        "preview_complete": (
            rebuilt["after_preview"]["complete"] if rebuilt["after_preview"] is not None else None
        ),
    }
