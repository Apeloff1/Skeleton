"""Portable source-bound journal -> playable game distribution acceptance.

A journal may be exported as a package play only when its original world
matches the independently replay-verified package. The transfer is a
replayable game artifact, not an executable or an authenticated signature.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, MAX_BUNDLE_BYTES, _keys, canonical, digest
from .harbor_crafting_journal import MAX_JOURNAL_BYTES, journal_head, verify_journal
from .harbor_crafting_package import (
    MAX_PLAY_BYTES, play_package, verify_package, verify_package_play,
)

SCHEMA = "skeleton.game.harbor.journal-package-play.v1"
MAX_TRANSFER_BYTES = MAX_JOURNAL_BYTES + MAX_PLAY_BYTES + MAX_BUNDLE_BYTES
FIELDS = {
    "schema", "journal", "journal_digest", "package_play",
    "package_digest", "terminal_digest", "transfer_digest",
}


def export_journal_package_play(
    journal: Any, package: Any, *, require_all: bool = False,
) -> dict[str, Any]:
    """Reconstruct game actions and export a fully playable package session."""
    verify_journal(journal)
    package_info = verify_package(package)
    head = journal_head(journal)
    if (head["source_digest"] != package_info["source_digest"]
            or head["source"] != package["source"]):
        raise HarborError("journal package world mismatch")
    actions = [deepcopy(event["action"]) for event in head["events"]]
    play = play_package(package, actions, require_all=require_all)
    verified = verify_package_play(play, require_all=require_all)
    if (play["report"]["bundle"] != head
            or verified["ending"] != head["state"]["ending"]):
        raise HarborError("journal package gameplay mismatch")
    result = {
        "schema": SCHEMA,
        "journal": deepcopy(journal),
        "journal_digest": journal["journal_digest"],
        "package_play": play,
        "package_digest": package_info["package_digest"],
        "terminal_digest": head["terminal_digest"],
    }
    result["transfer_digest"] = digest(result)
    if len(canonical(result)) > MAX_TRANSFER_BYTES:
        raise HarborError("journal package transfer exceeds byte limit")
    return result


def verify_journal_package_play(transfer: Any, *, require_all: bool = False) -> dict[str, Any]:
    """Replay world, journal, mission board and packaged gameplay independently."""
    _keys(transfer, FIELDS, "journal package transfer")
    if transfer["schema"] != SCHEMA or len(canonical(transfer)) > MAX_TRANSFER_BYTES:
        raise HarborError("unsupported or oversized journal package transfer")
    if transfer["transfer_digest"] != digest({
        key: value for key, value in transfer.items() if key != "transfer_digest"
    }):
        raise HarborError("journal package transfer digest mismatch")
    journal = transfer["journal"]
    if not isinstance(journal, dict) or transfer["journal_digest"] != journal.get("journal_digest"):
        raise HarborError("journal package custody mismatch")
    play = transfer["package_play"]
    if not isinstance(play, dict) or not isinstance(play.get("package"), dict):
        raise HarborError("journal package play missing")
    rebuilt = export_journal_package_play(
        journal, play["package"], require_all=require_all,
    )
    if rebuilt != transfer:
        raise HarborError("journal package transfer replay mismatch")
    return {
        "journal_digest": rebuilt["journal_digest"],
        "package_digest": rebuilt["package_digest"],
        "terminal_digest": rebuilt["terminal_digest"],
        "ending": rebuilt["package_play"]["report"]["bundle"]["state"]["ending"],
        "points": rebuilt["package_play"]["report"]["points"],
    }
