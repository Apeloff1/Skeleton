"""Append-only CAS convoy play journal with bounded historical replay and forks."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _keys, canonical, digest
from .harbor_crafting_convoy import normalize_convoy_action
from .harbor_crafting_convoy_package import (
    MAX_PLAY_BYTES, play_convoy_package, verify_convoy_package,
    verify_convoy_package_play,
)

SCHEMA = "skeleton.game.harbor.convoy-journal.v1"
MAX_JOURNAL_BYTES = MAX_PLAY_BYTES + 131072
MAX_ENTRIES = 32
MAX_ACTIONS = 256
MAX_SEGMENT = 32
FIELDS = {"schema", "package", "entries", "head", "journal_digest"}
ENTRY_FIELDS = {"index", "actions", "previous", "report_digest", "digest"}


def _seal(journal: dict[str, Any]) -> dict[str, Any]:
    journal["journal_digest"] = digest({
        key: value for key, value in journal.items() if key != "journal_digest"
    })
    if len(canonical(journal)) > MAX_JOURNAL_BYTES:
        raise HarborError("convoy journal exceeds byte budget")
    return journal


def create_convoy_journal(package: Any) -> dict[str, Any]:
    verify_convoy_package(package)
    genesis = play_convoy_package(package, [])
    return _seal({
        "schema": SCHEMA, "package": deepcopy(package),
        "entries": [], "head": genesis["play_digest"],
    })


def verify_convoy_journal(journal: Any) -> dict[str, Any]:
    _keys(journal, FIELDS, "convoy journal")
    if journal["schema"] != SCHEMA or len(canonical(journal)) > MAX_JOURNAL_BYTES:
        raise HarborError("unsupported or oversized convoy journal")
    if journal["journal_digest"] != digest({
        key: value for key, value in journal.items() if key != "journal_digest"
    }):
        raise HarborError("convoy journal digest mismatch")
    verify_convoy_package(journal["package"])
    entries = journal["entries"]
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise HarborError("invalid convoy journal length")
    all_actions: list[dict[str, str]] = []
    previous = digest({"package": journal["package"]["package_digest"], "genesis": True})
    for index, entry in enumerate(entries):
        _keys(entry, ENTRY_FIELDS, "convoy journal entry")
        if type(entry["index"]) is not int or entry["index"] != index:
            raise HarborError("convoy journal index mismatch")
        if (not isinstance(entry["actions"], list)
                or not 1 <= len(entry["actions"]) <= MAX_SEGMENT):
            raise HarborError("invalid convoy journal segment")
        normalized = [normalize_convoy_action(a) for a in entry["actions"]]
        if normalized != entry["actions"]:
            raise HarborError("noncanonical convoy journal actions")
        all_actions.extend(normalized)
        if len(all_actions) > MAX_ACTIONS:
            raise HarborError("convoy journal action budget exhausted")
        if entry["previous"] != previous:
            raise HarborError("convoy journal ancestry mismatch")
        if entry["digest"] != digest({
            key: value for key, value in entry.items() if key != "digest"
        }):
            raise HarborError("convoy journal entry digest mismatch")
        report = play_convoy_package(journal["package"], all_actions)
        if report["report"]["report_digest"] != entry["report_digest"]:
            raise HarborError("convoy journal replay mismatch")
        previous = entry["digest"]
    play = play_convoy_package(journal["package"], all_actions)
    if play["play_digest"] != journal["head"]:
        raise HarborError("convoy journal head replay mismatch")
    verify_convoy_package_play(play)
    return {
        "verified": True, "entries": len(entries), "actions": len(all_actions),
        "head": play["play_digest"],
        "complete": play["report"]["state"]["complete"],
        "failed": play["report"]["state"]["failed"],
        "journal_digest": journal["journal_digest"],
    }


def append_convoy_journal(journal: Any, actions: Any, *,
                          expected_digest: str) -> dict[str, Any]:
    status = verify_convoy_journal(journal)
    if type(expected_digest) is not str or expected_digest != status["journal_digest"]:
        raise HarborError("stale convoy journal lease")
    if status["complete"] or status["failed"]:
        raise HarborError("terminal convoy journal cannot advance")
    if len(journal["entries"]) >= MAX_ENTRIES:
        raise HarborError("convoy journal entry budget exhausted")
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_SEGMENT:
        raise HarborError("invalid convoy journal append segment")
    normalized = [normalize_convoy_action(a) for a in actions]
    previous_actions = [
        action for entry in journal["entries"] for action in entry["actions"]
    ]
    if len(previous_actions) + len(normalized) > MAX_ACTIONS:
        raise HarborError("convoy journal action budget exhausted")
    next_play = play_convoy_package(journal["package"], previous_actions + normalized)
    previous = (
        journal["entries"][-1]["digest"] if journal["entries"]
        else digest({"package": journal["package"]["package_digest"], "genesis": True})
    )
    entry = {
        "index": len(journal["entries"]), "actions": normalized,
        "previous": previous, "report_digest": next_play["report"]["report_digest"],
    }
    entry["digest"] = digest(entry)
    updated = {
        "schema": SCHEMA, "package": deepcopy(journal["package"]),
        "entries": deepcopy(journal["entries"]) + [entry],
        "head": next_play["play_digest"],
    }
    result = _seal(updated)
    verify_convoy_journal(result)
    return result


def convoy_journal_at(journal: Any, index: int) -> dict[str, Any]:
    verify_convoy_journal(journal)
    if type(index) is not int or not 0 <= index <= len(journal["entries"]):
        raise HarborError("invalid convoy journal historical index")
    entries = deepcopy(journal["entries"][:index])
    actions = [action for entry in entries for action in entry["actions"]]
    play = play_convoy_package(journal["package"], actions)
    historical = _seal({
        "schema": SCHEMA, "package": deepcopy(journal["package"]),
        "entries": entries, "head": play["play_digest"],
    })
    verify_convoy_journal(historical)
    return historical
