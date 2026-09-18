"""Security regressions for public HTTP error envelopes and crash redaction."""
from __future__ import annotations

import asyncio
import ast
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.http_errors import (  # noqa: E402
    PUBLIC_INTERNAL_ERROR,
    install_public_error_handlers,
    internal_http_error,
    public_http_error,
    redact_client_payload,
    redact_client_text,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE_FILES = [
    REPO_ROOT / "backend" / "routes" / "jeeves_tutor.py",
    REPO_ROOT / "backend" / "routes" / "npc_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "music_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "image_generation.py",
    REPO_ROOT / "backend" / "routes" / "export_github.py",
    REPO_ROOT / "backend" / "routes" / "gameforge_workflow.py",
    REPO_ROOT / "backend" / "routes" / "omega_conductor.py",
    REPO_ROOT / "backend" / "routes" / "interactive_education.py",
    REPO_ROOT / "backend" / "routes" / "ai_bible_enhanced.py",
    REPO_ROOT / "backend" / "routes" / "animation_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "game_logic_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "code_to_app_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "hybrid_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "interactive_narrative_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "lafs.py",
    REPO_ROOT / "backend" / "routes" / "galaxy_studio_catalogs.py",
    REPO_ROOT / "backend" / "routes" / "galaxy_studio_vault_admin.py",
    REPO_ROOT / "backend" / "routes" / "narrative_engine.py",
    REPO_ROOT / "backend" / "routes" / "logic_engine.py",
    REPO_ROOT / "backend" / "routes" / "world_engine.py",
    REPO_ROOT / "backend" / "routes" / "behaviour_npc_memory_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "world_models_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "testing_qa_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "server_backend_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "world_management_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "vfx_materials_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "monetization_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "neural_rendering_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "hardware_optimization_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "economy_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "director_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "bot_persona_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "action_gameplay_pipeline.py",
    REPO_ROOT / "backend" / "routes" / "worldforge.py",
    REPO_ROOT / "backend" / "routes" / "worldforge_publish.py",
]
SERVER_ERROR_FILES = [
    REPO_ROOT / "backend" / "routes" / "ops.py",
    REPO_ROOT / "backend" / "routes" / "deployment_checkpoint_trust.py",
    REPO_ROOT / "backend" / "routes" / "nexus.py",
    REPO_ROOT / "backend" / "routes" / "galaxy_studio.py",
]
JSON_ENVELOPE_FILES = [
    REPO_ROOT / "backend" / "routes" / "asset_genesis.py",
    REPO_ROOT / "backend" / "routes" / "galaxy_studio_files.py",
    REPO_ROOT / "backend" / "routes" / "jeeves_master_build.py",
    REPO_ROOT / "backend" / "routes" / "galaxy_studio.py",
    REPO_ROOT / "backend" / "routes" / "galaxy_studio_flair.py",
    REPO_ROOT / "backend" / "routes" / "galaxy_studio_ml_config.py",
    REPO_ROOT / "backend" / "routes" / "galaxy_studio_watchdog.py",
    REPO_ROOT / "backend" / "routes" / "galaxy_studio_eas.py",
    REPO_ROOT / "backend" / "routes" / "galaxy_studio_admin.py",
    REPO_ROOT / "backend" / "routes" / "galaxy_studio_code_library.py",
    REPO_ROOT / "backend" / "routes" / "galaxy_studio_mega_dbs.py",
    REPO_ROOT / "backend" / "routes" / "sota_2026.py",
    REPO_ROOT / "backend" / "routes" / "rosetta_challenge.py",
    REPO_ROOT / "backend" / "routes" / "multi_agent.py",
    REPO_ROOT / "backend" / "routes" / "marketplace.py",
    REPO_ROOT / "backend" / "routes" / "game_shared.py",
    REPO_ROOT / "backend" / "routes" / "game_factory.py",
    REPO_ROOT / "backend" / "routes" / "code_playground.py",
    REPO_ROOT / "backend" / "routes" / "camera_director.py",
    REPO_ROOT / "backend" / "routes" / "curriculum.py",
    REPO_ROOT / "backend" / "routes" / "agent_knowledge.py",
    REPO_ROOT / "backend" / "routes" / "photoreal.py",
    REPO_ROOT / "backend" / "routes" / "playable_polish.py",
    REPO_ROOT / "backend" / "routes" / "groupchat.py",
    REPO_ROOT / "backend" / "routes" / "playable.py",
    REPO_ROOT / "backend" / "routes" / "discourse.py",
    REPO_ROOT / "backend" / "routes" / "jeeves_core.py",
    REPO_ROOT / "backend" / "routes" / "jeeves_voice.py",
    REPO_ROOT / "backend" / "routes" / "jeeves_game_builder.py",
    REPO_ROOT / "backend" / "routes" / "game_command_agents.py",
    REPO_ROOT / "backend" / "routes" / "creator_economy.py",
    REPO_ROOT / "backend" / "routes" / "snowball.py",
    REPO_ROOT / "backend" / "routes" / "nexus.py",
    REPO_ROOT / "backend" / "routes" / "gameforge_studio.py",
    REPO_ROOT / "backend" / "routes" / "gameforge_cns.py",
    REPO_ROOT / "backend" / "routes" / "gameforge_runtime.py",
    REPO_ROOT / "backend" / "routes" / "apk_inspector.py",
    REPO_ROOT / "backend" / "routes" / "llm_router.py",
    REPO_ROOT / "backend" / "routes" / "expo_flaps.py",
    REPO_ROOT / "backend" / "routes" / "godot_engine.py",
    REPO_ROOT / "backend" / "services" / "game_llm_service.py",
    REPO_ROOT / "backend" / "services" / "ai_hub_svc.py",
    REPO_ROOT / "backend" / "services" / "tool_registry.py",
    REPO_ROOT / "backend" / "core" / "narrative_vault.py",
    REPO_ROOT / "backend" / "core" / "provenance_ledger.py",
    REPO_ROOT / "backend" / "core" / "autonomous_orchestrator.py",
    REPO_ROOT / "backend" / "core" / "runtime_health.py",
    REPO_ROOT / "backend" / "core" / "control_plane.py",
    REPO_ROOT / "backend" / "core" / "feature_flags_audit.py",
    REPO_ROOT / "backend" / "core" / "feature_flags_metrics.py",
    REPO_ROOT / "backend" / "core" / "unbulk.py",
    REPO_ROOT / "backend" / "core" / "mongo_guard.py",
    REPO_ROOT / "backend" / "core" / "churn_2_service.py",
    REPO_ROOT / "backend" / "core" / "scheduler.py",
    REPO_ROOT / "backend" / "gameforge" / "rooms" / "room_api_gateway.py",
    REPO_ROOT / "backend" / "gameforge" / "knowledge" / "free_apis.py",
    REPO_ROOT / "backend" / "gameforge" / "omega" / "integration.py",
    REPO_ROOT / "backend" / "gameforge" / "jeeves" / "jeeves_self_training.py",
    REPO_ROOT / "backend" / "gameforge" / "api" / "control.py",
    REPO_ROOT / "backend" / "gameforge" / "api" / "scim.py",
    REPO_ROOT / "backend" / "gameforge" / "godot_engine" / "binary.py",
    REPO_ROOT / "backend" / "core" / "boot_stages.py",
    REPO_ROOT / "backend" / "core" / "routes_registry.py",
    REPO_ROOT / "backend" / "core" / "truth_watch.py",
    REPO_ROOT / "backend" / "gameforge" / "godot_engine" / "health.py",
    REPO_ROOT / "backend" / "gameforge" / "enterprise" / "backup.py",
    REPO_ROOT / "backend" / "gameforge" / "exocortex" / "neuro_layers.py",
    REPO_ROOT / "backend" / "gameforge" / "prood" / "saga_orchestrator.py",
    REPO_ROOT / "backend" / "gameforge" / "prood" / "event_bus.py",
    REPO_ROOT / "backend" / "gameforge" / "persistence" / "chronoback.py",
    REPO_ROOT / "backend" / "routes" / "gameforge_build.py",
    REPO_ROOT / "backend" / "core" / "idle_curiosity_runtime.py",
    REPO_ROOT / "backend" / "gameforge" / "godot_engine" / "pipeline.py",
    REPO_ROOT / "backend" / "routes" / "jeeves_persona.py",
    REPO_ROOT / "backend" / "routes" / "playable_derive.py",
    REPO_ROOT / "backend" / "core" / "reliability.py",
    REPO_ROOT / "backend" / "core" / "cold_storage.py",
    REPO_ROOT / "backend" / "gameforge" / "enterprise" / "backup_scheduler.py",
    REPO_ROOT / "backend" / "routes" / "jeeves_media.py",
    REPO_ROOT / "backend" / "routes" / "final_build.py",
    REPO_ROOT / "backend" / "core" / "swarm_scheduler.py",
    REPO_ROOT / "backend" / "routes" / "galaxy_studio_agents.py",
    REPO_ROOT / "backend" / "routes" / "pipeline_agents.py",
    REPO_ROOT / "backend" / "routes" / "code_intelligence.py",
    REPO_ROOT / "backend" / "routes" / "collaboration.py",
    REPO_ROOT / "backend" / "routes" / "ai_toolkit_enhanced.py",
    REPO_ROOT / "backend" / "core" / "text_gamefile.py",
    REPO_ROOT / "backend" / "core" / "observability.py",
    REPO_ROOT / "backend" / "services" / "jeeves_consultant.py",
    REPO_ROOT / "backend" / "gameforge" / "runtime" / "agent_runtime.py",
    REPO_ROOT / "backend" / "gameforge" / "exocortex" / "quality.py",
    REPO_ROOT / "backend" / "gameforge" / "personal" / "synergy" / "coherence.py",
    REPO_ROOT / "backend" / "gameforge" / "enterprise" / "zaibatsu_security.py",
    REPO_ROOT / "backend" / "gameforge" / "personal" / "synergy" / "reliability.py",
    REPO_ROOT / "backend" / "core" / "product_control_plane.py",
    REPO_ROOT / "backend" / "gameforge" / "bootstrap" / "begin_cns_activation.py",
]
TELEMETRY = REPO_ROOT / "backend" / "routes" / "telemetry.py"
SERVER = REPO_ROOT / "backend" / "server.py"

_PRIVATE = "private-detail-must-not-leak-7f31"


def _is_exception_handler(handler: ast.ExceptHandler) -> bool:
    return isinstance(handler.type, ast.Name) and handler.type.id == "Exception"


def _http_exception_calls(node: ast.AST):
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "HTTPException"
        ):
            yield child


