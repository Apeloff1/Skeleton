"""Transactional authoring for source-bound Lantern Quay time-trial courses.

The revision is a replayable edit transaction. It uses both source and course
compare-and-swap digests and can optionally carry a canonical gameplay preview.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _keys,
    canonical, digest, validate_source, verify_bundle,
)
from .harbor_crafting_time_trials import (
    MAX_COURSE_BYTES, time_trial_report, validate_course,
)

SCHEMA = "skeleton.game.harbor.time-trial-revision.v1"
MAX_EDITS = 16
MAX_REVISION_BYTES = MAX_BUNDLE_BYTES * 5
FIELDS = {
    "schema", "source", "source_digest", "base_course", "base_course_digest",
    "edits", "course", "course_digest", "preview_bundle", "preview_report",
    "revision_digest",
}
SHAPES = {
    "set_deadline": {"op", "deadline"},
    "set_medals": {"op", "gold", "silver", "bronze"},
    "set_choice": {"op", "choice"},
    "set_checkpoint": {"op", "id", "at", "latest_tick"},
    "append_checkpoint": {"op", "id", "at", "latest_tick"},
    "remove_checkpoint": {"op", "id"},
}


def _apply(course: dict[str, Any], edits: Any) -> dict[str, Any]:
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
        raise HarborError("invalid time trial edit count")
    updated = deepcopy(course)
    for edit in edits:
        if not isinstance(edit, dict):
            raise HarborError("invalid time trial edit")
        op = edit.get("op")
        if type(op) is not str or op not in SHAPES or set(edit) != SHAPES[op]:
            raise HarborError("unsupported time trial edit shape")
        if op == "set_deadline":
            updated["deadline"] = _integer(edit["deadline"], 1, 1024, "edited deadline")
        elif op == "set_medals":
            updated["medals"] = {
                key: _integer(edit[key], 1, 1024, key + " medal")
                for key in ("gold", "silver", "bronze")
            }
        elif op == "set_choice":
            if type(edit["choice"]) is not str or edit["choice"] not in ("signal", "shelter"):
                raise HarborError("invalid edited ending")
            updated["choice"] = edit["choice"]
        else:
            name = _identifier(edit["id"], "edited checkpoint id")
            index = next(
                (i for i, point in enumerate(updated["checkpoints"]) if point["id"] == name),
                None,
            )
            if op == "remove_checkpoint":
                if index is None:
                    raise HarborError("missing checkpoint for removal")
                del updated["checkpoints"][index]
                continue
            point = {
                "id": name, "at": deepcopy(edit["at"]),
                "latest_tick": edit["latest_tick"],
            }
            if op == "append_checkpoint":
                if index is not None:
                    raise HarborError("checkpoint already exists")
                updated["checkpoints"].append(point)
            elif op == "set_checkpoint":
                if index is None:
                    raise HarborError("missing checkpoint for edit")
                updated["checkpoints"][index] = point
    return updated


def author_time_trial_revision(
    course: Any, source: Any, edits: Any, *,
    expected_course_digest: str, expected_source_digest: str,
    preview_bundle: Any = None,
) -> dict[str, Any]:
    """Apply the entire edit transaction or reject it without publishing a result."""
    world = validate_source(source)
    base = validate_course(course, world)
    if expected_source_digest != digest(world):
        raise HarborError("stale time trial source digest")
    if expected_course_digest != digest(base):
        raise HarborError("stale time trial course digest")
    if len(canonical(edits)) > MAX_COURSE_BYTES:
        raise HarborError("time trial edits exceed byte limit")
    revised = validate_course(_apply(base, edits), world)
    preview = None
    stored_bundle = None
    if preview_bundle is not None:
        verify_bundle(preview_bundle)
        if preview_bundle["source_digest"] != digest(world):
            raise HarborError("time trial preview source mismatch")
        stored_bundle = deepcopy(preview_bundle)
        preview = time_trial_report(stored_bundle, revised)
    revision = {
        "schema": SCHEMA, "source": world, "source_digest": digest(world),
        "base_course": base, "base_course_digest": digest(base),
        "edits": deepcopy(edits), "course": revised,
        "course_digest": digest(revised), "preview_bundle": stored_bundle,
        "preview_report": preview,
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("time trial revision exceeds byte limit")
    return revision


def verify_time_trial_revision(revision: Any) -> dict[str, Any]:
    """Re-run the original transaction, including an optional game replay preview."""
    _keys(revision, FIELDS, "time trial revision")
    if revision["schema"] != SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized time trial revision")
    if revision["revision_digest"] != digest({
        key: value for key, value in revision.items() if key != "revision_digest"
    }):
        raise HarborError("time trial revision digest mismatch")
    rebuilt = author_time_trial_revision(
        revision["base_course"], revision["source"], revision["edits"],
        expected_course_digest=revision["base_course_digest"],
        expected_source_digest=revision["source_digest"],
        preview_bundle=revision["preview_bundle"],
    )
    if rebuilt != revision:
        raise HarborError("time trial revision replay mismatch")
    return {
        "course": deepcopy(rebuilt["course"]),
        "course_digest": rebuilt["course_digest"],
        "preview": deepcopy(rebuilt["preview_report"]),
    }
