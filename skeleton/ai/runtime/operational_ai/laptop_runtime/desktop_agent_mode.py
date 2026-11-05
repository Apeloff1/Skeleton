"""Strict Jeeves agent tasks on the already live installed GGUF desktop worker.

Only the existing NativeJeevesRuntime + StrictJeevesAgentRuntime may plan,
verify and deliver answers. No second model, external tools, shell, network,
provider fallback, memory promotion or parallel SQLite ownership is added.
"""
from __future__ import annotations

from hashlib import sha256

from .contracts import identifier, nonnegative, utf8, refuse
from .identity import ActiveModel


class DesktopAgentHold(ValueError):
    """A desktop Jeeves reasoning run violated a finite native contract."""


def _bounded(value: object, *, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise DesktopAgentHold("invalid finite native agent " + label)
    return value


def run_agent(
    worker: object,
    source_fence: object,
    *,
    tenant: str,
    subject: str,
    prompt: str,
    run_id: str,
    maximum_steps: int = 8,
    maximum_model_calls: int = 8,
    maximum_wall_seconds: int = 180,
    signed_source: object | None = None,
    reasoning_profile: str = "guarded",
) -> dict[str, object]:
    """Run one native agent with either zero tools or an EXPLICIT signed read grant.

    The signed-source capability has been admitted *before* native activation
    and bound to the exact installed GGUF/tenant/tokenizer. The host grants
    only the canonical bounded READ_ONLY lookup tool for this one run;
    original file bytes and HMAC/expiry are reverified before and after.
    """
    # Delayed import preserves the cheap pure IPC admission boundary and
    # keeps canonical Jeeves ownership in its existing implementation.
    from skeleton.jeeves.agent.native_source_fence import NativeSourceFence
    from skeleton.jeeves.agent.native_runtime import NativeJeevesRuntime
    from skeleton.jeeves.agent.runtime import RunInputs
    from skeleton.jeeves.agent.tools import ToolRegistry
    from skeleton.jeeves.agent.native_source_tool import readonly_source_grant
    from skeleton.jeeves.agent.types import Goal, Budget
    from .desktop_signed_source import ActivatedSignedSource

    if type(source_fence) is not NativeSourceFence:
        raise DesktopAgentHold("canonical installed source guard required")
    checked_tenant = identifier(tenant, "tenant")
    checked_subject = identifier(subject, "subject")
    checked_id = identifier(run_id, "agent run ID")
    task = utf8(prompt, maximum=32768)
    steps = _bounded(maximum_steps, label="step bound", low=1, high=64)
    calls = _bounded(maximum_model_calls, label="model-call bound", low=1, high=64)
    seconds = _bounded(maximum_wall_seconds, label="wall budget", low=1, high=600)
    principal = ActiveModel.from_supervisor(worker)
    if (principal.tenant, principal.subject) != (checked_tenant, checked_subject):
        raise DesktopAgentHold("native agent worker belongs to another principal")
    source_fence.assert_live(worker)
    from .desktop_agent_profiles import choose_profile
    planned = choose_profile(
        name=reasoning_profile,
        native_max_output_tokens=worker.spine.limits.max_output_tokens,
        maximum_steps=steps,
        maximum_model_calls=calls,
        maximum_wall_seconds=seconds,
        signed_source_available=signed_source is not None,
    )
    if signed_source is not None and type(signed_source) is not ActivatedSignedSource:
        raise DesktopAgentHold("unrecognized or unsigned desktop source tool")
    tool_registry = ToolRegistry()
    grants = ()
    maximum_tool_calls = 0
    if signed_source is not None:
        signed_source.assert_current(worker)
        signed_source.bound_tool.install(tool_registry)
        maximum_tool_calls = signed_source.admission.maximum_tool_calls
        grants = (readonly_source_grant(maximum_calls=maximum_tool_calls),)
    if planned.name == "advanced":
        runtime = NativeJeevesRuntime(
            worker, tools=tool_registry, config=planned.config,
        )
    else:
        runtime = NativeJeevesRuntime(worker, tools=tool_registry)
    if (
        runtime.identity != principal
        or runtime.provider.name != "jeeves_native"
    ):
        raise DesktopAgentHold("native reasoning provider is not canonical")
    ceiling = worker.spine.limits.max_output_tokens
    if type(ceiling) is not int or not 1 <= ceiling <= 8192:
        raise DesktopAgentHold("native token budget unavailable")
    task_sha = sha256(task.encode("utf-8", "strict")).hexdigest()
    inputs = RunInputs(
        goal=Goal(
            goal_id="desktop_jeeves_" + task_sha[:24],
            objective=task,
            constraints=(
                "Use only the already installed local native provider.",
                "Do not execute shell commands, change files or infer tool authorization.",
                "Keep unverified assertions explicitly unresolved.",
            ),
        ),
        run_id=checked_id,
        tenant_id=checked_tenant,
        user_id=checked_subject,
        budget=Budget(
            max_steps=steps,
            max_model_calls=calls,
            max_tool_calls=maximum_tool_calls if maximum_tool_calls else 1,
            max_tokens=min(100000, ceiling * calls * 2),
            max_wall_seconds=seconds,
        ),
        preferred_provider="jeeves_native",
        grants=grants,
        confirmed_actions=(),
    )
    # NativeJeevesRuntime uses the *same* supervised model, canonical SQLite
    # and strict host-owned tool admission. A failed/uncertain request is
    # never retried here or promoted to a successful operator result.
    result = runtime.run(inputs)
    source_fence.assert_live(worker)
    if signed_source is not None:
        signed_source.assert_current(worker)
    if ActiveModel.from_supervisor(worker) != principal:
        raise DesktopAgentHold("principal drift after native agent execution")
    if (
        result.run_id != checked_id
        or result.goal_id != inputs.goal.goal_id
        or type(result.success) is not bool
        or result.usage.model_calls > calls
        or result.usage.steps > steps
        or result.usage.tool_calls > maximum_tool_calls
        or result.usage.tool_calls < 0
    ):
        raise DesktopAgentHold("strict native agent exceeded authorized execution")
    if result.success is not True:
        return {
            "schema": "jeeves.desktop.strict-agent.v1",
            "status": "held",
            "run_id": checked_id,
            "success": False,
            "termination_reason": result.reason.value,
            "model_sha256": principal.model_sha256,
            "release_certified": False,
            "device_qualified": False,
            "automatic_retry": False,
            "signed_source_tool_active": signed_source is not None,
            "tool_call_ceiling": maximum_tool_calls,
            "reasoning_profile": planned.name,
            "planning_policy": planned.to_public(),
        }
    answer = result.answer
    if type(answer) is not str:
        raise DesktopAgentHold("verified native agent answer must be UTF-8")
    try:
        raw = answer.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise DesktopAgentHold("native agent answer contains invalid Unicode") from exc
    if not 1 <= len(raw) <= 131072:
        raise DesktopAgentHold("verified native answer exceeds private byte limit")
    return {
        "schema": "jeeves.desktop.strict-agent.v1",
        "status": "verified",
        "run_id": checked_id,
        "success": True,
        "goal_id": result.goal_id,
        "model_sha256": principal.model_sha256,
        "answer": answer,
        "output_sha256": sha256(raw).hexdigest(),
        "termination_reason": result.reason.value,
        "trace_fingerprint": result.trace_fingerprint,
        "usage": {
            "model_calls": result.usage.model_calls,
            "prompt_tokens": result.usage.prompt_tokens,
            "completion_tokens": result.usage.completion_tokens,
            "tool_calls": result.usage.tool_calls,
            "steps": result.usage.steps,
        },
        "device_qualified": False,
        "release_certified": False,
        "automatic_retry": False,
        "filesystem_write_authorized": False,
        "reasoning_profile": planned.name,
        "planning_policy": planned.to_public(),
        "signed_source_tool_active": signed_source is not None,
        "tool_call_ceiling": maximum_tool_calls,
        "signed_source_manifest_sha256": (
            signed_source.admission.preflight.manifest_sha256
            if signed_source is not None else None
        ),
    }


__all__ = ["DesktopAgentHold", "run_agent"]
