"""REST API surface — thin FastAPI routers for every subsystem."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from skeleton.api.hmac_seal import require_seal
from skeleton.api.charter_gate import require_charter
from skeleton.api.idempotency import IdempotencyGuard
from skeleton.api.server import get_state
from skeleton.jeeves.core import SessionMode
from skeleton.memory.guarded_compaction import compact_turns
from skeleton.app.assembly import load_manifest

router = APIRouter()
_APP_MANIFEST = load_manifest()

# Idempotency for retry-sensitive POSTs (forge materialise, gameforge runs):
# a client retry replays the first recorded response instead of re-executing.
_idempotency = IdempotencyGuard()


def _state():
    return get_state()


def _require(obj: Any, name: str) -> Any:
    if obj is None:
        raise HTTPException(status_code=503, detail=f"{name} not available")
    return obj


def _payload_error(exc: Exception) -> HTTPException:
    from skeleton.application.command_contracts import CommandError

    if isinstance(exc, CommandError):
        return HTTPException(status_code=exc.http_status, detail=exc.message)
    return HTTPException(status_code=422, detail=str(exc))


def _int_field(payload: Dict[str, Any], key: str, default: int, *, minimum: int = 1) -> int:
    from skeleton.application.command_contracts import CommandError, require_int

    try:
        return require_int(payload, key, default, minimum=minimum)
    except CommandError as exc:
        raise _payload_error(exc) from exc


def _float_field(
    payload: Dict[str, Any],
    key: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    from skeleton.application.command_contracts import CommandError, require_float

    try:
        return require_float(payload, key, default, minimum=minimum, maximum=maximum)
    except CommandError as exc:
        raise _payload_error(exc) from exc


def _text_field(
    payload: Dict[str, Any],
    key: str,
    default: Optional[str] = "",
    *,
    allowed: tuple[str, ...] | None = None,
    optional: bool = False,
) -> Optional[str]:
    from skeleton.application.command_contracts import CommandError, require_text

    try:
        value = require_text(payload, key, default, optional=optional, allowed=allowed)
    except CommandError as exc:
        raise _payload_error(exc) from exc
    if optional:
        return value
    return str(value or "")


def _mapping_field(
    payload: Dict[str, Any],
    key: str,
    default: dict[str, Any] | None = None,
    *,
    optional: bool = True,
) -> dict[str, Any] | None:
    from skeleton.application.command_contracts import CommandError, require_mapping

    try:
        return require_mapping(payload, key, default, optional=optional)
    except CommandError as exc:
        raise _payload_error(exc) from exc


def _list_field(
    payload: Dict[str, Any],
    key: str,
    default: list[Any] | None = None,
    *,
    optional: bool = True,
    item_type: type | tuple[type, ...] | None = None,
) -> list[Any] | None:
    from skeleton.application.command_contracts import CommandError, require_list

    try:
        return require_list(payload, key, default, optional=optional, item_type=item_type)
    except CommandError as exc:
        raise _payload_error(exc) from exc


def _bool_field(payload: Dict[str, Any], key: str, default: bool = False) -> bool:
    from skeleton.application.command_contracts import CommandError, require_bool

    try:
        return require_bool(payload, key, default)
    except CommandError as exc:
        raise _payload_error(exc) from exc


def _pipeline_prefetch(state: Any, pipeline_name: str, description: Any) -> Dict[str, Any]:
    from skeleton.pipelines.speculative_rag import planning_prefetch_dict

    return planning_prefetch_dict(
        getattr(state, "genesis", None),
        pipeline_name,
        {"description": str(description or "")},
        limit=3,
    )


def _spec_rag(spec: Any, state: Any, pipeline_name: str, description: Any) -> Dict[str, Any]:
    payload = spec.to_dict() if hasattr(spec, "to_dict") else {}
    rag = payload.get("speculative_rag") if isinstance(payload, dict) else None
    if isinstance(rag, dict) and rag.get("pipeline"):
        return rag
    return _pipeline_prefetch(state, pipeline_name, description)


@router.get("/health")
async def health(state=Depends(_state)) -> Dict[str, Any]:
    checks = state.is_healthy()
    return {"status": "healthy" if checks["overall"] else "degraded", "checks": checks}


@router.get("/health/live")
async def live(state=Depends(_state)) -> Dict[str, Any]:
    payload = dict(_require(state.health, "Health").liveness())
    payload["application"] = {
        "name": _APP_MANIFEST.name,
        "version": _APP_MANIFEST.version,
        "component": "engine",
        "ingress_prefix": _APP_MANIFEST.service("skeleton").ingress_prefix,
    }
    return payload


@router.get("/health/ready")
async def ready(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.health, "Health").readiness()


@router.get("/metrics")
async def metrics(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.metrics, "Metrics").snapshot()


@router.get("/genesis")
async def genesis_report(state=Depends(_state)) -> Dict[str, Any]:
    genesis = _require(state.genesis, "Genesis")
    return {"report": genesis.report.to_dict(), "health": genesis.health()}


@router.get("/genesis/handles")
async def genesis_handles(state=Depends(_state)) -> Dict[str, Any]:
    """Names of every subsystem handle wired by the Genesis boot, per phase."""
    genesis = _require(state.genesis, "Genesis")
    return {
        "phases": genesis.report.phases,
        "wired": genesis.report.wired,
        "handle_names": sorted(genesis.handles.keys()),
    }


@router.get("/interface/reranker/stats")
async def reranker_stats(state=Depends(_state)) -> Dict[str, Any]:
    """FeatureReranker counters (queries reranked, active weights)."""
    genesis = _require(state.genesis, "Genesis")
    reranker = genesis.handles.get("reranker")
    if reranker is None:
        raise HTTPException(status_code=503, detail="reranker not wired")
    stats = reranker.stats() if hasattr(reranker, "stats") else {}
    return {"reranker": stats}


@router.post("/retrieval/query")
async def retrieval_query(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    """Fan a query over the four-plane quad retriever (RAG+CAG+MAG+KAG, RRF)."""
    genesis = _require(state.genesis, "Genesis")
    quad = genesis.handles.get("quad")
    if quad is None:
        raise HTTPException(status_code=503, detail="quad retriever not wired")
    query = _text_field(request, "query", "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="query is required")
    k = _int_field(request, "k", 8, minimum=1)
    results = quad.retrieve(query, k=k, use_cache=_bool_field(request, "use_cache", True))
    return {
        "query": query,
        "results": [
            {
                "id": f.fragment_id,
                "plane": f.plane,
                "content": f.content,
                "score": round(f.score, 6),
                "provenance": f.provenance,
            }
            for f in results
        ],
        "stats": quad.stats(),
    }


@router.post("/retrieval/ingest")
async def retrieval_ingest(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    """Ingest a document into the quad retriever's RAG+MAG planes."""
    genesis = _require(state.genesis, "Genesis")
    quad = genesis.handles.get("quad")
    if quad is None:
        raise HTTPException(status_code=503, detail="quad retriever not wired")
    doc_id = _text_field(request, "doc_id", "").strip()
    text = _text_field(request, "text", "").strip()
    if not doc_id or not text:
        raise HTTPException(status_code=422, detail="doc_id and text are required")
    chunks = quad.ingest_document(
        doc_id, text,
        metadata=_mapping_field(request, "metadata", None, optional=True),
        salience=_float_field(request, "salience", 0.5, minimum=0.0),
    )
    return {"doc_id": doc_id, "chunks": chunks, "status": "ingested"}


