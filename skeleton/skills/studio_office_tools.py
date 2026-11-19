"""Studio-office tools. Each one calls an existing owner and returns its output.

No provider SDK is imported here. A missing doctor, builder, job, or project
store is a failed tool result, not a guessed success.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from skeleton.forge.playtest import PLAYTEST_MODES
from skeleton.forge.playtest_agent import classify_godot_report, scripted_playtest


# Codes first_install_report already emits. Anything else collapses to the
# existing fail-closed doctor_unavailable code. Service redness stays on
# services_ready; it is not a new code.
_AI_FAILURE_CODES = frozenset({
    "local_model_not_configured",
    "local_configuration_invalid",
    "local_guard_unavailable",
    "local_guard_configuration_invalid",
})
_AI_READY_CODES = frozenset({
    "local_model_configured",
    "local_model_catalog_configured",
})
_FAIL_CLOSED_DOCTOR = "doctor_unavailable"


def doctor_codes(report: Mapping[str, Any]) -> list[str]:
    """Collect named codes the doctor report already carries.

    Unknown strings are replaced with ``doctor_unavailable``. A red service
    probe stays ``services_ready is False`` and does not invent a code.
    """
    codes: list[str] = []
    unknown = False
    ai = report.get("ai")
    if isinstance(ai, Mapping):
        for key in ("configuration_code", "readiness_code"):
            value = ai.get(key)
            if not isinstance(value, str) or not value or value in _AI_READY_CODES:
                continue
            if value in _AI_FAILURE_CODES:
                codes.append(value)
            else:
                unknown = True
    checks = report.get("checks")
    groups = checks.values() if isinstance(checks, Mapping) else ()
    for group in groups:
        if not isinstance(group, list):
            continue
        for row in group:
            if not isinstance(row, Mapping) or row.get("ok") is not False:
                continue
            code = row.get("code")
            if isinstance(code, str) and code:
                codes.append(code)
            elif row.get("code") not in (None, ""):
                unknown = True
    if unknown:
        codes.append(_FAIL_CLOSED_DOCTOR)
    seen: list[str] = []
    for code in codes:
        if code not in seen:
            seen.append(code)
    return seen[:32]


def doctor_is_green(report: Mapping[str, Any]) -> bool:
    """Green means the install doctor did not report a blocking failure.

    ``services_ready is None`` is the offline doctor (live probes were not
    asked). ``False`` is a red service probe and blocks the golden brief.
    """
    return (
        report.get("platform_ready") is True
        and report.get("configuration_ready") is True
        and report.get("services_ready") is not False
    )


def _summarize_doctor(report: Mapping[str, Any]) -> dict[str, Any]:
    codes = doctor_codes(report)
    return {
        "ok": True,
        "green": doctor_is_green(report),
        "codes": codes,
        "platform_ready": report.get("platform_ready"),
        "configuration_ready": report.get("configuration_ready"),
        "services_ready": report.get("services_ready"),
        "schema_version": report.get("schema_version"),
    }


def tool_doctor(*, live: bool = False, timeout: float = 3.0, report_fn: Callable[..., Mapping[str, Any]] | None = None, **_: Any) -> dict[str, Any]:
    """Call ``first_install_report``. Live probes stay opt-in."""
    if live is not True and live is not False:
        return {"ok": False, "green": False, "code": "doctor_input_invalid", "codes": ["doctor_input_invalid"]}
    fn = report_fn
    if fn is None:
        from skeleton.app.first_install import first_install_report

        fn = first_install_report
    try:
        report = fn(live=live, timeout=timeout if live else 3.0)
    except (OSError, ValueError, TypeError) as exc:
        return {
            "ok": False,
            "green": False,
            "code": "doctor_unavailable",
            "codes": ["doctor_unavailable"],
            "error": type(exc).__name__,
        }
    if not isinstance(report, Mapping):
        return {"ok": False, "green": False, "code": "doctor_unavailable", "codes": ["doctor_unavailable"]}
    return _summarize_doctor(report)


def tool_game_build(
    *,
    brief: Any,
    playtest: str = "auto",
    actor_id: str | None = None,
    tenant_id: str | None = None,
    deadline_s: float | None = None,
    on_progress: Callable[[float, str], None] | None = None,
    builder: Callable[..., Mapping[str, Any]] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Call ``build_playable_game``. Do not materialise a second compiler."""
    if playtest not in PLAYTEST_MODES:
        return {"ok": False, "code": "playtest_mode_invalid", "godot_ran": False, "core_loop_ok": False, "degraded": False}
    fn = builder
    if fn is None:
        from skeleton.forge.game_builder import build_playable_game

        fn = build_playable_game
    try:
        result = fn(
            brief,
            playtest_mode=playtest,
            actor_id=actor_id,
            tenant_id=tenant_id,
            deadline_s=deadline_s,
            on_progress=on_progress,
        )
    except ValueError as exc:
        return {
            "ok": False,
            "code": "game_build_rejected",
            "error": str(exc)[:300],
            "godot_ran": False,
            "core_loop_ok": False,
            "degraded": False,
        }
    except Exception as exc:
        return {
            "ok": False,
            "code": "game_build_unavailable",
            "error": type(exc).__name__,
            "godot_ran": False,
            "core_loop_ok": False,
            "degraded": False,
        }
    if not isinstance(result, Mapping):
        return {"ok": False, "code": "game_build_unavailable", "godot_ran": False, "core_loop_ok": False, "degraded": False}
    playtest_report = result.get("playtest") if isinstance(result.get("playtest"), Mapping) else None
    classified = classify_godot_report(playtest_report)
    agent = None
    if isinstance(playtest_report, Mapping) and isinstance(playtest_report.get("agent"), Mapping):
        agent = playtest_report.get("agent")
    elif isinstance(result.get("playtest_agent"), Mapping):
        agent = result.get("playtest_agent")
    taxonomy = agent.get("taxonomy") if isinstance(agent, Mapping) else None
    ok = result.get("ok") is True
    return {
        "ok": ok,
        "code": None if ok else "game_build_failed",
        "godot_ran": classified["godot_ran"],
        "core_loop_ok": classified["core_loop_ok"] if ok else False,
        "degraded": bool(ok and classified["degraded"]),
        "degraded_reason": classified["degraded_reason"] if ok and classified["degraded"] else classified["degraded_reason"],
        "playtest_status": classified["playtest_status"],
        "compiler_marker": result.get("marker") if isinstance(result.get("marker"), str) else None,
        "execution_id": result.get("execution_id") if isinstance(result.get("execution_id"), str) else None,
        "agent_taxonomy": taxonomy if isinstance(taxonomy, str) else None,
        "error": None if ok else str(result.get("error") or "proof failed")[:300],
    }


