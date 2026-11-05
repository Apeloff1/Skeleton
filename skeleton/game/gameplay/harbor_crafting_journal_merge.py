"""Fail-closed cross-device Lantern Quay journal comparison and fast-forward.

No implicit three-way gameplay merge: divergent player choices are preserved as
separate verifiable histories. Fast-forward requires exact root and prefix
identity and a caller-provided optimistic lease.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _keys, canonical, digest
from .harbor_crafting_journal import (
    MAX_JOURNAL_BYTES, journal_head, verify_journal,
)

SCHEMA = "skeleton.game.harbor.journal-comparison.v1"
MAX_COMPARISON_BYTES = MAX_JOURNAL_BYTES * 2 + 65536
FIELDS = {
    "schema", "left", "right", "left_digest", "right_digest", "root_digest",
    "common_revisions", "left_revisions", "right_revisions", "relation",
    "left_terminal_digest", "right_terminal_digest", "comparison_digest",
}


def _shared(left: dict[str, Any], right: dict[str, Any]) -> int:
    """Count complete identical revision records, not merely matching indices."""
    count = 0
    for a, b in zip(left["revisions"], right["revisions"]):
        if a != b:
            break
        count += 1
    return count


def compare_journals(left: Any, right: Any) -> dict[str, Any]:
    """Replay both histories and classify safe fast-forward versus divergence."""
    verify_journal(left)
    verify_journal(right)
    if left["root_digest"] != right["root_digest"]:
        raise HarborError("journal comparison root mismatch")
    if left["root"] != right["root"]:
        raise HarborError("journal comparison root substitution")
    common = _shared(left, right)
    l_count = len(left["revisions"])
    r_count = len(right["revisions"])
    if common == l_count == r_count:
        relation = "identical"
    elif common == l_count:
        relation = "left_ancestor"
    elif common == r_count:
        relation = "right_ancestor"
    else:
        relation = "diverged"
    report = {
        "schema": SCHEMA,
        "left": deepcopy(left),
        "right": deepcopy(right),
        "left_digest": left["journal_digest"],
        "right_digest": right["journal_digest"],
        "root_digest": left["root_digest"],
        "common_revisions": common,
        "left_revisions": l_count,
        "right_revisions": r_count,
        "relation": relation,
        "left_terminal_digest": left["head_terminal_digest"],
        "right_terminal_digest": right["head_terminal_digest"],
    }
    report["comparison_digest"] = digest(report)
    if len(canonical(report)) > MAX_COMPARISON_BYTES:
        raise HarborError("journal comparison exceeds byte limit")
    return report


def verify_journal_comparison(report: Any) -> dict[str, Any]:
    """Replay both branches; a recomputed outer digest is never enough."""
    _keys(report, FIELDS, "journal comparison")
    if report["schema"] != SCHEMA or len(canonical(report)) > MAX_COMPARISON_BYTES:
        raise HarborError("unsupported or oversized journal comparison")
    if report["comparison_digest"] != digest({
        key: value for key, value in report.items() if key != "comparison_digest"
    }):
        raise HarborError("journal comparison digest mismatch")
    rebuilt = compare_journals(report["left"], report["right"])
    if rebuilt != report:
        raise HarborError("journal comparison replay mismatch")
    return {
        "relation": rebuilt["relation"],
        "common_revisions": rebuilt["common_revisions"],
        "left_revisions": rebuilt["left_revisions"],
        "right_revisions": rebuilt["right_revisions"],
    }


def fast_forward_journal(
    current: Any, candidate: Any, *, expected_journal_digest: str,
) -> dict[str, Any]:
    """Return a candidate only when it extends every current revision exactly."""
    if (type(expected_journal_digest) is not str
            or not isinstance(current, dict)
            or current.get("journal_digest") != expected_journal_digest):
        raise HarborError("stale journal fast-forward lease")
    comparison = compare_journals(current, candidate)
    if comparison["relation"] not in ("identical", "left_ancestor"):
        raise HarborError("journal histories conflict; manual choice required")
    # Rebuild both saves, not just their hashes, before returning portable bytes.
    journal_head(current)
    journal_head(candidate)
    return deepcopy(candidate)
