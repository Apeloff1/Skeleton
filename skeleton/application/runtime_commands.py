"""Runtime handlers for the shared API/CLI command contracts."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from skeleton.observability.contract import annotate_context, get_observability

from .command_contracts import CONTRACT_VERSION, CommandError, CommandService

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


def _memory_handler(state: Any):
    def handle(payload: Mapping[str, Any]) -> Dict[str, Any]:
        memory = getattr(state, "memory_trinity", None)
        if memory is None:
            raise CommandError("unavailable", "memory service is not initialized")
        query = str(payload.get("query", "")).strip()
        if not query:
            raise CommandError("invalid_argument", "query is required")
        top_k = int(payload.get("top_k", 3))
        if top_k < 1:
            raise CommandError("invalid_argument", "top_k must be >= 1")
        result = memory.query_unified(
            query,
            top_k_per_tier=top_k,
            metadata_filter=payload.get("metadata_filter"),
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
        action = str(payload.get("action", "list")).strip().lower()
        tool_id = str(payload.get("tool_id") or f"registry.{action}")[:128]
        annotate_context(tool_id=tool_id)
        observability = get_observability()
        if action != "list":
            observability.emit(
                "runtime.tool",
                component="tool",
                status="error",
                attrs={"action": action, "tool_id": tool_id},
            )
            raise CommandError(
                "unsupported_operation",
                "shared tool contract currently supports action=list only",
                details={"action": action},
            )
        with observability.operation(
            "runtime.tool",
            component="tool",
            attrs={"action": action, "tool_id": tool_id},
        ):
            tools = []
            for capability in registry.list():
                tools.append(capability.to_dict() if hasattr(capability, "to_dict") else {"name": str(capability)})
        return {"action": "list", "tools": tools, "count": len(tools)}

    return handle


def _admin_handler(state: Any):
    def handle(payload: Mapping[str, Any]) -> Dict[str, Any]:
        action = str(payload.get("action", "summary")).strip().lower()
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
        answers = payload.get("answers", {})
        if not isinstance(answers, Mapping):
            raise CommandError("invalid_argument", "answers must be an object")
        spec = gameforge.run(
            dict(answers),
            title=payload.get("title"),
            target=payload.get("target", "json"),
            repair=bool(payload.get("repair", False)),
        )
        game = spec.to_dict() if hasattr(spec, "to_dict") else spec
        return {"game": game, "status": "generated"}

    return handle


def build_runtime_command_service(state: Any) -> CommandService:
    """Build the shared command dispatcher bound to one runtime state object."""

    service = CommandService()
    service.register("status", _status_handler(state))
    service.register("configuration", _configuration_handler(state))
    service.register("memory", _memory_handler(state))
    service.register("tool", _tool_handler(state))
    service.register("admin", _admin_handler(state))
    service.register("run", _run_handler(state))
    return service
