"""Deterministic source-leased review of two authored Jeeves world workflows.

A comparison is a review artifact, not a merge, replay substitute, write
permission or claim that a native game was compiled. Both plans are fully
replayed against their original source before differences can be inspected.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
from typing import Any

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_world_batch import replay_world_batch_plan

SCHEMA = "skeleton.jeeves.studio_world_batch_comparison.v1"
MAX_COMPARISON_BYTES = 32 * 1024


def compare_world_batch_plans(
    baseline: object, candidate: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world workflow comparison requires authorization")
    left = replay_world_batch_plan(baseline, authorized=True)
    right = replay_world_batch_plan(candidate, authorized=True)
    if left["catalog_digest"] != right["catalog_digest"]:
        raise StudioQuestError("world workflow comparison has different tool catalogs")
    if left["provenance"]["projects"] != right["provenance"]["projects"]:
        raise StudioQuestError("world workflow comparison crosses canon source epochs")
    before = left["steps"]
    after = right["steps"]
    # Exact request identities include all typed arguments, not just tool names.
    # An occurrence number disambiguates repeated identical tool requests.
    def identities(rows: list[dict[str, Any]]) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        result: list[tuple[str, int]] = []
        for row in rows:
            digest = row["request_digest"]
            index = counts.get(digest, 0)
            counts[digest] = index + 1
            result.append((digest, index))
        return result

    before_keys, after_keys = identities(before), identities(after)
    old_positions = {key: index for index, key in enumerate(before_keys)}
    new_positions = {key: index for index, key in enumerate(after_keys)}
    changes: list[dict[str, Any]] = []
    unchanged = 0
    moved = 0
    for ordinal, row in enumerate(after):
        key = after_keys[ordinal]
        prior = old_positions.get(key)
        if prior is None:
            kind = "added"
        elif prior == ordinal:
            kind = "unchanged"
            unchanged += 1
        else:
            kind = "moved"
            moved += 1
        changes.append({
            "kind": kind, "candidate_ordinal": ordinal,
            "baseline_ordinal": prior, "tool": row["request"]["tool"],
            "request_digest": row["request_digest"],
        })
    removed = []
    for ordinal, row in enumerate(before):
        if before_keys[ordinal] not in new_positions:
            removed.append({
                "kind": "removed", "baseline_ordinal": ordinal,
                "candidate_ordinal": None, "tool": row["request"]["tool"],
                "request_digest": row["request_digest"],
            })
    changes.extend(removed)
    changed_count = len(changes) - unchanged
    output: dict[str, Any] = {
        "schema": SCHEMA,
        "catalog_digest": left["catalog_digest"],
        "source_projects": left["provenance"]["projects"],
        "baseline_plan_digest": left["plan_digest"],
        "candidate_plan_digest": right["plan_digest"],
        "baseline_step_count": len(before),
        "candidate_step_count": len(after),
        "changes": changes,
        "changed_count": changed_count,
        "unchanged_count": unchanged,
        "moved_count": moved,
        "added_count": sum(row["kind"] == "added" for row in changes),
        "removed_count": len(removed),
        "source_replay_verified": True,
        "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(output)) > MAX_COMPARISON_BYTES - 128:
        raise StudioQuestError("world workflow comparison exceeds receipt budget")
    output["comparison_digest"] = _digest(output)
    return output


def replay_world_batch_comparison(
    receipt: object, baseline: object, candidate: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world workflow comparison replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid world workflow comparison receipt")
    verified = compare_world_batch_plans(baseline, candidate, authorized=True)
    if verified != receipt:
        raise StudioQuestError("world workflow comparison failed source replay")
    return verified


def render_world_batch_comparison_html(
    receipt: object, baseline: object, candidate: object, *, authorized: bool,
) -> bytes:
    verified = replay_world_batch_comparison(
        receipt, baseline, candidate, authorized=authorized)
    rows = []
    for change in verified["changes"]:
        rows.append(
            "<li>" + escape(change["kind"], quote=True) + ": " +
            escape(change["tool"], quote=True) + " — request SHA-256 " +
            escape(change["request_digest"]) + "</li>")
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        "base-uri 'none'; form-action 'none'\">"
        "<title>Original world workflow comparison</title></head><body><main>"
        "<h1>Source-verified world workflow changes</h1>"
        "<p>Read-only review. Not native runtime, release or rights proof.</p>"
        "<p>Baseline " + escape(verified["baseline_plan_digest"]) +
        "; candidate " + escape(verified["candidate_plan_digest"]) + "</p>"
        "<ol>" + "".join(rows) + "</ol></main></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_COMPARISON_BYTES:
        raise StudioQuestError("world workflow comparison HTML exceeds budget")
    return html
