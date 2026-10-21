"""Host-authorized, finite native Jeeves production execution with receipts.

The standalone Jeeves model proposes commands; this driver executes already
approved creator runbooks using exact one-shot host-issued ToolGrants. It NEVER
creates permission, installs handlers, invokes hosted AI or claims game release.

Every effect runs through CreatorRunbookRunner -> ToolExecutor, the immutable
CreatorRunbookStore revision chain, and the StudioEvidenceJournal. Unknown
external effects become IN_DOUBT, never unconditionally replayed.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from skeleton.jeeves.agent.tools import (
    ToolExecutionContext, ToolExecutor, ToolGrant,
)
from .creator_runbook_runtime import (
    CreatorRunbookError, RunbookState,
)
from .creator_runbook_store import CreatorRunbookStore
from .studio_interaction_contract import (
    JeevesStudioController, StudioInteractionError, canonical, digest,
)

MAX_BATCH_STEPS = 32


class StudioDelegationError(ValueError):
    """A production delegation cannot be safely authorized or replayed."""


def execute_approved_studio_batch(
    controller: JeevesStudioController, plan: Mapping[str, Any],
    *, executor: ToolExecutor, store: CreatorRunbookStore,
    host_grants: Mapping[str, tuple[ToolExecutionContext, ToolGrant]],
    max_steps: int = 8,
) -> dict[str, Any]:
    """Execute only explicitly granted ready steps, with complete host receipts.

    host_grants comes from trusted host code after approval; a model cannot
    supply one by writing JSON. A step without a grant remains pending.

    This deliberately does NOT hide uncertainty: one failed or indeterminate
    side effect ends the batch and needs independent later reconciliation.
    """
    if not isinstance(controller, JeevesStudioController):
        raise StudioDelegationError("host-owned Jeeves controller required")
    if not isinstance(executor, ToolExecutor):
        raise StudioDelegationError("host ToolExecutor required")
    if not isinstance(store, CreatorRunbookStore):
        raise StudioDelegationError("host-bound durable runbook store required")
    if not isinstance(host_grants, Mapping):
        raise StudioDelegationError("fresh host-issued grants must be a step map")
    if type(max_steps) is not int or not 1 <= max_steps <= MAX_BATCH_STEPS:
        raise StudioDelegationError("bounded number of authorized actions required")
    runner = controller.runner(plan, executor=executor, store=store)
    step_ids = {item.step_id for item in runner.plan.steps}
    if any(step not in step_ids for step in host_grants):
        raise StudioDelegationError("grant set references a foreign creator command")
    for step_id, credentials in host_grants.items():
        if not isinstance(credentials, tuple) or len(credentials) != 2:
            raise StudioDelegationError("host context and one-shot ToolGrant required")
        context, grant = credentials
        if not isinstance(context, ToolExecutionContext) or not isinstance(grant, ToolGrant):
            raise StudioDelegationError("untyped runbook execution authority")
    executed: list[dict[str, Any]] = []
    stopped = "batch_budget"
    initial = runner.snapshot()["head_digest"]
    for _ in range(max_steps):
        ready = runner.ready()
        if not ready:
            stopped = "no_ready_steps"
            break
        selected = next((step for step in ready if step in host_grants), None)
        if selected is None:
            stopped = "host_grant_required"
            break
        context, grant = host_grants[selected]
        try:
            outcome = runner.execute_step(selected, context=context, grant=grant)
        except Exception as exc:
            # The runner may already have persisted an IN_FLIGHT marker before
            # an external handler failed. Quarantine, never auto-retry.
            persisted = store.load()
            restored = persisted and next((
                step for step in persisted["steps"] if step["step_id"] == selected
            ), None)
            if restored and restored["status"] == RunbookState.IN_FLIGHT.value:
                observation = sha256(canonical({
                    "plan_sha256": runner.plan.plan_sha256,
                    "step_id": selected,
                    "failure_type": type(exc).__name__,
                    "effect_confirmed": False,
                    "automatic_retry": False,
                })).hexdigest()
                outcome = runner.reconcile_in_flight(
                    selected, evidence_digest=observation,
                    reason="unconfirmed_external_effect",
                )
            else:
                # No persisted dispatch: invalid grant or pre-effect failure.
                # Do not fabricate an execution journal entry.
                raise StudioDelegationError(
                    "creator operation was rejected before a verified execution outcome"
                ) from exc
        # The runner wrote actual result state before this auxiliary journal
        # references it. This observation cannot claim host completion by itself.
        recorded = controller.observe(runner=runner, store=store, step_id=selected)
        executed.append({
            "step_id": selected,
            "state": outcome.status.value,
            "attempts": outcome.attempts,
            "command_receipt_sha256": outcome.receipt_digest,
            "observation_sha256": outcome.observation_digest,
            "studio_event_sha256": recorded["digest"],
            "durable_runbook_state_sha256": runner.snapshot()["head_digest"],
        })
        if outcome.status is not RunbookState.SUCCEEDED:
            stopped = "external_effect_uncertain"
            break
    else:
        if not runner.ready():
            stopped = "no_ready_steps"
    final = runner.snapshot()
    body = {
        "schema_version": "skeleton.jeeves.studio_delegation_batch.v1",
        "project_id": controller.journal.project_id,
        "session_id": controller.journal.session_id,
        "plan_sha256": runner.plan.plan_sha256,
        "prior_runbook_state_sha256": initial,
        "runbook_state_sha256": final["head_digest"],
        "authorized_effects": executed,
        "completed_effects": sum(1 for item in executed
                                 if item["state"] == RunbookState.SUCCEEDED.value),
        "uncertain_effects": sum(1 for item in executed
                                 if item["state"] != RunbookState.SUCCEEDED.value),
        "remaining_ready_steps": list(runner.ready()),
        "stop_reason": stopped,
        "all_runbook_steps_succeeded": all(
            item["status"] == RunbookState.SUCCEEDED.value
            for item in final["steps"]
        ),
        "active_model_weights_modified": False,
        "game_release_certified": False,
    }
    body["batch_receipt_sha256"] = digest(body)
    return body


__all__ = ["execute_approved_studio_batch", "StudioDelegationError"]
