"""Jeeves primary-model custody: strictly local text inference, no hosted fallback.

This policy is deliberately small and dependency-free. It never guesses that
a local GGUF exists or changes the trusted native/SQLite/Mongo guard contract.
Multimodal components can provide reviewed context, but cannot be selected as
the primary assistant or redirect inference to a hosted model.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping

LOCAL_ONLY_KEY = "JEEVES_LOCAL_ONLY"
MODEL_ID_KEY = "JEEVES_PRIMARY_MODEL_ID"
MODEL_ID = "jeeves"
_LOCAL_SOURCES = (
    "AI_LOCAL_MODEL_PATH",
    "AI_LOCAL_DEPLOYMENT_PATH",
    "AI_LOCAL_MODEL_CATALOG_PATH",
)
_EXTERNAL_FALLBACK = (
    "AI_SECONDARY_API_KEY",
    "AI_SECONDARY_BASE_URL",
    "AI_SECONDARY_MODEL",
    "AI_VERIFICATION_MODEL",
)
_TRUTHY = frozenset(("1", "true"))
_FALSEY = frozenset(("", "0", "false"))


class JeevesLocalPolicyError(ValueError):
    """Local-only primary model configuration or routing is not admissible."""


def is_local_only(environment: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environment is None else environment
    raw = str(source.get(LOCAL_ONLY_KEY, "")).strip().lower()
    if raw not in _TRUTHY | _FALSEY:
        raise JeevesLocalPolicyError("Jeeves local-only policy has an invalid boolean value")
    return raw in _TRUTHY


def primary_model_id(environment: Mapping[str, str] | None = None) -> str:
    source = os.environ if environment is None else environment
    identity = str(source.get(MODEL_ID_KEY, MODEL_ID)).strip()
    # Jeeves is a real artifact identity, not an unverified runtime alias.
    if identity != MODEL_ID:
        raise JeevesLocalPolicyError("Jeeves primary model identity must be exactly jeeves")
    return identity


def require_local_configuration(
    environment: Mapping[str, str] | None = None,
    *,
    require_source: bool = True,
) -> str | None:
    """Fail before any external adapter is constructed or network I/O occurs.

    Only one local artifact/deployment/catalog is admitted. Existing ambient
    hosted credentials are never consulted for local inference, and explicit
    secondary/verifier routes are denied in the primary model control plane.
    """
    source = os.environ if environment is None else environment
    if not is_local_only(source):
        raise JeevesLocalPolicyError("Jeeves local-only mode must be explicitly active")
    primary_model_id(source)
    if str(source.get("AI_PROVIDER", "local")).strip().lower() != "local":
        raise JeevesLocalPolicyError("Jeeves may only activate AI_PROVIDER=local")
    for key in _EXTERNAL_FALLBACK:
        if str(source.get(key, "")).strip():
            raise JeevesLocalPolicyError("Jeeves may not use an external fallback or verifier")
    choices = [key for key in _LOCAL_SOURCES if str(source.get(key, "")).strip()]
    if len(choices) > 1 or (require_source and not choices):
        raise JeevesLocalPolicyError("Jeeves requires exactly one pinned local model source")
    return choices[0] if choices else None


def require_primary_selection(
    provider_id: str | None,
    model_id: str | None,
    environment: Mapping[str, str] | None = None,
) -> None:
    """Validate explicit user model choice before any canonical chat mutation.

    The omitted pair is permitted; engine automatic selection is local-only
    when require_local_configuration has been admitted. No silent remapping of
    a foreign model to Jeeves is permitted.
    """
    source = os.environ if environment is None else environment
    if not is_local_only(source):
        return
    primary_model_id(source)
    if provider_id is None and model_id is None:
        return
    if provider_id != "local" or model_id != MODEL_ID:
        raise JeevesLocalPolicyError("Jeeves chat only permits the local jeeves model")


def require_local_inventory(
    models: list[dict[str, object]],
    environment: Mapping[str, str] | None = None,
) -> None:
    """No provider-media adapter or non-Jeeves model may become active."""
    source = os.environ if environment is None else environment
    if not is_local_only(source):
        return
    primary_model_id(source)
    for model in models:
        if model.get("provider_id") != "local" or model.get("model_id") != MODEL_ID:
            raise JeevesLocalPolicyError("Jeeves inventory contains a nonlocal or nonprimary model")
