"""Bounded append-only league action journal with CAS, replay and history."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _integer, _keys, canonical, digest
from .harbor_crafting_convoy import normalize_convoy_action
from .harbor_crafting_convoy_league_package import (
    MAX_PLAY_BYTES, play_league_package, resume_league_package,
    verify_league_package, verify_league_package_play,
)

SCHEMA = "skeleton.game.harbor.convoy-league-journal.v1"
MAX_JOURNAL_BYTES = MAX_PLAY_BYTES + 262144
MAX_ENTRIES = 32
MAX_SEGMENT = 32
MAX_ACTIONS = 256
FIELDS = {"schema", "package", "entries", "head", "journal_digest"}
ENTRY_FIELDS = {"index", "actions", "previous", "save_digest", "play_digest", "digest"}


def _seal(journal: dict[str, Any]) -> dict[str, Any]:
    journal["journal_digest"] = digest({
        key: value for key, value in journal.items() if key != "journal_digest"
    })
    if len(canonical(journal)) > MAX_JOURNAL_BYTES:
        raise HarborError("league journal exceeds byte budget")
    return journal


def create_league_journal(package: Any) -> dict[str, Any]:
    verify_league_package(package)
    genesis = play_league_package(package, [])
    return _seal({
        "schema": SCHEMA, "package": deepcopy(package),
        "entries": [], "head": genesis["play_digest"],
    })


def _replay(journal: Any) -> dict[str, Any]:
    verify_league_package(journal["package"])
    entries = journal["entries"]
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise HarborError("invalid league journal entries")
    play = play_league_package(journal["package"], [])
    previous = digest({"package": journal["package"]["package_digest"], "genesis": True})
    total = 0
    for index, entry in enumerate(entries):
        _keys(entry, ENTRY_FIELDS, "league journal entry")
        if type(entry["index"]) is not int or entry["index"] != index:
            raise HarborError("league journal index mismatch")
        actions = entry["actions"]
        if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_SEGMENT:
            raise HarborError("invalid league journal segment")
        normalized = [normalize_convoy_action(action) for action in actions]
        if normalized != actions:
            raise HarborError("noncanonical league journal actions")
        total += len(actions)
        if total > MAX_ACTIONS:
            raise HarborError("league journal action budget exhausted")
        if entry["previous"] != previous:
            raise HarborError("league journal ancestry mismatch")
        if entry["digest"] != digest({
            key: value for key, value in entry.items() if key != "digest"
        }):
            raise HarborError("league journal entry digest mismatch")
        play = resume_league_package(
            play, normalized, expected_digest=play["play_digest"],
        )
        if (play["play_digest"] != entry["play_digest"]
                or play["save"]["save_digest"] != entry["save_digest"]):
            raise HarborError("league journal replay mismatch")
        previous = entry["digest"]
    if play["play_digest"] != journal["head"]:
        raise HarborError("league journal head mismatch")
    verify_league_package_play(play)
    return play


def verify_league_journal(journal: Any) -> dict[str, Any]:
    _keys(journal, FIELDS, "league journal")
    if journal["schema"] != SCHEMA or len(canonical(journal)) > MAX_JOURNAL_BYTES:
        raise HarborError("unsupported or oversized league journal")
    if journal["journal_digest"] != digest({
        key: value for key, value in journal.items() if key != "journal_digest"
    }):
        raise HarborError("league journal digest mismatch")
    play = _replay(journal)
    return {
        "verified": True, "entries": len(journal["entries"]),
        "head": play["play_digest"], "score": play["save"]["score"],
        "complete": play["save"]["complete"], "failed": play["save"]["failed"],
        "journal_digest": journal["journal_digest"],
    }


def append_league_journal(journal: Any, actions: Any, *,
                          expected_digest: str) -> dict[str, Any]:
    status = verify_league_journal(journal)
    if type(expected_digest) is not str or expected_digest != status["journal_digest"]:
        raise HarborError("stale league journal lease")
    if status["complete"] or status["failed"]:
        raise HarborError("terminal league journal cannot advance")
    if len(journal["entries"]) >= MAX_ENTRIES:
        raise HarborError("league journal entry budget exhausted")
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_SEGMENT:
        raise HarborError("invalid league journal append segment")
    normalized = [normalize_convoy_action(action) for action in actions]
    if sum(len(entry["actions"]) for entry in journal["entries"]) + len(normalized) > MAX_ACTIONS:
        raise HarborError("league journal action budget exhausted")
    play = _replay(journal)
    next_play = resume_league_package(
        play, normalized, expected_digest=play["play_digest"],
    )
    previous = (
        journal["entries"][-1]["digest"] if journal["entries"]
        else digest({"package": journal["package"]["package_digest"], "genesis": True})
    )
    entry = {
        "index": len(journal["entries"]), "actions": normalized,
        "previous": previous, "save_digest": next_play["save"]["save_digest"],
        "play_digest": next_play["play_digest"],
    }
    entry["digest"] = digest(entry)
    updated = _seal({
        "schema": SCHEMA, "package": deepcopy(journal["package"]),
        "entries": deepcopy(journal["entries"]) + [entry],
        "head": next_play["play_digest"],
    })
    verify_league_journal(updated)
    return updated


def league_journal_at(journal: Any, index: int) -> dict[str, Any]:
    verify_league_journal(journal)
    _integer(index, 0, len(journal["entries"]), "league journal index")
    entries = deepcopy(journal["entries"][:index])
    head = (
        entries[-1]["play_digest"] if entries
        else play_league_package(journal["package"], [])["play_digest"]
    )
    historical = _seal({
        "schema": SCHEMA, "package": deepcopy(journal["package"]),
        "entries": entries, "head": head,
    })
    verify_league_journal(historical)
    return historical


def compare_league_journals(left: Any, right: Any) -> dict[str, Any]:
    a = verify_league_journal(left)
    b = verify_league_journal(right)
    if left["package"] != right["package"]:
        raise HarborError("league journals use different packages")
    common = 0
    for first, second in zip(left["entries"], right["entries"]):
        if first != second:
            break
        common += 1
    return {
        "common_entries": common, "left_entries": a["entries"],
        "right_entries": b["entries"],
        "left_head": a["head"], "right_head": b["head"],
        "fast_forward": common == len(left["entries"]) and len(right["entries"]) > common,
        "diverged": common < min(len(left["entries"]), len(right["entries"])),
    }


def fast_forward_league_journal(left: Any, right: Any, *,
                                expected_digest: str) -> dict[str, Any]:
    comparison = compare_league_journals(left, right)
    if type(expected_digest) is not str or expected_digest != left["journal_digest"]:
        raise HarborError("stale league journal fast-forward lease")
    if not comparison["fast_forward"]:
        raise HarborError("league journal is not a strict descendant")
    return deepcopy(right)
