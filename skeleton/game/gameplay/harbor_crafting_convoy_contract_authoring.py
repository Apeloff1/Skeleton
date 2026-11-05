"""Transactional convoy quest authoring with full replayed consequence preview."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _keys, canonical, digest
from .harbor_crafting_convoy_contracts import (
    MAX_REPORT_BYTES, build_convoy_contract_report,
    validate_convoy_contracts, verify_convoy_contract_report,
)

SCHEMA = "skeleton.game.harbor.convoy-contract-revision.v1"
MAX_REVISION_BYTES = MAX_REPORT_BYTES * 2
FIELDS = {
    "schema", "convoy", "before", "after", "edits", "preview",
    "result", "before_digest", "after_digest", "revision_digest",
}
EDITABLE = {"points", "required", "target", "requires"}


def edit_convoy_contracts(convoy: Any, board: Any, edits: Any, *,
                          expected_board_digest: str,
                          preview_report: Any = None) -> dict[str, Any]:
    original = validate_convoy_contracts(board, convoy)
    if type(expected_board_digest) is not str or expected_board_digest != digest(original):
        raise HarborError("stale convoy contract authoring lease")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 24:
        raise HarborError("invalid convoy contract edit count")
    updated = deepcopy(original)
    for edit in edits:
        _keys(edit, {"id", "field", "value"}, "convoy contract edit")
        name = _identifier(edit["id"], "convoy contract edit id")
        if type(edit["field"]) is not str or edit["field"] not in EDITABLE:
            raise HarborError("unsupported convoy contract edit field")
        contract = next((c for c in updated["contracts"] if c["id"] == name), None)
        if contract is None:
            raise HarborError("unknown convoy contract edit id")
        contract[edit["field"]] = deepcopy(edit["value"])
    validate_convoy_contracts(updated, convoy)
    preview = None
    result = None
    if preview_report is not None:
        verify_convoy_contract_report(preview_report)
        if preview_report["convoy"] != convoy or preview_report["board"] != original:
            raise HarborError("convoy contract preview source mismatch")
        preview = deepcopy(preview_report)
        result = build_convoy_contract_report(
            convoy, updated, choice=preview["choice"],
        )
    revision = {
        "schema": SCHEMA, "convoy": deepcopy(convoy),
        "before": original, "after": updated, "edits": deepcopy(edits),
        "preview": preview, "result": result,
        "before_digest": digest(original), "after_digest": digest(updated),
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("convoy contract revision exceeds byte budget")
    return revision


def verify_convoy_contract_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "convoy contract revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized convoy contract revision")
    if revision["revision_digest"] != digest({
        k: v for k, v in revision.items() if k != "revision_digest"
    }):
        raise HarborError("convoy contract revision digest mismatch")
    rebuilt = edit_convoy_contracts(
        revision["convoy"], revision["before"], revision["edits"],
        expected_board_digest=revision["before_digest"],
        preview_report=revision["preview"],
    )
    if rebuilt != revision:
        raise HarborError("convoy contract authoring replay mismatch")
    return {
        "verified": True, "after_digest": rebuilt["after_digest"],
        "preview_complete": (
            None if rebuilt["result"] is None else rebuilt["result"]["complete"]
        ),
    }