@router.post("/retrieval/feedback")
async def retrieval_feedback(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    """Report which retrieval planes were used — trains plane-weight learner."""
    from skeleton.retrieval.feedback import record_plane_feedback

    genesis = _require(state.genesis, "Genesis")
    quad = genesis.handles.get("quad")
    if quad is None:
        raise HTTPException(status_code=503, detail="quad retriever not wired")

    if "used_planes" in request:
        used = _list_field(request, "used_planes", None, optional=True, item_type=str)
    elif "used" in request:
        used = _list_field(request, "used", None, optional=True, item_type=str)
    else:
        used = None
    return record_plane_feedback(
        quad,
        used,
        all_planes=_list_field(request, "all_planes", None, optional=True, item_type=str),
    )


@router.get("/capabilities")
async def capabilities(state=Depends(_state)) -> List[Dict[str, Any]]:
    return [cap.to_dict() for cap in _require(state.registry, "Registry").list()]


@router.get("/application/routes/audit/{method}/{path:path}")
async def application_api_route_audit_row(method: str, path: str) -> Dict[str, Any]:
    """Return one main-router audit row by method and path."""
    from skeleton.application import get_api_route_audit_row

    try:
        return get_api_route_audit_row(f"{method} /{path.lstrip('/')}")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/routes/audit")
async def application_api_route_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --route-audit``."""
    from skeleton.application import api_route_audit_snapshot

    return api_route_audit_snapshot()


@router.get("/application/hmac/audit/{method}/{path:path}")
async def application_hmac_open_audit_row(method: str, path: str) -> Dict[str, Any]:
    """Return one HMAC-open audit row by method and path."""
    from skeleton.application import get_hmac_open_audit_row

    try:
        return get_hmac_open_audit_row(f"{method} /{path.lstrip('/')}")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/hmac/audit")
async def application_hmac_open_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --hmac-audit``."""
    from skeleton.application import hmac_open_audit_snapshot

    return hmac_open_audit_snapshot()


@router.get("/application/cli/audit/{command_id}")
async def application_developer_cli_audit_row(command_id: str) -> Dict[str, Any]:
    """Return one developer-CLI audit row by command name."""
    from skeleton.application import get_developer_cli_audit_row

    try:
        return get_developer_cli_audit_row(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/cli/audit")
async def application_developer_cli_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --cli-audit``."""
    from skeleton.application import developer_cli_audit_snapshot

    return developer_cli_audit_snapshot()


@router.get("/application/templates/audit/{template_id}")
async def application_template_audit_row(template_id: str) -> Dict[str, Any]:
    """Return one scaffold-template audit row by template ID."""
    from skeleton.application import get_template_audit_row

    try:
        return get_template_audit_row(template_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/templates/audit")
async def application_template_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --template-audit``."""
    from skeleton.application import template_audit_snapshot

    return template_audit_snapshot()


@router.get("/application/sidecars/audit/{method}/{path:path}")
async def application_sidecar_route_audit_row(method: str, path: str) -> Dict[str, Any]:
    """Return one sidecar-router audit row by method and path."""
    from skeleton.application import get_sidecar_route_audit_row

    try:
        return get_sidecar_route_audit_row(f"{method} /{path.lstrip('/')}")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/sidecars/audit")
async def application_sidecar_route_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --sidecar-audit``."""
    from skeleton.application import sidecar_route_audit_snapshot

    return sidecar_route_audit_snapshot()


@router.get("/application/domains/audit/{path:path}")
async def application_gate_domain_audit_row(path: str) -> Dict[str, Any]:
    """Return one gate-domain audit row by documented path."""
    from skeleton.application import get_gate_domain_audit_row

    try:
        return get_gate_domain_audit_row(f"/{path.lstrip('/')}")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/domains/audit")
async def application_gate_domain_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --domain-audit``."""
    from skeleton.application import gate_domain_audit_snapshot

    return gate_domain_audit_snapshot()


@router.get("/application/cortex/audit/{method}/{path:path}")
async def application_cortex_route_audit_row(method: str, path: str) -> Dict[str, Any]:
    """Return one unmounted cortex-route audit row by method and path."""
    from skeleton.application import get_cortex_route_audit_row

    try:
        return get_cortex_route_audit_row(f"{method} /{path.lstrip('/')}")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/cortex/audit")
async def application_cortex_route_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --cortex-audit``."""
    from skeleton.application import cortex_route_audit_snapshot

    return cortex_route_audit_snapshot()


@router.get("/application/mounted/audit/{method}/{path:path}")
async def application_mounted_route_audit_row(method: str, path: str) -> Dict[str, Any]:
    """Return one mounted sidecar-router audit row by method and path."""
    from skeleton.application import get_mounted_route_audit_row

    try:
        return get_mounted_route_audit_row(f"{method} /{path.lstrip('/')}")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/mounted/audit")
async def application_mounted_route_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --mounted-audit``."""
    from skeleton.application import mounted_route_audit_snapshot

    return mounted_route_audit_snapshot()


@router.get("/application/main-cli/audit/{command_id}")
async def application_main_cli_audit_row(command_id: str) -> Dict[str, Any]:
    """Return one main-CLI audit row by command name."""
    from skeleton.application import get_main_cli_audit_row

    try:
        return get_main_cli_audit_row(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/main-cli/audit")
async def application_main_cli_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --main-cli-audit``."""
    from skeleton.application import main_cli_audit_snapshot

    return main_cli_audit_snapshot()


@router.get("/application/app/audit/{method}/{path:path}")
async def application_app_route_audit_row(method: str, path: str) -> Dict[str, Any]:
    """Return one create_app inline-handler audit row by method and path."""
    from skeleton.application import get_app_route_audit_row

    try:
        return get_app_route_audit_row(f"{method} /{path.lstrip('/')}")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/app/audit")
async def application_app_route_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --app-audit``."""
    from skeleton.application import app_route_audit_snapshot

    return app_route_audit_snapshot()


@router.get("/application/charter/audit/{method}/{path:path}")
async def application_charter_audit_row(method: str, path: str) -> Dict[str, Any]:
    """Return one charter-binding audit row by method and path."""
    from skeleton.application import get_charter_audit_row

    try:
        return get_charter_audit_row(f"{method} /{path.lstrip('/')}")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/charter/audit")
async def application_charter_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --charter-audit``."""
    from skeleton.application import charter_audit_snapshot

    return charter_audit_snapshot()


@router.get("/application/contracts/audit/{command_id}")
async def application_contract_audit_row(command_id: str) -> Dict[str, Any]:
    """Return one command-contract audit row by command name."""
    from skeleton.application import get_contract_audit_row

    try:
        return get_contract_audit_row(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/contracts/audit")
async def application_contract_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --contract-audit``."""
    from skeleton.application import contract_audit_snapshot

    return contract_audit_snapshot()


@router.get("/application/hmac/live-audit/{method}/{path:path}")
async def application_live_hmac_audit_row(method: str, path: str) -> Dict[str, Any]:
    """Return one live-HMAC audit row by method and path."""
    from skeleton.application import get_live_hmac_audit_row

    try:
        return get_live_hmac_audit_row(f"{method} /{path.lstrip('/')}")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/hmac/live-audit")
async def application_live_hmac_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --live-hmac-audit``."""
    from skeleton.application import live_hmac_audit_snapshot

    return live_hmac_audit_snapshot()


@router.get("/application/nested/audit/{include_id:path}")
async def application_nested_router_audit_row(include_id: str) -> Dict[str, Any]:
    """Return one nested-include audit row by host module."""
    from skeleton.application import get_nested_router_audit_row

    try:
        return get_nested_router_audit_row(include_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/nested/audit")
async def application_nested_router_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --nested-audit``."""
    from skeleton.application import nested_router_audit_snapshot

    return nested_router_audit_snapshot()


@router.get("/application/env/audit/{flag_id}")
async def application_env_flag_audit_row(flag_id: str) -> Dict[str, Any]:
    """Return one environment-flag audit row by variable name."""
    from skeleton.application import get_env_flag_audit_row

    try:
        return get_env_flag_audit_row(flag_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/env/audit")
async def application_env_flag_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --env-audit``."""
    from skeleton.application import env_flag_audit_snapshot

    return env_flag_audit_snapshot()


@router.get("/application/views/audit/{flag_id}")
async def application_capability_view_audit_row(flag_id: str) -> Dict[str, Any]:
    """Return one capability-view flag audit row by flag name."""
    from skeleton.application import get_capability_view_audit_row

    try:
        return get_capability_view_audit_row(flag_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/views/audit")
async def application_capability_view_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --view-audit``."""
    from skeleton.application import capability_view_audit_snapshot

    return capability_view_audit_snapshot()


@router.get("/application/idempotency/audit/{handler_id:path}")
async def application_idempotency_audit_row(handler_id: str) -> Dict[str, Any]:
    """Return one idempotency-audit row by module:handler key."""
    from skeleton.application import get_idempotency_audit_row

    try:
        return get_idempotency_audit_row(handler_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/idempotency/audit")
async def application_idempotency_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --idempotency-audit``."""
    from skeleton.application import idempotency_audit_snapshot

    return idempotency_audit_snapshot()


@router.get("/application/seal/audit/{method}/{path:path}")
async def application_seal_audit_row(method: str, path: str) -> Dict[str, Any]:
    """Return one live-seal audit row by method and path."""
    from skeleton.application import get_seal_audit_row

    try:
        return get_seal_audit_row(f"{method} /{path.lstrip('/')}")
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/seal/audit")
async def application_seal_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --seal-audit``."""
    from skeleton.application import seal_audit_snapshot

    return seal_audit_snapshot()


@router.get("/application/admit/audit/{method_id}")
async def application_admit_write_audit_row(method_id: str) -> Dict[str, Any]:
    """Return one write-admit audit row by HTTP method."""
    from skeleton.application import get_admit_write_audit_row

    try:
        return get_admit_write_audit_row(method_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/admit/audit")
async def application_admit_write_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --admit-audit``."""
    from skeleton.application import admit_write_audit_snapshot

    return admit_write_audit_snapshot()


@router.get("/application/limits/audit/{flag_id}")
async def application_gate_limit_audit_row(flag_id: str) -> Dict[str, Any]:
    """Return one gate-limit audit row by environment variable name."""
    from skeleton.application import get_gate_limit_audit_row

    try:
        return get_gate_limit_audit_row(flag_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/limits/audit")
async def application_gate_limit_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --limit-audit``."""
    from skeleton.application import gate_limit_audit_snapshot

    return gate_limit_audit_snapshot()


@router.get("/application/shared/audit/{command_id}")
async def application_cli_shared_audit_row(command_id: str) -> Dict[str, Any]:
    """Return one CLI shared-command mapping row by command name."""
    from skeleton.application import get_cli_shared_audit_row

    try:
        return get_cli_shared_audit_row(command_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/shared/audit")
async def application_cli_shared_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --shared-audit``."""
    from skeleton.application import cli_shared_audit_snapshot

    return cli_shared_audit_snapshot()


@router.get("/application/stack/audit/{layer_id}")
async def application_gate_stack_audit_row(layer_id: str) -> Dict[str, Any]:
    """Return one install_gate middleware-order audit row."""
    from skeleton.application import get_gate_stack_audit_row

    try:
        return get_gate_stack_audit_row(layer_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/stack/audit")
async def application_gate_stack_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --stack-audit``."""
    from skeleton.application import gate_stack_audit_snapshot

    return gate_stack_audit_snapshot()


@router.get("/application/allow/audit/{handler_id:path}")
async def application_allow_list_audit_row(handler_id: str) -> Dict[str, Any]:
    """Return one allow-list usage audit row by module:handler key."""
    from skeleton.application import get_allow_list_audit_row

    try:
        return get_allow_list_audit_row(handler_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/allow/audit")
async def application_allow_list_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --allow-audit``."""
    from skeleton.application import allow_list_audit_snapshot

    return allow_list_audit_snapshot()


@router.get("/application/version/audit/{source_id:path}")
async def application_version_audit_row(source_id: str) -> Dict[str, Any]:
    """Return one advertised-version audit row by source key."""
    from skeleton.application import get_version_audit_row

    try:
        return get_version_audit_row(source_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/version/audit")
async def application_version_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --version-audit``."""
    from skeleton.application import version_audit_snapshot

    return version_audit_snapshot()


@router.get("/application/authz/audit/{command_id}")
async def application_authz_audit_row(command_id: str) -> Dict[str, Any]:
    """Return one mutating/auth_required audit row by command name."""
    from skeleton.application import get_authz_audit_row

    try:
        return get_authz_audit_row(command_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/authz/audit")
async def application_authz_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --authz-audit``."""
    from skeleton.application import authz_audit_snapshot

    return authz_audit_snapshot()


@router.get("/application/open-dev/audit/{prefix_id:path}")
async def application_open_dev_audit_row(prefix_id: str) -> Dict[str, Any]:
    """Return one public-dev prefix audit row."""
    from skeleton.application import get_open_dev_audit_row

    try:
        return get_open_dev_audit_row(prefix_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/open-dev/audit")
async def application_open_dev_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --dev-audit``."""
    from skeleton.application import open_dev_audit_snapshot

    return open_dev_audit_snapshot()


@router.get("/application/tokens/audit/{token_id}")
async def application_dev_token_audit_row(token_id: str) -> Dict[str, Any]:
    """Return one public-dev surface token audit row."""
    from skeleton.application import get_dev_token_audit_row

    try:
        return get_dev_token_audit_row(token_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/tokens/audit")
async def application_dev_token_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --token-audit``."""
    from skeleton.application import dev_token_audit_snapshot

    return dev_token_audit_snapshot()


@router.get("/application/mode/audit/{source_id}")
async def application_session_mode_audit_row(source_id: str) -> Dict[str, Any]:
    """Return one SessionMode identity audit row."""
    from skeleton.application import get_session_mode_audit_row

    try:
        return get_session_mode_audit_row(source_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/mode/audit")
async def application_session_mode_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --mode-audit``."""
    from skeleton.application import session_mode_audit_snapshot

    return session_mode_audit_snapshot()


@router.get("/application/codename/audit/{source_id}")
async def application_codename_audit_row(source_id: str) -> Dict[str, Any]:
    """Return one advertised-codename audit row."""
    from skeleton.application import get_codename_audit_row

    try:
        return get_codename_audit_row(source_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/codename/audit")
async def application_codename_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --codename-audit``."""
    from skeleton.application import codename_audit_snapshot

    return codename_audit_snapshot()


@router.get("/application/cver/audit/{source_id}")
async def application_contract_version_audit_row(source_id: str) -> Dict[str, Any]:
    """Return one command-contract-version identity audit row."""
    from skeleton.application import get_contract_version_audit_row

    try:
        return get_contract_version_audit_row(source_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/cver/audit")
async def application_contract_version_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --cver-audit``."""
    from skeleton.application import contract_version_audit_snapshot

    return contract_version_audit_snapshot()


@router.get("/application/ttl/audit/{source_id}")
async def application_ttl_audit_row(source_id: str) -> Dict[str, Any]:
    """Return one HMAC/idempotency TTL identity audit row."""
    from skeleton.application import get_ttl_audit_row

    try:
        return get_ttl_audit_row(source_id)
    except KeyError as extra:
        raise HTTPException(status_code=404, detail=str(extra)) from extra
    except (TypeError, ValueError) as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra


@router.get("/application/ttl/audit")
async def application_ttl_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --ttl-audit``."""
    from skeleton.application import ttl_audit_snapshot

    return ttl_audit_snapshot()


@router.get("/application/planes/audit/{plane_id}")
async def application_plane_audit_row(plane_id: str) -> Dict[str, Any]:
    """Return one F-15 plane audit row by stable ID."""
    from skeleton.application import get_plane_audit_row

    try:
        return get_plane_audit_row(plane_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/planes/audit")
async def application_plane_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --plane-audit``."""
    from skeleton.application import plane_audit_snapshot

    return plane_audit_snapshot()


@router.get("/application/genesis/audit/{phase_id}")
async def application_genesis_boot_audit_row(phase_id: str) -> Dict[str, Any]:
    """Return one genesis boot-audit row by phase name."""
    from skeleton.application import get_genesis_boot_audit_row

    try:
        return get_genesis_boot_audit_row(phase_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/genesis/audit")
async def application_genesis_boot_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --boot-audit``."""
    from skeleton.application import genesis_boot_audit_snapshot

    return genesis_boot_audit_snapshot()


@router.get("/application/capabilities/export-audit/{capability_id}")
async def application_export_audit_row(capability_id: str) -> Dict[str, Any]:
    """Return one manifest export-audit row by capability ID."""
    from skeleton.application import get_export_audit_row

    try:
        return get_export_audit_row(capability_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/capabilities/export-audit")
async def application_export_audit() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities --export-audit``."""
    from skeleton.application import export_audit_snapshot

    return export_audit_snapshot()


@router.get("/application/capabilities/lifecycle")
async def application_capability_lifecycle() -> Dict[str, Any]:
    """Return resolvable/loaded status for the curated capability manifest."""
    from skeleton.application import capability_lifecycle_snapshot

    return capability_lifecycle_snapshot()


@router.get("/application/capabilities/{capability_id}")
async def application_capability(capability_id: str) -> Dict[str, Any]:
    """Return one curated capability by stable ID."""
    from dataclasses import asdict

    from skeleton.application import get_capability

    try:
        return asdict(get_capability(capability_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/application/capabilities")
async def application_capabilities() -> Dict[str, Any]:
    """Return the identical payload as ``python -m skeleton capabilities``."""
    from skeleton.application import capability_manifest

    return capability_manifest()


@router.post("/jeeves/session")
async def jeeves_session(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    jeeves = _require(state.jeeves, "Jeeves")
    raw_mode = _text_field(request, "mode", "tutoring", allowed=tuple(item.value for item in SessionMode))
    mode = SessionMode(raw_mode)
    session = jeeves.open_session(_text_field(request, "user_id", "anonymous"), mode=mode)
    return {"session_id": session.session_id, "mode": session.mode.value, "status": "created"}


@router.post("/jeeves/interact")
async def jeeves_interact(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    jeeves = _require(state.jeeves, "Jeeves")
    session_id = _text_field(request, "session_id", "")
    reply = jeeves.ask(
        session_id,
        _text_field(request, "input", ""),
        context=_mapping_field(request, "context", None, optional=True),
    )
    return {"response": reply, "session_id": session_id}


@router.post("/jeeves/review")
async def jeeves_review(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.jeeves, "Jeeves").review_code(
        _text_field(request, "session_id", ""),
        _text_field(request, "code", ""),
    )


@router.post("/jeeves/bind-era")
async def jeeves_bind_era(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    from skeleton.forge.eras import list_eras

    pack = _require(state.jeeves, "Jeeves").bind_era(
        _text_field(request, "era", "extraction_now", allowed=tuple(list_eras()))
    )
    return {"era": pack["era"], "primary_dps": pack["primary_dps"], "status": "bound"}


@router.post("/jeeves/advise")
async def jeeves_advise(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.jeeves, "Jeeves").advise(
        _text_field(request, "session_id", ""),
        _mapping_field(request, "telemetry", {}, optional=False) or {},
    )


@router.get("/jeeves/matrices/{session_id}")
async def jeeves_matrices(session_id: str, state=Depends(_state)) -> Dict[str, Any]:
    _require(state.jeeves, "Jeeves")
    return {
        "sam": state.jeeves_sam.snapshot() if state.jeeves_sam else {},
        "clom": state.jeeves_clom.snapshot() if state.jeeves_clom else {},
        "krem": state.jeeves_krem.snapshot() if state.jeeves_krem else {},
        "memory_items": len(state.jeeves_memory) if state.jeeves_memory else 0,
    }


@router.post("/memory/query")
async def memory_query(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    result = _require(state.memory_trinity, "Memory").query_unified(
        _text_field(request, "query", ""),
        top_k_per_tier=_int_field(request, "top_k", 3, minimum=1),
        metadata_filter=_mapping_field(request, "metadata_filter", None, optional=True),
    )
    body: Dict[str, Any] = {
        "facts": [r.chunk.text for r in result.facts],
        "persona_frame": [r.chunk.text for r in result.persona_frame],
        "personal_history": [r.chunk.text for r in result.personal_history],
        "combined_score": result.combined_score,
        "token_estimate": result.token_estimate,
        "provenance": result.provenance_chain,
    }
    # F-3: when turns are supplied, run rot-triggered compaction on them.
    constraints = _list_field(request, "constraints", None, optional=True)
    compaction = compact_turns(_list_field(request, "turns", None, optional=True), constraints=constraints)
    if compaction is not None:
        body["compaction"] = compaction
    return body


@router.get("/swarm/stats")
async def swarm_stats(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.mesh, "Swarm").stats()


@router.post("/swarm/agent")
async def swarm_register_agent(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    agent = _require(state.mesh, "Swarm").join(
        set(_list_field(request, "specialisations", [], optional=False, item_type=str) or []),
        weight=_float_field(request, "weight", 1.0, minimum=0.0),
        metadata=_mapping_field(request, "metadata", None, optional=True),
    )
    return {"agent_id": str(agent.agent_id), "status": "registered"}


@router.post("/swarm/route")
async def swarm_route(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    agent = _require(state.mesh, "Swarm").route(_text_field(request, "capability", ""))
    return {"agent_id": str(agent.agent_id), "load": agent.load}


@router.post("/swarm/submit")
async def swarm_submit(
    request: Dict[str, Any],
    state=Depends(_state),
    attester: str = Depends(require_charter("swarm", "submit")),
) -> Dict[str, Any]:
    """Submit a task into the attested swarm DAG — seal then charter decide."""
    from skeleton.swarm.dag import SubmitError, SwarmDag

    dag = getattr(state, "swarm_dag", None)
    if dag is None:
        dag = SwarmDag()
        state.swarm_dag = dag
    task_id = _text_field(request, "task_id", "") or _text_field(request, "id", "")
    if not task_id:
        raise HTTPException(status_code=400, detail="missing task id")
    capability = _text_field(request, "capability", "")
    payload = _mapping_field(request, "payload", {}, optional=False) or {}
    deps = _list_field(request, "deps", [], optional=False) or []
    try:
        dag.submit(str(task_id), str(capability), payload, list(deps))
    except SubmitError as exc:
        raise HTTPException(
            status_code=400, detail={"error": exc.kind, "detail": exc.detail}
        ) from exc
    node = dag.get(str(task_id))
    return {
        "task_id": str(task_id),
        "status": node.status.value if node is not None else "pending",
        "attester": attester,
        "accepted": True,
    }


@router.get("/ledger/stats")
async def ledger_stats(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.ledger, "Ledger").stats()


@router.get("/ledger/tail")
async def ledger_tail(n: int = 50, state=Depends(_state)) -> List[Dict[str, Any]]:
    return [e.to_dict() for e in _require(state.ledger, "Ledger").tail(n)]


@router.get("/scheduler/stats")
async def scheduler_stats(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.scheduler, "Scheduler").stats()


@router.post("/pipeline/npc")
async def pipeline_npc(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    description = _text_field(request, "description", "")
    spec = _require(state.npc_pipeline, "NPC pipeline").run(
        description,
        name=_text_field(request, "name", "") or None,
        dialogue_beats=_int_field(request, "dialogue_beats", 3, minimum=1),
        params=_mapping_field(request, "params", None, optional=True),
    )
    return {
        "npc": spec.to_dict(),
        "status": "generated",
        "speculative_rag": _spec_rag(spec, state, "npc", description),
    }


@router.post("/pipeline/game-logic")
async def pipeline_game_logic(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    from skeleton.application.command_contracts import PROGRESSION_CURVES

    description = _text_field(request, "description", "")
    spec = _require(state.game_logic_pipeline, "Game logic pipeline").run(
        description,
        title=_text_field(request, "title", "untitled"),
        max_level=_int_field(request, "max_level", 50, minimum=1),
        curve=_text_field(request, "curve", "quadratic", allowed=PROGRESSION_CURVES),
        currency=_text_field(request, "currency", "gold"),
    )
    return {
        "game_logic": spec.to_dict(),
        "status": "generated",
        "speculative_rag": _spec_rag(spec, state, "game_logic", description),
    }


@router.post("/pipeline/animation")
async def pipeline_animation(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    actions = _list_field(request, "actions", None, optional=True, item_type=str)
    description = _text_field(request, "description", "humanoid")
    spec = _require(state.animation_pipeline, "Animation pipeline").run(
        description,
        actions=tuple(actions) if actions else ("idle", "walk", "run", "attack"),
    )
    return {
        "animation": spec.to_dict(),
        "status": "generated",
        "speculative_rag": _spec_rag(spec, state, "animation", description),
    }


def _item_mapping(item: Any, *, label: str) -> Dict[str, Any]:
    return _mapping_field({label: item}, label, optional=False) or {}


def _apply_forge_graph(forge: Any, bp: Any, request: Dict[str, Any]) -> None:
    for comp in _list_field(request, "components", [], optional=False) or []:
        item = _item_mapping(comp, label="components")
        forge.instantiate(
            bp,
            _text_field(item, "kind", ""),
            _text_field(item, "instance_id", ""),
            config=_mapping_field(item, "config", {}, optional=True) or {},
        )
    for wire in _list_field(request, "wires", [], optional=False) or []:
        item = _item_mapping(wire, label="wires")
        bp.connect(
            tuple(_list_field(item, "from", [], optional=False, item_type=str) or []),
            tuple(_list_field(item, "to", [], optional=False, item_type=str) or []),
        )


@router.post("/forge/blueprint")
async def forge_blueprint(request: Dict[str, Any], state=Depends(_state), attester: str = Depends(require_charter("forge", "blueprint"))) -> Dict[str, Any]:
    forge = _require(state.forge, "Forge")
    bp = forge.new_blueprint(_text_field(request, "name", "unnamed"))
    _apply_forge_graph(forge, bp, request)
    problems = bp.validate()
    return {"blueprint_id": bp.blueprint_id, "valid": not problems, "problems": problems, "status": "created"}


@router.post("/forge/materialise")
async def forge_materialise(http_request: Request, request: Dict[str, Any], state=Depends(_state), attester: str = Depends(require_charter("forge", "materialise"))) -> Dict[str, Any]:
    replay = _idempotency.replay(dict(http_request.headers))
    if replay is not None:
        return replay  # type: ignore[return-value]
    forge = _require(state.forge, "Forge")
    bp = forge.new_blueprint(_text_field(request, "name", "unnamed"))
    _apply_forge_graph(forge, bp, request)
    repair = _bool_field(request, "repair", False)
    max_rounds = _int_field(request, "max_rounds", 3, minimum=1)
    from skeleton.application.command_contracts import MATERIALISE_TARGETS

    artefact = forge.materialise(
        bp,
        era=_text_field(request, "era", "extraction_now"),
        target=_text_field(request, "target", "json", allowed=MATERIALISE_TARGETS),
        repair=repair,
        max_rounds=max_rounds,
    )
    response = {
        "artefact": artefact,
        "status": "materialised",
        "verification": artefact.get("verification"),
        "verify_loop": artefact.get("verify_loop"),
        "repair": artefact.get("repair"),
    }
    _idempotency.remember(dict(http_request.headers), response)
    return response


@router.get("/forge/kinds")
async def forge_kinds(state=Depends(_state)) -> List[str]:
    return _require(state.forge, "Forge").available_kinds()


@router.get("/forge/eras")
async def forge_eras() -> Dict[str, Any]:
    from skeleton.forge.eras import list_eras, compile_era
    return {"eras": list_eras(), "default": "extraction_now", "sample": compile_era("extraction_now")["primary_dps"]}


@router.post("/forge/archetype")
async def forge_archetype(http_request: Request, request: Dict[str, Any], state=Depends(_state), attester: str = Depends(require_charter("forge", "archetype"))) -> Dict[str, Any]:
    replay = _idempotency.replay(dict(http_request.headers))
    if replay is not None:
        return replay  # type: ignore[return-value]
    from skeleton.forge.archetypes import default_library
    from skeleton.application.command_contracts import MATERIALISE_TARGETS

    forge = _require(state.forge, "Forge")
    name = _text_field(request, "name", "extraction")
    era = _text_field(request, "era", "extraction_now")
    target = _text_field(request, "target", "godot", allowed=MATERIALISE_TARGETS)
    bp = default_library().build(forge, name)
    repair = _bool_field(request, "repair", target == "godot")
    max_rounds = _int_field(request, "max_rounds", 3, minimum=1)
    artefact = forge.materialise(bp, era=era, target=target, repair=repair, max_rounds=max_rounds)
    response = {
        "blueprint_id": bp.blueprint_id,
        "artefact": artefact,
        "status": "materialised",
        "verification": artefact.get("verification"),
        "verify_loop": artefact.get("verify_loop"),
        "repair": artefact.get("repair"),
    }
    _idempotency.remember(dict(http_request.headers), response)
    return response


@router.post("/intelligence/reason")
async def intelligence_reason(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.intelligence, "Intelligence").reason(
        query=_text_field(request, "query", ""),
        context=_mapping_field(request, "context", None, optional=True),
    )


@router.post("/resilience/sanitise")
async def resilience_sanitise(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    fortress = _require(state.resilience, "Resilience")
    sanitized, report = fortress.process_input(
        raw_input=_text_field(request, "input", ""),
        user_id=_text_field(request, "user_id", "anonymous"),
    )
    level = getattr(report.level, "name", None) or getattr(report.level, "value", str(report.level))
    return {
        "sanitized": sanitized,
        "threat_level": level,
        "confidence": getattr(report, "confidence", None),
        "action": getattr(report, "action_taken", None),
    }


@router.get("/resilience/stats")
async def resilience_stats(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.resilience, "Resilience").stats()


@router.get("/context/snapshot")
async def context_snapshot(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.cockpit, "Cockpit").snapshot()


@router.post("/context/command")
async def context_command(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.cockpit, "Cockpit").apply(_text_field(request, "command", ""))


@router.post("/gameforge/run")
async def gameforge_run(http_request: Request, request: Dict[str, Any], state=Depends(_state), attester: str = Depends(require_charter("forge", "run"))) -> Dict[str, Any]:
    replay = _idempotency.replay(dict(http_request.headers))
    if replay is not None:
        return replay  # type: ignore[return-value]
    from skeleton.application.command_contracts import MATERIALISE_TARGETS

    runner = _require(state.gameforge, "GameForge")
    out = runner.execute(
        _text_field(request, "vision", ""),
        era=_text_field(request, "era", "") or None,
        archetype=_text_field(request, "archetype", "extraction"),
        target=_text_field(request, "target", "godot", allowed=MATERIALISE_TARGETS),
    )
    # files can be large; keep names in the HTTP body
    files = out.get("files") or {}
    out = dict(out)
    out["file_names"] = sorted(files)
    if not _bool_field(request, "include_files", False):
        out.pop("files", None)
    _idempotency.remember(dict(http_request.headers), out)
    return out


@router.post("/gameforge/intake")
async def gameforge_intake(http_request: Request, request: Dict[str, Any], state=Depends(_state), attester: str = Depends(require_charter("forge", "intake"))) -> Dict[str, Any]:
    replay = _idempotency.replay(dict(http_request.headers))
    if replay is not None:
        return replay  # type: ignore[return-value]
    from skeleton.context.questionnaire import intake
    from skeleton.application.command_contracts import MATERIALISE_TARGETS

    answers = _mapping_field(request, "answers", {}, optional=False) or {}
    taken = intake(answers)
    runner = _require(state.gameforge, "GameForge")
    out = runner.execute(
        taken.vision,
        era=taken.era,
        answers=answers,
        project_root=_text_field(request, "project_root", None, optional=True),
        overwrite=_bool_field(request, "overwrite", False),
        target=_text_field(request, "target", "godot", allowed=MATERIALISE_TARGETS),
        archetype=_text_field(request, "archetype", "extraction"),
    )
    files = out.get("files") or {}
    out = dict(out)
    out["intake"] = taken.to_dict()
    out["file_names"] = sorted(files)
    if not _bool_field(request, "include_files", False):
        out.pop("files", None)
    _idempotency.remember(dict(http_request.headers), out)
    return out


@router.get("/auth/github")
async def github_oauth_card() -> Dict[str, Any]:
    """The exact strings to paste into GitHub → New OAuth App."""
    from skeleton.api.oauth import oauth_card
    return oauth_card()


@router.get("/auth/github/start")
async def github_oauth_start() -> Dict[str, Any]:
    from skeleton.api.oauth import authorize_url, client_id
    if not client_id():
        raise HTTPException(status_code=503, detail="SKELETON_GITHUB_CLIENT_ID unset")
    return authorize_url()


@router.get("/auth/github/callback")
async def github_oauth_callback(code: str = "", state: str = "") -> Dict[str, Any]:
    from skeleton.api.oauth import exchange_code
    if not code:
        raise HTTPException(status_code=400, detail="missing code")
    out = exchange_code(code)
    safe = {k: v for k, v in out.items() if k != "access_token"}
    safe["state"] = state
    return safe
