"""Shared fail-closed guard for user-controlled host code execution.

Host execution is a privileged capability. A single development toggle must
never be enough to enable user-controlled code on an unclassified or deployed
runtime. Only an explicitly local development/test environment may use the
single-key opt-in; every other environment requires a second production-host
acknowledgement.
"""

from __future__ import annotations

import os

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_LOCAL_ENVIRONMENTS = frozenset({"local", "dev", "development", "test", "testing"})
_PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production", "stage", "staging"})
_PRODUCTION_MARKERS = (
    "K_SERVICE",  # Google Cloud Run
    "GAE_ENV",  # Google App Engine
    "KUBERNETES_SERVICE_HOST",  # Kubernetes
    "WEBSITE_INSTANCE_ID",  # Azure App Service
    "FUNCTIONS_WORKER_RUNTIME",  # Azure Functions
    "DYNO",  # Heroku
    "RENDER",  # Render
    "RENDER_SERVICE_ID",
    "RAILWAY_ENVIRONMENT",
    "RAILWAY_PROJECT_ID",
    "FLY_APP_NAME",
    "VERCEL",
    "VERCEL_ENV",
    "AWS_EXECUTION_ENV",
    "AWS_LAMBDA_FUNCTION_NAME",
    "ECS_CONTAINER_METADATA_URI",
    "ECS_CONTAINER_METADATA_URI_V4",
    "CF_INSTANCE_GUID",  # Cloud Foundry
    "NOMAD_ALLOC_ID",  # HashiCorp Nomad
)


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE_VALUES


def _environment_name() -> str:
    """Return the normalized deployment environment label, if explicitly set."""
    return os.environ.get("ENVIRONMENT", os.environ.get("ENV", "")).strip().lower()


def production_runtime_detected() -> bool:
    """Return True when the process positively identifies as a deployed host."""
    if _truthy("EMERGENT_DEPLOY"):
        return True
    if _environment_name() in _PRODUCTION_ENVIRONMENTS:
        return True
    return any(bool(os.environ.get(marker)) for marker in _PRODUCTION_MARKERS)


def explicit_local_runtime() -> bool:
    """Return True only for an explicitly labelled local/test runtime.

    Hosted-runtime markers always win over a misleading ``ENVIRONMENT=dev`` so
    copied development configuration cannot downgrade a deployed process.
    """
    return _environment_name() in _LOCAL_ENVIRONMENTS and not production_runtime_detected()


def production_override_required() -> bool:
    """Unknown/unlabelled runtimes are privileged, not implicitly local."""
    return not explicit_local_runtime()


def code_execution_enabled() -> bool:
    """Return whether user-controlled host execution is explicitly permitted.

    All environments require ``ALLOW_UNSAFE_CODE_EXECUTION=true``. Only an
    explicitly local/dev/test process may stop there. Production, staging,
    hosted, and unknown/unlabelled runtimes additionally require
    ``ALLOW_PRODUCTION_HOST_CODE_EXECUTION=true``.
    """
    if not _truthy("ALLOW_UNSAFE_CODE_EXECUTION"):
        return False
    if production_override_required():
        return _truthy("ALLOW_PRODUCTION_HOST_CODE_EXECUTION")
    return True


def execution_disabled_message(action: str = "Code execution") -> str:
    if production_override_required():
        return (
            f"{action} is disabled on this application host. "
            "Use an isolated sandbox, or explicitly set both execution overrides "
            "only for a deliberately isolated worker."
        )
    return (
        f"{action} is disabled by default. "
        "Set ALLOW_UNSAFE_CODE_EXECUTION=true only in a trusted isolated local environment."
    )


def execution_disabled_response(action: str = "Code execution") -> dict:
    return {
        "ok": False,
        "disabled": True,
        "error": execution_disabled_message(action),
    }


def require_execution_allowed(action: str = "Code execution") -> bool:
    """Compatibility predicate used by execution routes."""
    return code_execution_enabled()
