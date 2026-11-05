"""Operator-controlled cold-restart-safe Jeeves work on canonical SQLite.

This is an interface to the existing NativeDurableJeevesAgent, not a new
checkpoint store or alternate model provider. No tool grants, shell,
network, automatic replay/resume or secret disclosure are introduced.
"""
from __future__ import annotations

from hashlib import sha256

from .contracts import identifier, utf8
from .identity import ActiveModel


class DesktopDurableHold(ValueError):
    """A durable model task cannot proceed under the supplied source custody."""


_ACTIONS = frozenset(("start", "inspect", "resume", "replay"))


def _limit(value: object, *, name: str, upper: int) -> int:
    if type(value) is not int or not 1 <= value <= upper:
        raise DesktopDurableHold("invalid finite durable " + name)
    return value


def _trusted_reply(
    record: object, *, run_id: str, goal_id: str,
    model_sha256: str, replayed: bool,
) -> dict[str, object]:
    """Project a canonical terminal result into one bounded source record."""
    if (
        type(record) is not dict
        or record.get("schema") != "jeeves.native_terminal_result.v1"
        or record.get("run_id") != run_id
        or record.get("goal_id") != goal_id
        or record.get("model_sha256") != model_sha256
        or type(record.get("success")) is not bool
        or record.get("release_certified") is not False
        or record.get("device_qualified") is not False
        or type(record.get("replayed")) is not bool
        or record.get("replayed") != replayed
        or type(record.get("usage")) is not dict
        or record["usage"].get("tool_calls") != 0
    ):
        raise DesktopDurableHold("canonical terminal SQLite source or rights mismatch")
    answer = record.get("answer")
    if type(answer) is not str:
        raise DesktopDurableHold("terminal answer must be exact UTF-8")
    try:
        raw = answer.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise DesktopDurableHold("invalid terminal answer Unicode") from exc
    if len(raw) > 131072:
        raise DesktopDurableHold("unbounded terminal answer")
    return {
        "success": record["success"],
        "answer": answer if record["success"] else "",
        "output_sha256": sha256(raw).hexdigest() if record["success"] else "",
        "termination_reason": record.get("reason"),
        "trace_fingerprint": record.get("trace_fingerprint"),
        "usage": record["usage"],
        "replayed_without_native_generation": replayed,
    }


