"""Replay-authoritative, bounded Lantern Quay session journal.

A journal is a compact sequence of CAS-guarded continuations. Its outer hash
is a corruption detector, not an authorization credential: every verification
replays every transition against the original validated world.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _integer, _keys, canonical, digest,
    normalize_action, verify_bundle,
)
from .harbor_crafting_sessions import resume_bundle

SCHEMA = "skeleton.game.harbor.journal.v1"
MAX_REVISIONS = 32
MAX_ACTIONS_PER_REVISION = 128
MAX_JOURNAL_BYTES = MAX_BUNDLE_BYTES * 2
JOURNAL_FIELDS = {
    "schema", "root", "root_digest", "revisions", "head_terminal_digest",
    "head_bundle_digest", "journal_digest",
}
REVISION_FIELDS = {
    "index", "parent", "actions", "terminal_digest", "bundle_digest",
    "revision_digest",
}


def _seal(journal: dict[str, Any]) -> dict[str, Any]:
    journal["journal_digest"] = digest({
        key: value for key, value in journal.items() if key != "journal_digest"
    })
    if len(canonical(journal)) > MAX_JOURNAL_BYTES:
        raise HarborError("journal exceeds byte budget")
    return journal


def create_journal(bundle: Any) -> dict[str, Any]:
    """Initialize a portable journal from a fully replay-verified checkpoint."""
    verify_bundle(bundle)
    journal = {
        "schema": SCHEMA,
        "root": deepcopy(bundle),
        "root_digest": bundle["bundle_digest"],
        "revisions": [],
        "head_terminal_digest": bundle["terminal_digest"],
        "head_bundle_digest": bundle["bundle_digest"],
    }
    return _seal(journal)


def _replay(journal: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _keys(journal, JOURNAL_FIELDS, "journal")
    if journal["schema"] != SCHEMA or len(canonical(journal)) > MAX_JOURNAL_BYTES:
        raise HarborError("unsupported or oversized journal")
    if journal["journal_digest"] != digest({
        key: value for key, value in journal.items() if key != "journal_digest"
    }):
        raise HarborError("journal digest mismatch")
    root = journal["root"]
    verify_bundle(root)
    if root["bundle_digest"] != journal["root_digest"]:
        raise HarborError("journal root mismatch")
    revisions = journal["revisions"]
    if not isinstance(revisions, list) or len(revisions) > MAX_REVISIONS:
        raise HarborError("journal revision budget exceeded")
    current = root
    states = [deepcopy(root)]
    previous = root["bundle_digest"]
    for index, revision in enumerate(revisions):
        _keys(revision, REVISION_FIELDS, "journal revision")
        if type(revision["index"]) is not int or revision["index"] != index + 1:
            raise HarborError("journal revision sequence mismatch")
        if revision["parent"] != previous:
            raise HarborError("journal parent mismatch")
        if revision["revision_digest"] != digest({
            key: value for key, value in revision.items() if key != "revision_digest"
        }):
            raise HarborError("journal revision digest mismatch")
        actions = revision["actions"]
        if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_ACTIONS_PER_REVISION:
            raise HarborError("journal action budget exceeded")
        normalized = [normalize_action(action) for action in actions]
        if normalized != actions:
            raise HarborError("journal action normalization mismatch")
        current = resume_bundle(
            current, normalized, expected_terminal_digest=current["terminal_digest"],
        )
        if (current["terminal_digest"] != revision["terminal_digest"]
                or current["bundle_digest"] != revision["bundle_digest"]):
            raise HarborError("journal continuation replay mismatch")
        previous = revision["revision_digest"]
        states.append(deepcopy(current))
    if (journal["head_terminal_digest"] != current["terminal_digest"]
            or journal["head_bundle_digest"] != current["bundle_digest"]):
        raise HarborError("journal head mismatch")
    return deepcopy(current), states


def verify_journal(journal: Any) -> dict[str, Any]:
    """Return replay-derived head and revision metadata, never a supplied state."""
    current, states = _replay(journal)
    return {
        "source_digest": current["source_digest"],
        "terminal_digest": current["terminal_digest"],
        "bundle_digest": current["bundle_digest"],
        "tick": current["state"]["tick"],
        "ending": current["state"]["ending"],
        "revisions": len(states) - 1,
    }


def journal_head(journal: Any) -> dict[str, Any]:
    """Reconstruct the canonical playable save from all journal continuations."""
    current, _ = _replay(journal)
    return current


def append_journal(
    journal: Any, actions: Any, *, expected_journal_digest: str,
    require_win: bool = False,
) -> dict[str, Any]:
    """CAS append: on any failure no new journal or partial revision is returned."""
    current, _ = _replay(journal)
    if (type(expected_journal_digest) is not str
            or expected_journal_digest != journal["journal_digest"]):
        raise HarborError("stale journal revision lease")
    if len(journal["revisions"]) >= MAX_REVISIONS:
        raise HarborError("journal revision budget exceeded")
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_ACTIONS_PER_REVISION:
        raise HarborError("journal action budget exceeded")
    normalized = [normalize_action(action) for action in actions]
    updated = resume_bundle(
        current, normalized, expected_terminal_digest=current["terminal_digest"],
        require_win=require_win,
    )
    previous = (
        journal["revisions"][-1]["revision_digest"]
        if journal["revisions"] else journal["root_digest"]
    )
    revision = {
        "index": len(journal["revisions"]) + 1,
        "parent": previous,
        "actions": normalized,
        "terminal_digest": updated["terminal_digest"],
        "bundle_digest": updated["bundle_digest"],
    }
    revision["revision_digest"] = digest(revision)
    result = deepcopy(journal)
    result["revisions"].append(revision)
    result["head_terminal_digest"] = updated["terminal_digest"]
    result["head_bundle_digest"] = updated["bundle_digest"]
    return _seal(result)


def journal_at(journal: Any, index: int) -> dict[str, Any]:
    """Return a verified historical save at a journal revision boundary."""
    _, states = _replay(journal)
    _integer(index, 0, len(states) - 1, "journal revision index")
    return states[index]


def rewind_journal(
    journal: Any, index: int, *, expected_journal_digest: str,
) -> dict[str, Any]:
    """Create an independently verifiable history prefix without mutating input."""
    _, states = _replay(journal)
    if (type(expected_journal_digest) is not str
            or expected_journal_digest != journal["journal_digest"]):
        raise HarborError("stale journal revision lease")
    _integer(index, 0, len(states) - 1, "journal revision index")
    result = deepcopy(journal)
    result["revisions"] = result["revisions"][:index]
    result["head_terminal_digest"] = states[index]["terminal_digest"]
    result["head_bundle_digest"] = states[index]["bundle_digest"]
    return _seal(result)


def journal_audit(journal: Any) -> dict[str, Any]:
    """Replay-derived audit with source, revision, state and digest evidence."""
    current, states = _replay(journal)
    entries = []
    for index, bundle in enumerate(states):
        entries.append({
            "index": index,
            "tick": bundle["state"]["tick"],
            "ending": bundle["state"]["ending"],
            "terminal_digest": bundle["terminal_digest"],
            "bundle_digest": bundle["bundle_digest"],
            "revision_digest": (
                journal["revisions"][index - 1]["revision_digest"] if index else None
            ),
        })
    return {
        "schema": "skeleton.game.harbor.journal-audit.v1",
        "source_digest": current["source_digest"],
        "journal_digest": journal["journal_digest"],
        "entries": entries,
    }
