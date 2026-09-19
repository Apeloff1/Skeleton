"""Request pipeline / authN-Z glue — Throughput Middleware pack.

Extend-only assurance plane for principal binding, scope/role gates,
pipeline stages, and fail-closed filters. Does not touch api/server.py lifespan.
"""

from __future__ import annotations

from skeleton.request_pipeline.principal import Principal, bind_principal, verify_principal_token
from skeleton.request_pipeline.scopes import ScopeGate, RoleGate, evaluate_scope, evaluate_role
from skeleton.request_pipeline.pipeline import PipelineStage, RequestPipeline, default_pipeline
from skeleton.request_pipeline.filters import FilterChain, FilterVerdict, run_filters
from skeleton.request_pipeline.catalog import PIPELINE_CATALOG, describe_catalog
from skeleton.request_pipeline.operations import registry, digest_registry, playbook_smoke
from skeleton.request_pipeline.evidence import digest_plane, render_evidence

__all__ = [
    "Principal",
    "bind_principal",
    "verify_principal_token",
    "ScopeGate",
    "RoleGate",
    "evaluate_scope",
    "evaluate_role",
    "PipelineStage",
    "RequestPipeline",
    "default_pipeline",
    "FilterChain",
    "FilterVerdict",
    "run_filters",
    "PIPELINE_CATALOG",
    "describe_catalog",
    "registry",
    "digest_registry",
    "playbook_smoke",
    "digest_plane",
    "render_evidence",
]
