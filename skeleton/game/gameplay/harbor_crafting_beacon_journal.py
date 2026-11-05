"""Append-only CAS beacon rescue save journal with deterministic historical replay."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _integer, _keys, canonical, digest, validate_source
from .harbor_crafting_beacons import (
    build_beacon_rescue, normalize_beacon_action, validate_beacon_board,
)

SCHEMA = "skeleton.game.harbor.beacon-journal.v1"
MAX_JOURNAL_BYTES = 524288
MAX_CHECKPOINTS = 32
FIELDS = {"schema", "source", "board", "checkpoints", "tip", "journal_digest"}
ENTRY_FIELDS = {"sequence", "actions", "report_digest", "previous", "entry_digest"}


def _genesis(source: dict[str, Any], board: dict[str, Any]) -> str:
    return digest({
        "source": digest(source), "board": digest(board), "genesis": True,
    })


def create_beacon_journal(source: Any, board: Any) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_beacon_board(board, world)
    journal = {
        "schema": SCHEMA, "source": world, "board": authored,
        "checkpoints": [], "tip": _genesis(world, authored),
    }
    journal["journal_digest"] = digest(journal)
    if len(canonical(journal)) > MAX_JOURNAL_BYTES:
        raise HarborError("beacon journal exceeds byte budget")
    return journal


def _replay(journal: Any) -> tuple[dict[str, Any], list[dict[str, str]]]:
    _keys(journal, FIELDS, "beacon journal")
    if journal["schema"] != SCHEMA or len(canonical(journal)) > MAX_JOURNAL_BYTES:
        raise HarborError("unsupported or oversized beacon journal")
    if journal["journal_digest"] != digest({
        key: value for key, value in journal.items() if key != "journal_digest"
    }):
        raise HarborError("beacon journal digest mismatch")
    world = validate_source(journal["source"])
    board = validate_beacon_board(journal["board"], world)
    entries = journal["checkpoints"]
    if not isinstance(entries, list) or len(entries) > MAX_CHECKPOINTS:
        raise HarborError("invalid beacon journal checkpoint count")
    actions: list[dict[str, str]] = []
    previous = _genesis(world, board)
    report = build_beacon_rescue(world, board, [])
    for index, entry in enumerate(entries):
        _keys(entry, ENTRY_FIELDS, "beacon journal checkpoint")
        if entry["sequence"] != index or entry["previous"] != previous:
            raise HarborError("beacon journal ancestry mismatch")
        batch = entry["actions"]
        if not isinstance(batch, list) or not 1 <= len(batch) <= board["max_turns"]:
            raise HarborError("invalid beacon journal batch")
        normalized = [normalize_beacon_action(action) for action in batch]
        if normalized != batch:
            raise HarborError("beacon journal action normalization mismatch")
        if report["state"]["rescued"]:
            raise HarborError("beacon journal appended after terminal rescue")
        actions.extend(normalized)
        if len(actions) > board["max_turns"]:
            raise HarborError("beacon journal exceeds turn budget")
        report = build_beacon_rescue(world, board, actions)
        if entry["report_digest"] != report["report_digest"]:
            raise HarborError("beacon journal checkpoint replay mismatch")
        if entry["entry_digest"] != digest({
            key: value for key, value in entry.items() if key != "entry_digest"
        }):
            raise HarborError("beacon journal checkpoint digest mismatch")
        previous = entry["entry_digest"]
    if journal["tip"] != previous:
        raise HarborError("beacon journal tip mismatch")
    return report, actions


def verify_beacon_journal(journal: Any) -> dict[str, Any]:
    report, actions = _replay(journal)
    return {
        "verified": True, "checkpoints": len(journal["checkpoints"]),
        "actions": len(actions), "rescued": report["state"]["rescued"],
        "report_digest": report["report_digest"], "tip": journal["tip"],
    }


def append_beacon_journal(journal: Any, batch: Any, *,
                          expected_tip: str) -> dict[str, Any]:
    report, actions = _replay(journal)
    if type(expected_tip) is not str or expected_tip != journal["tip"]:
        raise HarborError("stale beacon journal lease")
    if report["state"]["rescued"]:
        raise HarborError("beacon journal already terminal")
    if len(journal["checkpoints"]) >= MAX_CHECKPOINTS:
        raise HarborError("beacon journal checkpoint budget exhausted")
    if not isinstance(batch, list) or not 1 <= len(batch) <= journal["board"]["max_turns"]:
        raise HarborError("invalid beacon journal append batch")
    normalized = [normalize_beacon_action(action) for action in batch]
    combined = actions + normalized
    advanced = build_beacon_rescue(journal["source"], journal["board"], combined)
    entry = {
        "sequence": len(journal["checkpoints"]), "actions": normalized,
        "report_digest": advanced["report_digest"], "previous": journal["tip"],
    }
    entry["entry_digest"] = digest(entry)
    updated = deepcopy(journal)
    updated["checkpoints"].append(entry)
    updated["tip"] = entry["entry_digest"]
    updated["journal_digest"] = digest({
        key: value for key, value in updated.items() if key != "journal_digest"
    })
    if len(canonical(updated)) > MAX_JOURNAL_BYTES:
        raise HarborError("beacon journal exceeds byte budget")
    verify_beacon_journal(updated)
    return updated


def beacon_journal_at(journal: Any, checkpoint: int) -> dict[str, Any]:
    _replay(journal)
    _integer(checkpoint, 0, len(journal["checkpoints"]), "beacon checkpoint index")
    actions = [
        action for entry in journal["checkpoints"][:checkpoint]
        for action in entry["actions"]
    ]
    return build_beacon_rescue(journal["source"], journal["board"], actions)


def fork_beacon_journal(journal: Any, checkpoint: int) -> dict[str, Any]:
    _replay(journal)
    _integer(checkpoint, 0, len(journal["checkpoints"]), "beacon fork index")
    updated = deepcopy(journal)
    updated["checkpoints"] = updated["checkpoints"][:checkpoint]
    updated["tip"] = (
        updated["checkpoints"][-1]["entry_digest"] if checkpoint
        else _genesis(updated["source"], updated["board"])
    )
    updated["journal_digest"] = digest({
        key: value for key, value in updated.items() if key != "journal_digest"
    })
    verify_beacon_journal(updated)
    return updated
