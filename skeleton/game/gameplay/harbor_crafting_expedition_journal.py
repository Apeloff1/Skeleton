"""Bounded append-only expedition save custody, historical replay and safe forks.

A journal is a sequence of complete source-bound expedition replays. Every
revision must strictly extend the previous input action prefix and preserve
all three derived gameplay planes. Divergent branches are never auto-merged.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _integer, _keys, canonical, digest
from .harbor_crafting_expedition import verify_expedition

SCHEMA = "skeleton.game.harbor.expedition-journal.v1"
COMPARE_SCHEMA = "skeleton.game.harbor.expedition-journal-compare.v1"
MAX_ENTRIES = 16
MAX_JOURNAL_BYTES = 8 * 1024 * 1024
MAX_COMPARE_BYTES = MAX_JOURNAL_BYTES * 2 + 8192
FIELDS = {"schema", "entries", "head_report_digest", "journal_digest"}
ENTRY_FIELDS = {"index", "report", "previous", "digest"}


def _same_source(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return all(first[key] == second[key] for key in (
        "source", "survey_board", "weather_board", "dialogue_board",
    ))


def _extends(first: dict[str, Any], second: dict[str, Any]) -> bool:
    old = first["input_actions"]
    new = second["input_actions"]
    if len(new) <= len(old) or new[:len(old)] != old:
        return False
    for key, field in (("dialogue", "events"), ("weather", "events")):
        if second[key][field][:len(first[key][field])] != first[key][field]:
            return False
    return (second["survey"]["bundle"]["events"][:len(first["survey"]["bundle"]["events"])]
            == first["survey"]["bundle"]["events"])


def _build(reports: Any) -> dict[str, Any]:
    if not isinstance(reports, list) or not 1 <= len(reports) <= MAX_ENTRIES:
        raise HarborError("invalid expedition journal length")
    entries: list[dict[str, Any]] = []
    previous = None
    for index, report in enumerate(reports):
        verify_expedition(report)
        if previous is not None:
            if not _same_source(previous, report):
                raise HarborError("expedition journal source drift")
            if previous["dialogue"]["bundle"]["state"]["ending"] is not None:
                raise HarborError("expedition journal cannot extend terminal game")
            if not _extends(previous, report):
                raise HarborError("expedition journal history divergence")
        previous_digest = (
            entries[-1]["digest"] if entries
            else digest({"genesis": True, "source": report["dialogue"]["bundle"]["source_digest"]})
        )
        entry = {
            "index": index, "report": deepcopy(report),
            "previous": previous_digest,
        }
        entry["digest"] = digest(entry)
        entries.append(entry)
        previous = report
    journal = {
        "schema": SCHEMA, "entries": entries,
        "head_report_digest": reports[-1]["expedition_digest"],
    }
    journal["journal_digest"] = digest(journal)
    if len(canonical(journal)) > MAX_JOURNAL_BYTES:
        raise HarborError("expedition journal exceeds byte limit")
    return journal


def create_expedition_journal(report: Any) -> dict[str, Any]:
    return _build([report])


def verify_expedition_journal(journal: Any) -> dict[str, Any]:
    _keys(journal, FIELDS, "expedition journal")
    if journal["schema"] != SCHEMA or len(canonical(journal)) > MAX_JOURNAL_BYTES:
        raise HarborError("unsupported or oversized expedition journal")
    if journal["journal_digest"] != digest({
        key: value for key, value in journal.items() if key != "journal_digest"
    }):
        raise HarborError("expedition journal digest mismatch")
    entries = journal["entries"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ENTRIES:
        raise HarborError("invalid expedition journal entries")
    reports = []
    for entry in entries:
        _keys(entry, ENTRY_FIELDS, "expedition journal entry")
        reports.append(entry["report"])
    rebuilt = _build(reports)
    if rebuilt != journal:
        raise HarborError("expedition journal replay mismatch")
    return {
        "revisions": len(entries), "head_report_digest": journal["head_report_digest"],
        "journal_digest": journal["journal_digest"],
        "complete": entries[-1]["report"]["complete"],
    }


def append_expedition_journal(journal: Any, report: Any, *,
                              expected_digest: str) -> dict[str, Any]:
    status = verify_expedition_journal(journal)
    if type(expected_digest) is not str or expected_digest != status["journal_digest"]:
        raise HarborError("stale expedition journal lease")
    return _build([entry["report"] for entry in journal["entries"]] + [report])


def expedition_journal_at(journal: Any, revision: int) -> dict[str, Any]:
    verify_expedition_journal(journal)
    _integer(revision, 0, len(journal["entries"]) - 1, "expedition revision")
    return deepcopy(journal["entries"][revision]["report"])


def fork_expedition_journal(journal: Any, revision: int, *,
                            expected_digest: str) -> dict[str, Any]:
    status = verify_expedition_journal(journal)
    if type(expected_digest) is not str or expected_digest != status["journal_digest"]:
        raise HarborError("stale expedition fork lease")
    _integer(revision, 0, len(journal["entries"]) - 1, "expedition fork revision")
    return _build([entry["report"] for entry in journal["entries"][:revision + 1]])


def compare_expedition_journals(left: Any, right: Any) -> dict[str, Any]:
    verify_expedition_journal(left)
    verify_expedition_journal(right)
    a = left["entries"]
    b = right["entries"]
    if a[0]["digest"] != b[0]["digest"]:
        raise HarborError("expedition journals have different genesis")
    common = 0
    for x, y in zip(a, b):
        if x["digest"] != y["digest"]:
            break
        common += 1
    if common == len(a) == len(b):
        relation = "identical"
    elif common == len(a):
        relation = "right_ahead"
    elif common == len(b):
        relation = "left_ahead"
    else:
        relation = "diverged"
    comparison = {
        "schema": COMPARE_SCHEMA,
        "left": deepcopy(left), "right": deepcopy(right),
        "common_revisions": common, "relation": relation,
        "left_head": left["journal_digest"], "right_head": right["journal_digest"],
    }
    comparison["comparison_digest"] = digest(comparison)
    if len(canonical(comparison)) > MAX_COMPARE_BYTES:
        raise HarborError("expedition comparison exceeds byte limit")
    return comparison


def verify_expedition_comparison(comparison: Any) -> dict[str, Any]:
    _keys(comparison, {
        "schema", "left", "right", "common_revisions", "relation",
        "left_head", "right_head", "comparison_digest",
    }, "expedition comparison")
    if (comparison["schema"] != COMPARE_SCHEMA
            or len(canonical(comparison)) > MAX_COMPARE_BYTES):
        raise HarborError("unsupported or oversized expedition comparison")
    if comparison["comparison_digest"] != digest({
        key: value for key, value in comparison.items() if key != "comparison_digest"
    }):
        raise HarborError("expedition comparison digest mismatch")
    rebuilt = compare_expedition_journals(comparison["left"], comparison["right"])
    if rebuilt != comparison:
        raise HarborError("expedition comparison replay mismatch")
    return {"relation": rebuilt["relation"], "common_revisions": rebuilt["common_revisions"]}


def fast_forward_expedition_journal(left: Any, right: Any, *,
                                    expected_digest: str) -> dict[str, Any]:
    status = verify_expedition_journal(left)
    if type(expected_digest) is not str or expected_digest != status["journal_digest"]:
        raise HarborError("stale expedition fast-forward lease")
    comparison = compare_expedition_journals(left, right)
    if comparison["relation"] != "right_ahead":
        raise HarborError("expedition journal fast-forward requires strict ancestry")
    return deepcopy(right)