def tool_job_status(*, execution_id: str | None = None, actor_id: str | None = None, tenant_id: str | None = None, view_fn: Callable[..., Mapping[str, Any]] | None = None, **_: Any) -> dict[str, Any]:
    """Read one forge build through ``execution_view``."""
    if not isinstance(execution_id, str) or not execution_id:
        return {"ok": False, "code": "execution_required"}
    fn = view_fn
    if fn is None:
        from skeleton.forge.game_build_queue import execution_view

        fn = execution_view
    try:
        view = fn(execution_id, actor_id=actor_id, tenant_id=tenant_id)
    except KeyError:
        return {"ok": False, "code": "job_not_found", "execution_id": execution_id}
    except Exception as exc:
        return {"ok": False, "code": "job_unavailable", "execution_id": execution_id, "error": type(exc).__name__}
    if not isinstance(view, Mapping):
        return {"ok": False, "code": "job_unavailable", "execution_id": execution_id}
    result = view.get("result") if isinstance(view.get("result"), Mapping) else None
    public_result = None
    if result is not None:
        playtest_report = result.get("playtest") if isinstance(result.get("playtest"), Mapping) else None
        public_result = {
            "ok": result.get("ok"),
            "marker": result.get("marker") if isinstance(result.get("marker"), str) else None,
            "playtest_status": playtest_report.get("status") if playtest_report is not None else None,
        }
    return {
        "ok": True,
        "code": None,
        "execution_id": execution_id,
        "job_id": view.get("job_id"),
        "status": view.get("status"),
        "progress": view.get("progress"),
        "message": str(view.get("message") or "")[:240],
        "result": public_result,
        "error": view.get("error"),
    }


