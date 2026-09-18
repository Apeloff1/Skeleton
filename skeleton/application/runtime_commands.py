"""Runtime handlers for the shared API/CLI command contracts."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .command_contracts import (
    CONTRACT_VERSION,
    MATERIALISE_TARGETS,
    CommandError,
    CommandService,
    require_bool,
    require_int,
    require_list,
    require_mapping,
    require_text,
)

APP_VERSION = "16.0.0"


def _runtime_initialized(state: Any) -> bool:
    return getattr(state, "genesis", None) is not None


def _status_handler(state: Any):
    def handle(_payload: Mapping[str, Any]) -> Dict[str, Any]:
        checks = state.is_healthy() if hasattr(state, "is_healthy") else {"overall": False, "checks": {}}
        overall = bool(checks.get("overall", False))
        return {
            "status": "healthy" if overall else "degraded",
            "initialized": _runtime_initialized(state),
            "health": checks,
        }

    return handle


def _configuration_handler(state: Any):
    def handle(_payload: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "application": "Skeleton",
            "application_version": APP_VERSION,
            "command_contract_version": CONTRACT_VERSION,
            "runtime_initialized": _runtime_initialized(state),
        }

    return handle


_CAPABILITY_VIEW_FLAGS = (
    "lifecycle",
    "plane_audit",
    "boot_audit",
    "export_audit",
    "route_audit",
    "hmac_audit",
    "cli_audit",
    "template_audit",
    "sidecar_audit",
    "domain_audit",
    "cortex_audit",
    "mounted_audit",
    "main_cli_audit",
    "app_audit",
    "charter_audit",
    "contract_audit",
    "live_hmac_audit",
    "nested_audit",
    "env_audit",
    "view_audit",
    "idempotency_audit",
    "seal_audit",
    "admit_audit",
    "limit_audit",
    "shared_audit",
    "stack_audit",
    "allow_audit",
    "version_audit",
    "authz_audit",
    "dev_audit",
    "token_audit",
    "mode_audit",
    "codename_audit",
    "cver_audit",
    "ttl_audit",
)


def _capability_view_flags(payload: Mapping[str, Any]) -> Dict[str, bool]:
    flags: Dict[str, bool] = {}
    enabled: list[str] = []
    for name in _CAPABILITY_VIEW_FLAGS:
        flags[name] = require_bool(payload, name, False)
        if flags[name]:
            enabled.append(name)
    if len(enabled) > 1:
        raise CommandError(
            "invalid_argument",
            f"{' and '.join(enabled)} are mutually exclusive",
        )
    return flags


def _lookup_row(payload: Mapping[str, Any], key: str, getter, snapshot):
    raw_id = payload.get(key, "")
    if raw_id in {"", None}:
        return snapshot()
    if not isinstance(raw_id, str):
        raise CommandError("invalid_argument", f"{key} must be a string")
    try:
        return getter(raw_id)
    except KeyError as exc:
        raise CommandError("invalid_argument", str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise CommandError("invalid_argument", str(exc)) from exc


def _capabilities_handler(_state: Any):
    def handle(payload: Mapping[str, Any]) -> Dict[str, Any]:
        flags = _capability_view_flags(payload)
        if flags["ttl_audit"]:
            from .ttl_audit import get_ttl_audit_row, ttl_audit_snapshot

            return _lookup_row(payload, "source_id", get_ttl_audit_row, ttl_audit_snapshot)
        if flags["cver_audit"]:
            from .contract_version_audit import (
                contract_version_audit_snapshot,
                get_contract_version_audit_row,
            )

            return _lookup_row(
                payload,
                "source_id",
                get_contract_version_audit_row,
                contract_version_audit_snapshot,
            )
        if flags["codename_audit"]:
            from .codename_audit import codename_audit_snapshot, get_codename_audit_row

            return _lookup_row(payload, "source_id", get_codename_audit_row, codename_audit_snapshot)
        if flags["mode_audit"]:
            from .session_mode_audit import get_session_mode_audit_row, session_mode_audit_snapshot

            return _lookup_row(payload, "source_id", get_session_mode_audit_row, session_mode_audit_snapshot)
        if flags["token_audit"]:
            from .dev_token_audit import dev_token_audit_snapshot, get_dev_token_audit_row

            return _lookup_row(payload, "token_id", get_dev_token_audit_row, dev_token_audit_snapshot)
        if flags["dev_audit"]:
            from .open_dev_audit import get_open_dev_audit_row, open_dev_audit_snapshot

            return _lookup_row(payload, "prefix_id", get_open_dev_audit_row, open_dev_audit_snapshot)
        if flags["authz_audit"]:
            from .authz_audit import authz_audit_snapshot, get_authz_audit_row

            return _lookup_row(payload, "command_id", get_authz_audit_row, authz_audit_snapshot)
        if flags["version_audit"]:
            from .version_audit import get_version_audit_row, version_audit_snapshot

            return _lookup_row(payload, "source_id", get_version_audit_row, version_audit_snapshot)
        if flags["allow_audit"]:
            from .allow_list_audit import allow_list_audit_snapshot, get_allow_list_audit_row

            return _lookup_row(payload, "handler_id", get_allow_list_audit_row, allow_list_audit_snapshot)
        if flags["stack_audit"]:
            from .gate_stack_audit import gate_stack_audit_snapshot, get_gate_stack_audit_row

            return _lookup_row(payload, "layer_id", get_gate_stack_audit_row, gate_stack_audit_snapshot)
        if flags["shared_audit"]:
            from .cli_shared_audit import cli_shared_audit_snapshot, get_cli_shared_audit_row

            return _lookup_row(payload, "command_id", get_cli_shared_audit_row, cli_shared_audit_snapshot)
        if flags["limit_audit"]:
            from .gate_limit_audit import gate_limit_audit_snapshot, get_gate_limit_audit_row

            return _lookup_row(payload, "flag_id", get_gate_limit_audit_row, gate_limit_audit_snapshot)
        if flags["admit_audit"]:
            from .admit_write_audit import admit_write_audit_snapshot, get_admit_write_audit_row

            return _lookup_row(payload, "method_id", get_admit_write_audit_row, admit_write_audit_snapshot)
        if flags["seal_audit"]:
            from .seal_audit import get_seal_audit_row, seal_audit_snapshot

            return _lookup_row(payload, "route_id", get_seal_audit_row, seal_audit_snapshot)
        if flags["idempotency_audit"]:
            from .idempotency_audit import get_idempotency_audit_row, idempotency_audit_snapshot

            return _lookup_row(payload, "handler_id", get_idempotency_audit_row, idempotency_audit_snapshot)
        if flags["view_audit"]:
            from .capability_view_audit import capability_view_audit_snapshot, get_capability_view_audit_row

            return _lookup_row(payload, "flag_id", get_capability_view_audit_row, capability_view_audit_snapshot)
        if flags["env_audit"]:
            from .env_flag_audit import env_flag_audit_snapshot, get_env_flag_audit_row

            return _lookup_row(payload, "flag_id", get_env_flag_audit_row, env_flag_audit_snapshot)
        if flags["nested_audit"]:
            from .nested_router_audit import get_nested_router_audit_row, nested_router_audit_snapshot

            return _lookup_row(payload, "include_id", get_nested_router_audit_row, nested_router_audit_snapshot)
        if flags["live_hmac_audit"]:
            from .live_hmac_audit import get_live_hmac_audit_row, live_hmac_audit_snapshot

            return _lookup_row(payload, "route_id", get_live_hmac_audit_row, live_hmac_audit_snapshot)
        if flags["contract_audit"]:
            from .contract_audit import contract_audit_snapshot, get_contract_audit_row

            return _lookup_row(payload, "command_id", get_contract_audit_row, contract_audit_snapshot)
        if flags["charter_audit"]:
            from .charter_audit import charter_audit_snapshot, get_charter_audit_row

            return _lookup_row(payload, "route_id", get_charter_audit_row, charter_audit_snapshot)
        if flags["app_audit"]:
            from .app_route_audit import app_route_audit_snapshot, get_app_route_audit_row

            return _lookup_row(payload, "route_id", get_app_route_audit_row, app_route_audit_snapshot)
        if flags["main_cli_audit"]:
            from .main_cli_audit import get_main_cli_audit_row, main_cli_audit_snapshot

            return _lookup_row(payload, "command_id", get_main_cli_audit_row, main_cli_audit_snapshot)
        if flags["mounted_audit"]:
            from .mounted_route_audit import get_mounted_route_audit_row, mounted_route_audit_snapshot

            return _lookup_row(payload, "route_id", get_mounted_route_audit_row, mounted_route_audit_snapshot)
        if flags["cortex_audit"]:
            from .cortex_route_audit import cortex_route_audit_snapshot, get_cortex_route_audit_row

            return _lookup_row(payload, "route_id", get_cortex_route_audit_row, cortex_route_audit_snapshot)
        if flags["domain_audit"]:
            from .gate_domain_audit import gate_domain_audit_snapshot, get_gate_domain_audit_row

            return _lookup_row(payload, "path", get_gate_domain_audit_row, gate_domain_audit_snapshot)
        if flags["sidecar_audit"]:
            from .sidecar_route_audit import get_sidecar_route_audit_row, sidecar_route_audit_snapshot

            return _lookup_row(payload, "route_id", get_sidecar_route_audit_row, sidecar_route_audit_snapshot)
        if flags["template_audit"]:
            from .template_audit import get_template_audit_row, template_audit_snapshot

            return _lookup_row(payload, "template_id", get_template_audit_row, template_audit_snapshot)
        if flags["cli_audit"]:
            from .developer_cli_audit import developer_cli_audit_snapshot, get_developer_cli_audit_row

            return _lookup_row(payload, "command_id", get_developer_cli_audit_row, developer_cli_audit_snapshot)
        if flags["hmac_audit"]:
            from .hmac_open_audit import get_hmac_open_audit_row, hmac_open_audit_snapshot

            return _lookup_row(payload, "route_id", get_hmac_open_audit_row, hmac_open_audit_snapshot)
        if flags["route_audit"]:
            from .api_route_audit import api_route_audit_snapshot, get_api_route_audit_row

            return _lookup_row(payload, "route_id", get_api_route_audit_row, api_route_audit_snapshot)
        if flags["export_audit"]:
            from .export_audit import export_audit_snapshot, get_export_audit_row

            return _lookup_row(payload, "capability_id", get_export_audit_row, export_audit_snapshot)
        if flags["boot_audit"]:
            from .genesis_boot_audit import genesis_boot_audit_snapshot, get_genesis_boot_audit_row

            return _lookup_row(payload, "phase_id", get_genesis_boot_audit_row, genesis_boot_audit_snapshot)
        if flags["plane_audit"]:
            from .plane_audit import get_plane_audit_row, plane_audit_snapshot

            return _lookup_row(payload, "plane_id", get_plane_audit_row, plane_audit_snapshot)
        if flags["lifecycle"]:
            from .capability_runtime import capability_lifecycle_snapshot

            return capability_lifecycle_snapshot()
        from .capability_manifest import capability_manifest

        return capability_manifest()

    return handle


def _memory_handler(state: Any):
    def handle(payload: Mapping[str, Any]) -> Dict[str, Any]:
        memory = getattr(state, "memory_trinity", None)
        if memory is None:
            raise CommandError("unavailable", "memory service is not initialized")
        query = require_text(payload, "query", "").strip()
        if not query:
            raise CommandError("invalid_argument", "query is required")
        top_k = require_int(payload, "top_k", 3, minimum=1)
        result = memory.query_unified(
            query,
            top_k_per_tier=top_k,
            metadata_filter=require_mapping(payload, "metadata_filter", None, optional=True),
        )
        return {
            "facts": [item.chunk.text for item in result.facts],
            "persona_frame": [item.chunk.text for item in result.persona_frame],
            "personal_history": [item.chunk.text for item in result.personal_history],
            "combined_score": result.combined_score,
            "token_estimate": result.token_estimate,
            "provenance": result.provenance_chain,
        }

    return handle


def _tool_handler(state: Any):
    def handle(payload: Mapping[str, Any]) -> Dict[str, Any]:
        registry = getattr(state, "registry", None)
        if registry is None:
            raise CommandError("unavailable", "tool registry is not initialized")
        action = require_text(payload, "action", "list").strip().lower()
        if action != "list":
            raise CommandError(
                "unsupported_operation",
                "shared tool contract currently supports action=list only",
                details={"action": action},
            )
        tools = []
        for capability in registry.list():
            tools.append(capability.to_dict() if hasattr(capability, "to_dict") else {"name": str(capability)})
        return {"action": "list", "tools": tools, "count": len(tools)}

    return handle


def _admin_handler(state: Any):
    def handle(payload: Mapping[str, Any]) -> Dict[str, Any]:
        action = require_text(payload, "action", "summary").strip().lower()
        if action != "summary":
            raise CommandError(
                "unsupported_operation",
                "shared admin contract currently supports action=summary only",
                details={"action": action},
            )
        genesis = getattr(state, "genesis", None)
        handles = sorted(getattr(genesis, "handles", {}).keys()) if genesis is not None else []
        return {
            "action": "summary",
            "initialized": genesis is not None,
            "handle_count": len(handles),
            "handles": handles,
        }

    return handle


def _run_handler(state: Any):
    def handle(payload: Mapping[str, Any]) -> Dict[str, Any]:
        gameforge = getattr(state, "gameforge", None)
        if gameforge is None:
            raise CommandError("unavailable", "GameForge runtime is not initialized")
        answers = require_mapping(payload, "answers", {}, optional=False)
        spec = gameforge.run(
            answers,
            title=require_text(payload, "title", None, optional=True),
            target=require_text(payload, "target", "json", allowed=MATERIALISE_TARGETS),
            repair=require_bool(payload, "repair", False),
        )
        game = spec.to_dict() if hasattr(spec, "to_dict") else spec
        return {"game": game, "status": "generated"}

    return handle


def build_runtime_command_service(state: Any) -> CommandService:
    """Build the shared command dispatcher bound to one runtime state object."""

    service = CommandService()
    service.register("status", _status_handler(state))
    service.register("configuration", _configuration_handler(state))
    service.register("capabilities", _capabilities_handler(state))
    service.register("memory", _memory_handler(state))
    service.register("tool", _tool_handler(state))
    service.register("admin", _admin_handler(state))
    service.register("run", _run_handler(state))
    return service
