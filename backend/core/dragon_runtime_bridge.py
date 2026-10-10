"""Mount Dragon adapters on an existing application-owned global resource ledger.

No capacity discovery/grant creation, provider SDK, private scheduler or timer.
Configuration is explicit and cannot be supplied in an HTTP request body.
"""
from __future__ import annotations
from contextvars import ContextVar
from dataclasses import replace
from fastapi import Depends, HTTPException, Request
from routes.gameforge_auth import require_role
from skeleton.ai.webcrawler.dragon_execution_pool import DragonExecutionPool, DragonPoolCapacityError
from skeleton.ai.game_builder.resource_governor import ResourceEnvelope
from skeleton.ai.webcrawler.dragon_resource_session import plan_resources


_foreground_plan = ContextVar("dragon_foreground_resource_plan", default=None)


def dragon_context_budget(base):
    plan = _foreground_plan.get()
    if plan is None:
        return base
    total = min(base.max_context_tokens, max(2048, plan.context_bytes // 4))
    output = min(base.reserved_output_tokens, total // 4)
    policy = min(base.reserved_policy_tokens, total // 8)
    margin = min(base.safety_margin_tokens, total // 16)
    tools = min(base.reserved_tool_result_tokens, total // 8)
    segment = min(base.max_segment_tokens, total - output - policy - margin - tools)
    return replace(base, max_context_tokens=total, reserved_output_tokens=output, reserved_tool_result_tokens=tools,
        reserved_policy_tokens=policy, safety_margin_tokens=margin, max_segment_tokens=segment,
        max_artifact_tokens=min(base.max_artifact_tokens, segment),
        max_tool_result_tokens=min(base.max_tool_result_tokens, segment))


def install_dragon_runtime(app, shared_resources, envelope: ResourceEnvelope, **options):
    if getattr(app.state, "dragon_execution_pool", None) is not None or getattr(app.state, "dragon_practice_executor_factory", None) is not None:
        raise ValueError("Dragon runtime already mounted; cannot reset retained budgets")
    pool = DragonExecutionPool(shared_resources, envelope, **options)
    app.state.dragon_execution_pool = pool
    app.state.dragon_practice_executor_factory = pool.executor
    return pool


async def dragon_foreground(request: Request, user=Depends(require_role("viewer"))):
    pool = getattr(request.app.state, "dragon_execution_pool", None)
    if pool is None:
        yield  # Existing deployments remain compatible; guarded practice denies execution.
        return
    if not isinstance(pool, DragonExecutionPool):
        raise HTTPException(status_code=503, detail="Dragon resource runtime unavailable")
    # Reuse exactly the Academy's verified tenant/principal identity contract.
    from routes.dragon_academy import _principal
    owner = _principal(user)
    try:
        with pool.foreground(owner):
            plan = plan_resources(pool.hardware(), now=pool.clock(), foreground=True)
            if plan.effort == "defer":
                raise HTTPException(status_code=503, detail="Dragon hardware resources temporarily unavailable")
            token = _foreground_plan.set(plan)
            try:
                yield
            finally:
                _foreground_plan.reset(token)
    except DragonPoolCapacityError:
        raise HTTPException(status_code=503, detail="Dragon resource capacity unavailable") from None


def mount_configured_dragon_runtime(app, conversation_authority):
    """Lifespan hook: mount supplied canonical dependencies, never invent them."""
    from core.dragon_conversation_binding import DragonConversationBinding, install_dragon_conversation_binding
    scheduler = getattr(app.state, 'global_resource_scheduler', None)
    envelope = getattr(app.state, 'dragon_resource_envelope', None)
    pool = getattr(app.state, 'dragon_execution_pool', None)
    if scheduler is not None or envelope is not None:
        if pool is None:
            pool = install_dragon_runtime(app, scheduler, envelope)
        elif not isinstance(pool, DragonExecutionPool) or pool.shared_resources is not scheduler or pool.envelope != envelope:
            raise ValueError('Dragon lifespan cannot replace retained resource accounting')
    binding = getattr(app.state, 'dragon_conversation_binding', None)
    if binding is not None:
        if not isinstance(binding, DragonConversationBinding):
            raise ValueError('typed canonical-consent conversation binding required')
        existing = getattr(conversation_authority, 'dragon_projection', None)
        if existing is None:
            install_dragon_conversation_binding(conversation_authority, binding)
        elif existing is not binding:
            raise ValueError('Dragon lifespan cannot replace conversation retention binding')
    return {'resource_runtime_mounted': pool is not None,
            'conversation_binding_mounted': getattr(conversation_authority,'dragon_projection',None) is not None}