def tool_list_projects(*, actor_id: str | None = None, tenant_id: str | None = None, db: Any = None, **_: Any) -> dict[str, Any]:
    """List projects from ``ProjectsV1Store`` when that store is actually present."""
    if not actor_id or not tenant_id:
        return {"ok": False, "code": "projects_unavailable", "items": []}
    if db is None:
        try:
            from skeleton.app_services.runtime import get_app_services

            db = get_app_services().db
        except Exception as exc:
            return {"ok": False, "code": "projects_unavailable", "items": [], "error": type(exc).__name__}
    try:
        from skeleton.persistence.app_foundation.projects_v1 import ProjectsV1Store

        items, nxt = ProjectsV1Store(db).list(actor_id, tenant_id, 20, None)
    except Exception as exc:
        return {"ok": False, "code": "projects_unavailable", "items": [], "error": type(exc).__name__}
    public: list[dict[str, str]] = []
    for project in items:
        title = ""
        brief = getattr(project, "brief", None)
        if brief is not None and getattr(brief, "title", None):
            title = str(brief.title)[:120]
        project_id = str(getattr(project, "project_id", "") or "")
        if project_id:
            public.append({"project_id": project_id, "title": title})
    return {"ok": True, "code": None, "items": public, "next_cursor": nxt}


def tool_playtest(
    *,
    genre: str | None = None,
    content: Mapping[str, Any] | None = None,
    frames: int = 4,
    playtest_report: Mapping[str, Any] | None = None,
    require_godot: bool = False,
    **_: Any,
) -> dict[str, Any]:
    """Run the scripted agent. ``require_godot`` fails closed when Godot did not boot."""
    try:
        agent = scripted_playtest(content if isinstance(content, Mapping) else {}, str(genre or ""), frames=frames)
    except (TypeError, ValueError) as exc:
        return {
            "ok": False,
            "code": "input_rejected",
            "error": str(exc)[:200],
            "godot_ran": False,
            "core_loop_ok": False,
            "degraded": False,
            "agent_taxonomy": "input_rejected",
        }
    godot = classify_godot_report(playtest_report if isinstance(playtest_report, Mapping) else None)
    if require_godot and godot["godot_ran"] is not True:
        return {
            "ok": False,
            "code": "godot_unavailable",
            "agent_taxonomy": agent["taxonomy"],
            "repair_codes": agent["repair_codes"],
            **godot,
        }
    if agent["taxonomy"] != "passed":
        return {
            "ok": False,
            "code": agent["taxonomy"],
            "agent_taxonomy": agent["taxonomy"],
            "repair_codes": agent["repair_codes"],
            "frames_run": agent["frames_run"],
            **godot,
        }
    return {
        "ok": True,
        "code": "passed",
        "agent_taxonomy": "passed",
        "repair_codes": agent["repair_codes"],
        "frames_run": agent["frames_run"],
        "compiler_marker": agent.get("marker"),
        **godot,
    }


def default_tools() -> dict[str, Callable[..., dict[str, Any]]]:
    return {
        "doctor": tool_doctor,
        "game_build": tool_game_build,
        "job_status": tool_job_status,
        "list_projects": tool_list_projects,
        "playtest": tool_playtest,
    }


__all__ = [
    "default_tools",
    "doctor_codes",
    "doctor_is_green",
    "tool_doctor",
    "tool_game_build",
    "tool_job_status",
    "tool_list_projects",
    "tool_playtest",
]
