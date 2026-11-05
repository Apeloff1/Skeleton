"""CAS-protected, append-only salvage replay journal with historical forks."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _integer, _keys, canonical, digest
from .harbor_crafting_salvage import (
    MAX_BOARD_BYTES, MAX_REPORT_BYTES, build_salvage, verify_salvage,
    validate_salvage_board,
)

SCHEMA = "skeleton.game.harbor.salvage-journal.v1"
MAX_JOURNAL_BYTES = MAX_REPORT_BYTES * 2
MAX_REVISIONS = 48
KEYS = {"schema", "source", "board", "revisions", "tip", "journal_digest"}
REVISION_KEYS = {"sequence", "actions", "report_digest", "previous", "digest"}


def _seal(journal: dict[str, Any]) -> dict[str, Any]:
    journal["journal_digest"] = digest({k: v for k, v in journal.items()
                                         if k != "journal_digest"})
    if len(canonical(journal)) > MAX_JOURNAL_BYTES:
        raise HarborError("salvage journal exceeds byte budget")
    return journal


def create_salvage_journal(source: Any, board: Any) -> dict[str, Any]:
    authored = validate_salvage_board(board, source)
    initial = build_salvage(source, authored, [])
    return _seal({"schema": SCHEMA, "source": initial["source"],
                  "board": authored, "revisions": [], "tip": initial["report_digest"]})


def verify_salvage_journal(journal: Any) -> dict[str, Any]:
    _keys(journal, KEYS, "salvage journal")
    if journal["schema"] != SCHEMA or len(canonical(journal)) > MAX_JOURNAL_BYTES:
        raise HarborError("invalid salvage journal schema or size")
    if journal["journal_digest"] != digest({k: v for k, v in journal.items()
                                             if k != "journal_digest"}):
        raise HarborError("salvage journal digest mismatch")
    current = build_salvage(journal["source"], journal["board"], [])
    tip = current["report_digest"]
    actions: list[dict[str, str]] = []
    if not isinstance(journal["revisions"], list) or len(journal["revisions"]) > MAX_REVISIONS:
        raise HarborError("salvage revision budget exceeded")
    for index, revision in enumerate(journal["revisions"]):
        _keys(revision, REVISION_KEYS, "salvage journal revision")
        if revision["sequence"] != index or revision["previous"] != tip:
            raise HarborError("salvage journal history discontinuity")
        if not isinstance(revision["actions"], list) or not revision["actions"]:
            raise HarborError("empty salvage journal append")
        if revision["digest"] != digest({k: v for k, v in revision.items()
                                          if k != "digest"}):
            raise HarborError("salvage journal revision digest mismatch")
        actions += revision["actions"]
        current = build_salvage(journal["source"], journal["board"], actions)
        if current["report_digest"] != revision["report_digest"]:
            raise HarborError("salvage journal replay mismatch")
        tip = current["report_digest"]
    if tip != journal["tip"]:
        raise HarborError("salvage journal tip mismatch")
    verify_salvage(current)
    return {"report": current, "tip": tip, "revision_count": len(journal["revisions"])}


def append_salvage_journal(journal: Any, actions: Any, *, expected_tip: str) -> dict[str, Any]:
    checked = verify_salvage_journal(journal)
    if type(expected_tip) is not str or expected_tip != checked["tip"]:
        raise HarborError("stale salvage journal CAS lease")
    if len(journal["revisions"]) >= MAX_REVISIONS:
        raise HarborError("salvage journal revision limit reached")
    if not isinstance(actions, list) or not actions:
        raise HarborError("salvage journal requires nonempty action batch")
    old_actions = checked["report"]["actions"]
    report = build_salvage(journal["source"], journal["board"], old_actions + actions)
    entry = {"sequence": len(journal["revisions"]), "actions": deepcopy(actions),
             "previous": checked["tip"], "report_digest": report["report_digest"]}
    entry["digest"] = digest(entry)
    result = deepcopy(journal)
    result["revisions"].append(entry)
    result["tip"] = report["report_digest"]
    _seal(result)
    verify_salvage_journal(result)
    return result


def salvage_journal_at(journal: Any, index: int) -> dict[str, Any]:
    checked = verify_salvage_journal(journal)
    _integer(index, 0, checked["revision_count"], "salvage journal index")
    actions: list[dict[str, str]] = []
    for entry in journal["revisions"][:index]:
        actions.extend(entry["actions"])
    return build_salvage(journal["source"], journal["board"], actions)


def fork_salvage_journal(journal: Any, index: int) -> dict[str, Any]:
    checked = verify_salvage_journal(journal)
    _integer(index, 0, checked["revision_count"], "salvage fork index")
    fork = deepcopy(journal)
    fork["revisions"] = fork["revisions"][:index]
    fork["tip"] = salvage_journal_at(journal, index)["report_digest"]
    _seal(fork)
    verify_salvage_journal(fork)
    return fork


def fast_forward_salvage_journal(ancestor: Any, descendant: Any) -> dict[str, Any]:
    verify_salvage_journal(ancestor)
    verify_salvage_journal(descendant)
    if (ancestor["source"] != descendant["source"]
            or ancestor["board"] != descendant["board"]
            or ancestor["revisions"] != descendant["revisions"][:len(ancestor["revisions"]) ]):
        raise HarborError("salvage journal history conflict")
    return deepcopy(descendant)
