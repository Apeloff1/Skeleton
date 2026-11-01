"""Fail-closed append-only three-way merge for source-leased Jeeves workflows.

This is a *typed planning* merge, not a Git merge or a grant of execution
authority. It accepts only two append-only forks of one canon-replayed plan.
Any deletion, reordering, rewrite, ambiguous duplicate or incompatible
concurrent addition fails before a merged plan can be compiled or executed.
"""
from __future__ import annotations

from html import escape
from typing import Any

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical, _digest
from skeleton.ai.game_builder.studio_world_batch import (
    MAX_STEPS, compile_world_batch_plan, replay_world_batch_plan,
)

SCHEMA = "skeleton.jeeves.studio_world_batch_three_way_merge.v1"
PROMPT = "merge append-only original world workflows"
MAX_RECEIPT_BYTES = 32 * 1024


def _requests(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [step["request"] for step in plan["steps"]]


def _identity(request: dict[str, Any]) -> tuple[str, str]:
    """Conflict domain: one tool acting on one canonical authored project."""
    return (request["tool"], request["arguments"]["project_id"])


def _merge_suffix_order(
    left_suffix: list[dict[str, Any]], right_suffix: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Stable topological merge preserving *both* authored branch orders.

    A common step may appear in both forks. Its position is a causal
    constraint, not permission to move earlier or later steps around it.
    A cycle is a genuine merge conflict; selecting a winner would silently
    rewrite one operator's authored workflow.
    """
    by_digest: dict[str, dict[str, Any]] = {}
    rank: dict[str, int] = {}
    edges: dict[str, set[str]] = {}
    indegree: dict[str, int] = {}
    for suffix in (left_suffix, right_suffix):
        for request in suffix:
            digest = _digest(request)
            if digest not in by_digest:
                rank[digest] = len(rank)
                by_digest[digest] = request
                edges[digest] = set()
                indegree[digest] = 0
        sequence = [_digest(request) for request in suffix]
        for earlier, later in zip(sequence, sequence[1:]):
            if earlier == later:
                raise StudioQuestError("three-way merge has repeated ordered steps")
            if later not in edges[earlier]:
                edges[earlier].add(later)
                indegree[later] += 1

    ready = [key for key in by_digest if indegree[key] == 0]
    merged: list[dict[str, Any]] = []
    while ready:
        ready.sort(key=rank.__getitem__)
        key = ready.pop(0)
        merged.append(by_digest[key])
        for following in sorted(edges[key], key=rank.__getitem__):
            indegree[following] -= 1
            if indegree[following] == 0:
                ready.append(following)
    if len(merged) != len(by_digest):
        raise StudioQuestError("three-way merge has conflicting concurrent step order")
    return merged


def merge_world_batch_plans(
    baseline: object, left: object, right: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world workflow merge requires operator authorization")
    base = replay_world_batch_plan(baseline, authorized=True)
    ours = replay_world_batch_plan(left, authorized=True)
    theirs = replay_world_batch_plan(right, authorized=True)
    plans = (base, ours, theirs)
    if any(plan["catalog_digest"] != base["catalog_digest"] for plan in plans):
        raise StudioQuestError("three-way merge crosses tool catalog epochs")
    if any(plan["provenance"]["projects"] != base["provenance"]["projects"]
           for plan in plans):
        raise StudioQuestError("three-way merge crosses canonical world sources")

    original = _requests(base)
    a = _requests(ours)
    b = _requests(theirs)
    prefix = len(original)
    if a[:prefix] != original or b[:prefix] != original:
        raise StudioQuestError("three-way merge refuses edits to the common ancestor")
    if len(a) < prefix or len(b) < prefix:
        raise StudioQuestError("three-way merge refuses ancestor deletions")

    # Repeated appended requests have no stable independent identity; they
    # cannot be safely deduplicated or reconciled without an authored ID.
    existing = {_digest(item) for item in original}
    left_suffix, right_suffix = a[prefix:], b[prefix:]
    for suffix in (left_suffix, right_suffix):
        digests = [_digest(item) for item in suffix]
        if len(set(digests)) != len(digests) or existing.intersection(digests):
            raise StudioQuestError("three-way merge refuses ambiguous repeated steps")

    # A concurrent change to the same project/tool slot is a semantic
    # conflict unless the requests are byte-for-byte canonical identical.
    # Different tools, or the same tool on different worlds, can coexist.
    left_slots = {_identity(item): _digest(item) for item in left_suffix}
    right_slots = {_identity(item): _digest(item) for item in right_suffix}
    if len(left_slots) != len(left_suffix) or len(right_slots) != len(right_suffix):
        raise StudioQuestError("three-way merge refuses duplicate semantic slots")
    for slot in left_slots.keys() & right_slots.keys():
        if left_slots[slot] != right_slots[slot]:
            raise StudioQuestError("three-way merge has conflicting concurrent authoring")

    appended = _merge_suffix_order(left_suffix, right_suffix)
    requests = original + appended
    if len(requests) > MAX_STEPS:
        raise StudioQuestError("three-way merge exceeds bounded execution steps")
    merged = compile_world_batch_plan(
        requests, authorized=True,
        expected_catalog_digest=base["catalog_digest"],
    )
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "catalog_digest": base["catalog_digest"],
        "source_projects": base["provenance"]["projects"],
        "baseline_plan_digest": base["plan_digest"],
        "left_plan_digest": ours["plan_digest"],
        "right_plan_digest": theirs["plan_digest"],
        "merged_plan_digest": merged["plan_digest"],
        "baseline_step_count": prefix,
        "left_appended_count": len(left_suffix),
        "right_appended_count": len(right_suffix),
        "unique_appended_count": len(appended),
        "merged_step_count": len(requests),
        "merge_policy": "append_only_same_canon_same_catalog_fail_closed",
        "ordering_policy": "stable_topological_preserve_both_forks",
        "ordered_append_digest": _digest(appended),
        "source_replay_verified": True,
        "file_write_performed": False,
        "native_runtime_verified": False,
        "release_certified": False,
    }
    if len(_canonical(receipt)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("three-way merge receipt exceeds byte budget")
    receipt["merge_digest"] = _digest(receipt)
    return {"receipt": receipt, "plan": merged}


def replay_world_batch_merge(
    result: object, baseline: object, left: object, right: object, *,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("three-way merge replay requires authorization")
    if (type(result) is not dict or set(result) != {"receipt", "plan"}
            or type(result["receipt"]) is not dict
            or result["receipt"].get("schema") != SCHEMA):
        raise StudioQuestError("invalid three-way merge receipt")
    verified = merge_world_batch_plans(
        baseline, left, right, authorized=True)
    if verified != result:
        raise StudioQuestError("three-way merge failed canonical replay")
    return verified


def propose_world_batch_merge(
    prompt: str, baseline: object, left: object, right: object, *,
    authorized: bool,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported typed three-way merge prompt")
    return merge_world_batch_plans(
        baseline, left, right, authorized=authorized)


def render_world_batch_merge_html(
    result: object, baseline: object, left: object, right: object, *,
    authorized: bool,
) -> bytes:
    verified = replay_world_batch_merge(
        result, baseline, left, right, authorized=authorized)
    receipt = verified["receipt"]
    rows = [
        ("Common ancestor", receipt["baseline_plan_digest"]),
        ("Left authored fork", receipt["left_plan_digest"]),
        ("Right authored fork", receipt["right_plan_digest"]),
        ("Merged typed plan", receipt["merged_plan_digest"]),
    ]
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        "base-uri 'none'; form-action 'none'; object-src 'none'\">"
        "<title>Canonical Jeeves workflow merge</title></head><body><main>"
        "<h1>Verified append-only world workflow merge</h1>"
        "<p>Source-replayed typed plan. No native runtime or release certification.</p>"
        "<dl>" + "".join(
            "<dt>" + escape(name, quote=True) + "</dt><dd>" +
            escape(digest, quote=True) + "</dd>" for name, digest in rows
        ) + "</dl><p>Independent appended steps: " +
        str(receipt["unique_appended_count"]) +
        "</p></main></body></html>"
    ).encode("utf-8")
    if len(html) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("three-way merge HTML exceeds byte budget")
    return html