def run_durable(
    worker: object,
    source_fence: object,
    *,
    action: str,
    tenant: str,
    subject: str,
    task: str,
    run_id: str,
    maximum_steps: int = 8,
    maximum_model_calls: int = 8,
    maximum_wall_seconds: int = 180,
) -> dict[str, object]:
    """Execute an explicit durable run action on one source-fenced GGUF.

    Every request requires the *original exact* task and budgets. On cold
    reopen, the authoritative checkpoint journal independently rebinds all
    fields to one model/tokenizer/tenant/subject. Wrong or changed data are
    denied, not silently repaired or regenerated.
    """
    from skeleton.jeeves.agent.native_source_fence import NativeSourceFence
    from skeleton.jeeves.agent.native_durable_runtime import NativeDurableJeevesAgent
    from skeleton.jeeves.agent.runtime import RunInputs
    from skeleton.jeeves.agent.types import Goal, Budget

    if type(action) is not str or action not in _ACTIONS:
        raise DesktopDurableHold("unknown explicit durable operator action")
    if type(source_fence) is not NativeSourceFence:
        raise DesktopDurableHold("source-fenced canonical native worker required")
    owner = identifier(tenant, "tenant")
    subject_id = identifier(subject, "subject")
    run = identifier(run_id, "durable run ID")
    original = utf8(task, maximum=32768)
    steps = _limit(maximum_steps, name="step ceiling", upper=64)
    calls = _limit(maximum_model_calls, name="native-call ceiling", upper=64)
    wall = _limit(maximum_wall_seconds, name="wall clock ceiling", upper=600)
    principal = ActiveModel.from_supervisor(worker)
    if (principal.tenant, principal.subject) != (owner, subject_id):
        raise DesktopDurableHold("durable native worker belongs to another owner")
    source_fence.assert_live(worker)
    output_ceiling = worker.spine.limits.max_output_tokens
    if type(output_ceiling) is not int or not 1 <= output_ceiling <= 8192:
        raise DesktopDurableHold("real native output capacity unavailable")
    task_digest = sha256(original.encode("utf-8", "strict")).hexdigest()
    goal_id = "desktop_work_" + task_digest[:24]
    inputs = RunInputs(
        goal=Goal(
            goal_id=goal_id,
            objective=original,
            constraints=(
                "Local native GGUF only; no remote providers.",
                "No file, network, command or third-party tool grants.",
                "Report unresolved steps instead of inventing completion.",
            ),
        ),
        tenant_id=owner,
        user_id=subject_id,
        run_id=run,
        budget=Budget(
            max_steps=steps, max_model_calls=calls,
            max_tool_calls=1,
            max_tokens=min(100000, output_ceiling * calls * 2),
            max_wall_seconds=wall,
        ),
        preferred_provider="jeeves_native",
        grants=(),
        confirmed_actions=(),
    )
    agent = NativeDurableJeevesAgent(worker)
    if (
        agent.identity != principal
        or agent.worker is not worker
    ):
        raise DesktopDurableHold("durable agent worker/source changed")
    if action == "start":
        result = agent.run(inputs)
    elif action == "resume":
        # Explicit operator action only. The canonical journal verifies the
        # complete snapshot, refuses unknown pending native inference and
        # prevents concurrent cold-reopen mutation with SessionGate.
        result = agent.resume_operator_approved(inputs)
    elif action == "inspect":
        snapshot = agent.inspect(inputs)
        source_fence.assert_live(worker)
        if (
            type(snapshot) is not dict
            or snapshot.get("schema") != "jeeves.native_durable_run.v1"
            or snapshot.get("run_id") != run
            or snapshot.get("goal_id") != goal_id
            or snapshot.get("model_sha256") != principal.model_sha256
            or snapshot.get("device_qualified") is not False
            or snapshot.get("release_certified") is not False
        ):
            raise DesktopDurableHold("untrusted read-only durable checkpoint inspection")
        return {
            "schema": "jeeves.desktop.durable-work.v1",
            "status": "inspected",
            "action": action, "run_id": run,
            "model_sha256": principal.model_sha256,
            "snapshot": snapshot,
            "native_generation_executed": False,
            "automatic_resume": False,
            "release_certified": False,
            "device_qualified": False,
        }
    else:
        sealed = agent.replay_terminal(inputs)
        source_fence.assert_live(worker)
        record = _trusted_reply(
            sealed, run_id=run, goal_id=goal_id,
            model_sha256=principal.model_sha256,
            replayed=True,
        )
        return {
            "schema": "jeeves.desktop.durable-work.v1",
            "status": "terminal-replayed" if record["success"] else "terminal-held",
            "action": action, "run_id": run,
            "model_sha256": principal.model_sha256,
            **record,
            "native_generation_executed": False,
            "automatic_resume": False,
            "release_certified": False,
            "device_qualified": False,
        }

    source_fence.assert_live(worker)
    if ActiveModel.from_supervisor(worker) != principal:
        raise DesktopDurableHold("durable native principal changed during execution")
    if (
        result.run_id != run
        or result.goal_id != goal_id
        or type(result.success) is not bool
        or result.usage.model_calls > calls
        or result.usage.steps > steps
        or result.usage.tool_calls != 0
    ):
        raise DesktopDurableHold("durable native result is not authorized")
    if result.success is not True:
        return {
            "schema": "jeeves.desktop.durable-work.v1",
            "status": "held", "action": action,
            "run_id": run,
            "model_sha256": principal.model_sha256,
            "success": False,
            "automatic_resume": False,
            "release_certified": False,
            "device_qualified": False,
        }
    answer = result.answer
    if type(answer) is not str:
        raise DesktopDurableHold("verified durable answer not UTF-8")
    try:
        raw = answer.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise DesktopDurableHold("invalid durable answer Unicode") from exc
    if not 1 <= len(raw) <= 131072:
        raise DesktopDurableHold("durable terminal answer out of finite limit")
    return {
        "schema": "jeeves.desktop.durable-work.v1",
        "status": "terminal-committed",
        "action": action, "run_id": run,
        "model_sha256": principal.model_sha256,
        "success": True,
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
        "native_generation_executed": True,
        "automatic_resume": False,
        "release_certified": False,
        "device_qualified": False,
    }


__all__ = ["DesktopDurableHold", "run_durable"]
