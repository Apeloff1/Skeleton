"""Bounded batch execution of existing non-mutating Jeeves game-studio adapters.

This is an ergonomic composition layer, not a tool executor, security context,
execution service, authority registry, or replacement for canonical adapters.
Every subaction is dispatched through the same JeevesAppwideRuntime.invoke
boundary that a single user action uses. Only allow-listed side-effect-free
catalog, preview and simulation actions may enter a batch.
"""
from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING, Any

from .jeeves_appwide_fabric import (
    JeevesAppwideError, canonical, digest, OPERATIONS,
)

if TYPE_CHECKING:
    from .jeeves_appwide_fabric import JeevesAppwideRuntime

SCHEMA = "skeleton.ai.jeeves_batch_preview.v1"
MAX_JOBS = 12
MAX_RESPONSE_BYTES = 500_000
MAX_SUBRESPONSE_BYTES = 120_000
MAX_INPUT_BYTES = 250_000

# Reviewed compute/read actions only. Do not infer eligibility from a model,
# a tool registry entry, a file name, or a new action being registered.
ALLOW = frozenset({
    "inventory.report",
    "inventory.search",
    "editor.catalog",
    "editor.preview",
    "editor.template",
    "director.rpg",
    "director.world",
    "forge.tools",
    "forge.kinds",
    "forge.graph",
    "companion.visual",
    "companion.simulate",
    "crawler.plan",
    "crawler.catalog",
    "tool.fabric",
    "studio.tree",
    "studio.file",
})


def _plain_dictionary(value: Any, *, label: str) -> dict:
    if type(value) is not dict:
        raise JeevesAppwideError(label + " must be an object")
    if any(type(key) is not str or len(key) > 128 for key in value):
        raise JeevesAppwideError(label + " contains noncanonical parameter keys")
    return value


def _admit(runtime: "JeevesAppwideRuntime", request: Any) -> list[dict]:
    params = _plain_dictionary(request, label="batch parameters")
    if set(params) != {"jobs"}:
        raise JeevesAppwideError("batch accepts only a jobs array")
    jobs = params["jobs"]
    if type(jobs) is not list or not 1 <= len(jobs) <= MAX_JOBS:
        raise JeevesAppwideError("1–12 bounded batch jobs required")
    if len(canonical(params).encode("utf-8")) > MAX_INPUT_BYTES:
        raise JeevesAppwideError("batch input too large")
    approved = []
    seen = set()
    for position, raw in enumerate(jobs):
        row = _plain_dictionary(raw, label="batch job")
        if set(row) != {"action", "params"}:
            raise JeevesAppwideError("batch job must contain action and params only")
        action = row["action"]
        arguments = _plain_dictionary(row["params"], label="batch job params")
        if type(action) is not str or action not in ALLOW:
            raise JeevesAppwideError("batch contains an unreviewed or effectful adapter")
        declared = OPERATIONS.get(action)
        if declared is None or declared[0] not in ("read", "compute") or declared[2]:
            raise JeevesAppwideError("batch subaction has effect or operator gate")
        if action in ("studio.file", "studio.tree", "forge.kinds",
                      "forge.graph", "companion.simulate",
                      "crawler.catalog", "tool.fabric"):
            # The underlying canonical adapters also enforce the active
            # project. This prevents a batch with mixed project authority.
            active = runtime.workspace.active() if runtime.workspace is not None else None
            if active is None or arguments.get("project") != active:
                raise JeevesAppwideError("batch requires same active project for scoped action")
        key = digest({"action": action, "params": arguments})
        if key in seen:
            raise JeevesAppwideError("duplicate identical preview in one batch")
        seen.add(key)
        approved.append({
            "position": position, "action": action,
            "params": arguments, "request_digest": key,
        })
    return approved


def run_batch_preview(runtime: "JeevesAppwideRuntime",
                      params: dict[str, Any]) -> dict:
    """Preflight *all* jobs, then invoke existing adapters sequentially.

    No optional 'authorized' switch is accepted here. All nested invocations
    must remain safely read/compute-only and use the existing authority
    boundary; this does not provide a shortcut to compiler writes, shell
    actions, source proposals, tool plans, approvals or learning promotion.
    """
    admitted = _admit(runtime, params)
    receipts = []
    output_bytes = 0
    truncated = 0
    for job in admitted:
        # Intentional use of ordinary canonical invoke: the batch must never
        # make private executor calls that bypass production adapter guards.
        try:
            sub = runtime.invoke(job["action"], job["params"], authorized=False)
        except (JeevesAppwideError, PermissionError, ValueError, TypeError, KeyError):
            # No partially committed batch state exists: every allowed
            # subaction was preflighted as read/compute-only.
            raise JeevesAppwideError(
                "batch subaction failed at position " + str(job["position"])
            ) from None
        raw = canonical(sub)
        size = len(raw.encode("utf-8"))
        payload = sub.get("result")
        # Always retain audit digests even for a clipped preview.
        if size > MAX_SUBRESPONSE_BYTES or output_bytes + size > MAX_RESPONSE_BYTES:
            payload = None
            truncated += 1
        else:
            output_bytes += size
        receipts.append({
            "position": job["position"],
            "action": job["action"],
            "request_digest": job["request_digest"],
            "canonical_action_receipt": sub.get("digest"),
            "canonical_result_digest": digest(sub.get("result")),
            "canonical_response_bytes": size,
            "result": payload,
            "result_omitted_for_budget": payload is None,
            "effect": OPERATIONS[job["action"]][0],
        })
    body = {
        "schema": SCHEMA,
        "inventory_snapshot": runtime.inventory._digest,
        "job_count": len(admitted),
        "jobs": receipts,
        "outbound_result_bytes": output_bytes,
        "omitted_large_results": truncated,
        "max_response_bytes": MAX_RESPONSE_BYTES,
        "only_canonical_read_or_compute_adapters": True,
        "project_authority_not_widened": True,
        "source_edits_performed": False,
        "code_committed": False,
        "automatic_model_weights_updated": False,
        "tools_dispatched": False,
        "operator_approval_inferred": False,
    }
    return {**body, "digest": digest(body)}
