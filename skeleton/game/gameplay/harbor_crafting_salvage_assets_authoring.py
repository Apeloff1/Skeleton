"""Transactional glyph and original text-label authoring with replay preview."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _keys, canonical, digest
from .harbor_crafting_salvage_assets import validate_salvage_assets
from .harbor_crafting_salvage_map import render_salvage_map

SCHEMA = "skeleton.game.harbor.salvage-asset-revision.v1"
MAX_BYTES = 262144
MAX_EDITS = 32
FIELDS = {"schema", "source", "board", "before", "edits", "after",
          "before_digest", "after_digest", "preview_report", "preview_before",
          "preview_after", "revision_digest"}


def edit_salvage_assets(source: Any, board: Any, assets: Any, edits: Any, *,
                        expected_assets_digest: str,
                        preview_report: Any = None) -> dict[str, Any]:
    before = validate_salvage_assets(assets, source, board)
    if type(expected_assets_digest) is not str or digest(before) != expected_assets_digest:
        raise HarborError("stale salvage assets CAS lease")
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
        raise HarborError("salvage assets edit budget exceeded")
    after = deepcopy(before)
    for edit in edits:
        _keys(edit, {"op", "id", "value"}, "salvage assets edit")
        if edit["op"] == "set-glyph" and edit["id"] in after["glyphs"]:
            after["glyphs"][edit["id"]] = edit["value"]
        elif edit["op"] == "set-label" and edit["id"] in after["labels"]:
            after["labels"][edit["id"]] = edit["value"]
        else:
            raise HarborError("unknown salvage asset edit")
        validate_salvage_assets(after, source, board)
    before_preview = None
    after_preview = None
    if preview_report is not None:
        before_preview = render_salvage_map(preview_report, before)["frame"]
        after_preview = render_salvage_map(preview_report, after)["frame"]
    revision = {"schema": SCHEMA, "source": deepcopy(source), "board": deepcopy(board),
                "before": before, "edits": deepcopy(edits), "after": after,
                "before_digest": digest(before), "after_digest": digest(after),
                "preview_report": deepcopy(preview_report),
                "preview_before": before_preview, "preview_after": after_preview}
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_BYTES:
        raise HarborError("salvage assets revision oversized")
    return revision


def verify_salvage_assets_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "salvage assets revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_BYTES:
        raise HarborError("invalid salvage assets revision")
    if revision["revision_digest"] != digest({k: v for k, v in revision.items()
                                               if k != "revision_digest"}):
        raise HarborError("salvage assets revision digest mismatch")
    rebuilt = edit_salvage_assets(
        revision["source"], revision["board"], revision["before"],
        revision["edits"], expected_assets_digest=revision["before_digest"],
        preview_report=revision["preview_report"],
    )
    if rebuilt != revision:
        raise HarborError("salvage assets authoring replay mismatch")
    return deepcopy(revision["after"])