def _references_name(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(child, ast.Name)
        and isinstance(child.ctx, ast.Load)
        and child.id == name
        for child in ast.walk(node)
    )


def _broad_failure_http_leaks(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    leaks: list[int] = []
    for handler in (node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)):
        if not _is_exception_handler(handler) or not handler.name:
            continue
        for statement in handler.body:
            for call in _http_exception_calls(statement):
                if _references_name(call, handler.name):
                    leaks.append(call.lineno)
    return leaks


def _http_status_code(call: ast.Call) -> int | None:
    for keyword in call.keywords:
        if keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant):
            value = keyword.value.value
            if isinstance(value, int):
                return value
    if call.args:
        first = call.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, int):
            return first.value
    return None


def _server_error_http_leaks(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    leaks: list[int] = []
    for handler in (node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)):
        if not handler.name:
            continue
        for statement in handler.body:
            for call in _http_exception_calls(statement):
                status = _http_status_code(call)
                if status is not None and status >= 500 and _references_name(call, handler.name):
                    leaks.append(call.lineno)
    return leaks


@pytest.mark.parametrize("path", ROUTE_FILES, ids=lambda path: path.name)
def test_converted_routes_do_not_leak_caught_exceptions(path: Path) -> None:
    leaks = _broad_failure_http_leaks(path)
    assert leaks == [], f"{path.name} exposes caught exception data in HTTP responses at lines {leaks}"


