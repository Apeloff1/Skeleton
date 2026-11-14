"""Optimistic immutable routebook edits; replay must still prove outcomes."""
from __future__ import annotations

from copy import deepcopy
from .custody import canonical, digest
from .routebook import RoutebookError, parse_routebook, run_route

REVISION_SCHEMA = "ridge.rescue.routebook.revision.v1"


def revise_routebook(source: dict | str | bytes, operation: dict) -> dict:
    before = parse_routebook(source)
    if not isinstance(operation, dict) or set(operation) != {"expected_sha256", "kind", "track", "index", "value"}:
        raise RoutebookError("invalid route edit operation")
    if operation["expected_sha256"] != digest(before):
        raise RoutebookError("stale routebook source revision")
    if operation["kind"] not in ("set-action", "set-guard", "set-title"):
        raise RoutebookError("unsupported route edit")
    updated = deepcopy(before)
    matches = [track for track in updated["tracks"] if track["id"] == operation["track"]]
    if len(matches) != 1:
        raise RoutebookError("unknown route edit target")
    track = matches[0]
    if operation["kind"] == "set-title":
        if operation["index"] is not None:
            raise RoutebookError("title edit cannot use step index")
        track["title"] = operation["value"]
    else:
        index = operation["index"]
        if type(index) is not int or not 0 <= index < len(track["steps"]):
            raise RoutebookError("invalid route step index")
        track["steps"][index]["action" if operation["kind"] == "set-action" else "guard"] = operation["value"]
    normalized = parse_routebook(updated)
    # The edited track is a playable contract, not merely a syntactically valid document.
    try:
        completed = run_route(normalized, track["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise RoutebookError("edited route does not replay to earned ending") from exc
    if completed["status"] != "completed":
        raise RoutebookError("edited route is not playable")
    return {"schema": REVISION_SCHEMA, "previous_sha256": digest(before),
            "sha256": digest(normalized), "source": normalized}


def verify_routebook_revision(source: dict | str | bytes, revision: dict, operation: dict) -> bool:
    if not isinstance(revision, dict) or set(revision) != {"schema", "previous_sha256", "sha256", "source"}:
        raise RoutebookError("invalid route revision")
    if revision["schema"] != REVISION_SCHEMA:
        raise RoutebookError("unsupported route revision")
    expected = revise_routebook(source, operation)
    if canonical(revision) != canonical(expected):
        raise RoutebookError("route edit revision does not replay")
    return True
