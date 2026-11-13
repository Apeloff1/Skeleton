"""Transactional source-bound salvage board editor with replay-safe previews."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest, validate_source
from .harbor_crafting_salvage import (
    MAX_BOARD_BYTES, build_salvage, validate_salvage_board,
)

REVISION_SCHEMA = "skeleton.game.harbor.salvage-revision.v1"
MAX_REVISION_BYTES = 262144
MAX_EDITS = 32
REVISION_KEYS = {"schema", "source", "before", "edits", "after", "before_digest",
                 "after_digest", "preview_actions", "preview_before",
                 "preview_after", "revision_digest"}


def _apply(board: dict[str, Any], edit: Any) -> None:
    if not isinstance(edit, dict) or type(edit.get("op")) is not str:
        raise HarborError("invalid salvage edit")
    op = edit["op"]
    if op == "add-site":
        _keys(edit, {"op", "site"}, "add salvage site")
        board["sites"].append(deepcopy(edit["site"]))
    elif op == "remove-site":
        _keys(edit, {"op", "id"}, "remove salvage site")
        name = _identifier(edit["id"], "site id")
        if not any(site["id"] == name for site in board["sites"]):
            raise HarborError("cannot remove missing salvage site")
        board["sites"] = [s for s in board["sites"] if s["id"] != name]
    elif op in {"set-site", "move-site"}:
        required = {"op", "id", "field", "value"} if op == "set-site" else {"op", "id", "at"}
        _keys(edit, required, "edit salvage site")
        name = _identifier(edit["id"], "site id")
        site = next((s for s in board["sites"] if s["id"] == name), None)
        if site is None:
            raise HarborError("unknown salvage site")
        if op == "set-site":
            if edit["field"] not in {"weight", "reward"}:
                raise HarborError("unsupported salvage site field")
            site[edit["field"]] = edit["value"]
        else:
            site["at"] = deepcopy(edit["at"])
    elif op == "set-rule":
        _keys(edit, {"op", "field", "value"}, "edit salvage rule")
        if edit["field"] not in {"hull", "cargo_capacity", "tide_period", "max_turns", "tool"}:
            raise HarborError("unsupported salvage rule field")
        board[edit["field"]] = edit["value"]
    else:
        raise HarborError("unsupported salvage edit operation")


def edit_salvage(source: Any, board: Any, edits: Any, *, expected_board_digest: str,
                 preview_actions: Any = None) -> dict[str, Any]:
    world = validate_source(source)
    before = validate_salvage_board(board, world)
    if type(expected_board_digest) is not str or digest(before) != expected_board_digest:
        raise HarborError("stale salvage board CAS lease")
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
        raise HarborError("salvage edit budget exceeded")
    after = deepcopy(before)
    for edit in edits:
        _apply(after, edit)
        validate_salvage_board(after, world)
    if len(canonical(after)) > MAX_BOARD_BYTES:
        raise HarborError("edited salvage board oversized")
    before_preview = None
    after_preview = None
    if preview_actions is not None:
        before_preview = build_salvage(world, before, preview_actions)["report_digest"]
        after_preview = build_salvage(world, after, preview_actions)["report_digest"]
    revision = {
        "schema": REVISION_SCHEMA, "source": world, "before": before,
        "edits": deepcopy(edits), "after": after, "before_digest": digest(before),
        "after_digest": digest(after), "preview_actions": deepcopy(preview_actions),
        "preview_before": before_preview, "preview_after": after_preview,
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("salvage revision exceeds byte budget")
    return revision


def verify_salvage_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, REVISION_KEYS, "salvage revision")
    if revision["schema"] != REVISION_SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("invalid salvage revision schema or size")
    if revision["revision_digest"] != digest({k: v for k, v in revision.items()
                                               if k != "revision_digest"}):
        raise HarborError("salvage revision digest mismatch")
    rebuilt = edit_salvage(
        revision["source"], revision["before"], revision["edits"],
        expected_board_digest=revision["before_digest"],
        preview_actions=revision["preview_actions"],
    )
    if rebuilt != revision:
        raise HarborError("salvage revision replay mismatch")
    return deepcopy(revision["after"])