@pytest.mark.parametrize("path", ROUTE_FILES, ids=lambda path: path.name)
def test_converted_routes_use_stable_helpers_or_constants(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    assert "detail=str(" not in source
    assert "str(e)" not in source
    assert "str(exc)" not in source
    assert "repr(e)" not in source
    assert "type(e).__name__}: {e}" not in source
    assert "internal_http_error(" in source or "from core.http_errors import" in source


@pytest.mark.parametrize("path", SERVER_ERROR_FILES, ids=lambda path: path.name)
def test_mixed_routes_do_not_leak_server_errors(path: Path) -> None:
    leaks = _server_error_http_leaks(path)
    assert leaks == [], f"{path.name} exposes caught exception data in 5xx responses at lines {leaks}"
    source = path.read_text(encoding="utf-8")
    assert "internal_http_error(" in source or "public_http_error(" in source


@pytest.mark.parametrize("path", JSON_ENVELOPE_FILES, ids=lambda path: path.name)
def test_json_envelopes_do_not_stringify_caught_exceptions(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    assert '"error": str(e)' not in source
    assert '"message": str(e)' not in source
    assert '"detail": str(e)' not in source
    assert "persist failed: {e}" not in source
    assert "APK toolchain unavailable:" not in source
    assert "Failed to load build:" not in source
    assert "Failed to launch build task:" not in source
    assert "curiosity research unavailable:" not in source
    assert "type(e).__name__}: {e}" not in source
    assert 'f"stripe error:' not in source
    assert "all models failed:" not in source
    assert "persist_failed: {e}" not in source
    assert "probe_crashed:" not in source
    assert "engine run error:" not in source
    assert "manifest_corrupt:" not in source
    assert "type(exc).__name__}: {exc}" not in source
    assert '"error": str(r)' not in source
    assert '"error": str(ex)' not in source
    assert '"error": str(error)' not in source
    assert "self.last_error = str(e)" not in source
    assert '"error": str(e)[:300]' not in source
    assert '"error":       str(e)[:200]' not in source
    assert "Agent temporarily unavailable:" not in source
    assert "output pending —" not in source
    assert 'f"Error: {str(e)}"' not in source
    assert 'f"AI Error: {str(e)}"' not in source
    assert "unreachable: {last_err}" not in source
    assert 'res["error"] = str(e)' not in source
    assert "err=str(e)[:300]" not in source
    assert '_cp_err"] = str(e)' not in source
    assert "work.error = str(e)" not in source
    assert "last_error = str(e)" not in source
    assert "worker-fallback:" not in source
    assert "gaps=[str(e)]" not in source
    assert "errors.append(str(e))" not in source
    assert "data, [str(e)]" not in source
    assert 'error=str(e)' not in source
    assert "TriggerError(TriggerErrorCode.UNKNOWN, msg" not in source
    assert '"error": str(exc)' not in source
    assert 'f"ZIP extract failed: {pe}"' not in source
    assert "vault injection soft-failed:" not in source
    assert 'f"room_engine: {e}"' not in source



def test_json_envelopes_do_not_expose_upstream_response_bodies() -> None:
    source = (REPO_ROOT / "backend" / "routes" / "game_command_agents.py").read_text(encoding="utf-8")
    assert "response.text" not in source
    assert "Image generation unavailable (" not in source


def test_internal_http_error_is_stable_and_typed() -> None:
    exc = internal_http_error("Jeeves request failed", RuntimeError(_PRIVATE))
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 500
    assert exc.detail == "Jeeves request failed"
    assert _PRIVATE not in str(exc.detail)


def test_public_http_error_keeps_status_and_hides_exception_text() -> None:
    exc = public_http_error(503, "curiosity_research_unavailable", RuntimeError(_PRIVATE))
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 503
    assert exc.detail == "curiosity_research_unavailable"
    assert _PRIVATE not in str(exc.detail)


def test_unhandled_exception_handler_redacts_detail() -> None:
    app = FastAPI()
    before = app.exception_handlers.get(StarletteHTTPException)
    install_public_error_handlers(app)
    assert app.exception_handlers.get(StarletteHTTPException) is before
    handler = app.exception_handlers[Exception]
    response = asyncio.run(handler(None, RuntimeError(_PRIVATE)))
    assert response.status_code == 500
    payload = response.body.decode("utf-8")
    assert PUBLIC_INTERNAL_ERROR in payload
    assert _PRIVATE not in payload


def test_redact_client_text_strips_credentials() -> None:
    rendered = redact_client_text(
        "authorization=Bearer abc.def token=super-secret password=hunter2"
    )
    assert "abc.def" not in rendered
    assert "super-secret" not in rendered
    assert "hunter2" not in rendered
    assert rendered.count("[REDACTED]") >= 2


def test_redact_client_payload_is_bounded() -> None:
    payload = {"token": "abc", "nested": {"password": "x", "ok": "fine"}}
    redacted = redact_client_payload(payload)
    assert redacted["token"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["nested"]["ok"] == "fine"


def test_telemetry_crash_path_redacts_before_persist() -> None:
    source = TELEMETRY.read_text(encoding="utf-8")
    assert "def crash_row(" in source
    assert "redact_client_text(report.message" in source
    assert "redact_client_text(report.stack" in source
    assert "redact_client_payload(report.info)" in source
    assert 'stack": (report.stack or "")[:8000]' not in source


def test_server_health_envelopes_do_not_stringify_exceptions() -> None:
    source = SERVER.read_text(encoding="utf-8")
    assert 'return {"error": str(e)}' not in source
    assert '"error": str(e)[:200]' not in source
    assert "index_audit_failed" in source
    assert "probe_failed" in source
    assert "analysis_failed" in source
    assert "boot_task_failed" in source
    assert "execution_failed" in source
    assert 'entry["error"] = f"{type(e).__name__}: {str(e)[:200]}"' not in source
    assert "result.error = str(e)" not in source
