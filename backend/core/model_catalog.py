"""Safe chat-model projection of the existing canonical engine inventory.

The backend owns a read-only product projection. Provider configuration,
credentials, activation, policy and inference remain in the engine process.
"""

from __future__ import annotations

import hashlib
import asyncio
import json
import re
from collections.abc import Mapping
from typing import Any

from core.engine_client import (
    EngineAuthorizationError,
    EngineClient,
    EngineClientError,
    EngineProtocolError,
)
from skeleton.contracts.context import ContextBudget

CATALOG_SCHEMA = "skeleton.chat_model_catalog.v1"
_MAX_ROWS = 16
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REFERENCE_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_READINESS = {
    "ready": ("Ready for chat.", None),
    "engine_not_configured": (
        "The AI engine has not been connected.",
        "Ask an administrator to configure the AI engine.",
    ),
    "engine_unavailable": (
        "The AI engine cannot be reached right now.",
        "Try again shortly or ask an administrator to check the engine.",
    ),
    "engine_access_denied": (
        "The AI engine has not granted access for this workspace.",
        "Ask an administrator to review engine access for this workspace.",
    ),
    "engine_inventory_invalid": (
        "The AI engine returned an incompatible model catalog.",
        "Ask an administrator to update the engine and application together.",
    ),
    "tenant_inventory_unavailable": (
        "This engine does not expose an authenticated tenant-scoped model inventory.",
        "Ask an administrator to enable an engine endpoint bound to this tenant and user.",
    ),
    "provider_architecture_unacknowledged": (
        "This model has not passed the required runtime configuration checks.",
        "Ask an administrator to restore the engine construction contracts.",
    ),
    "provider_credentials_missing": (
        "Hosted AI credentials are not configured.",
        "Ask an administrator to configure a hosted provider or activate a local model.",
    ),
    "provider_sdk_unavailable": (
        "The hosted provider runtime is unavailable.",
        "Ask an administrator to install the configured provider runtime.",
    ),
    "provider_configuration_unavailable": (
        "This provider is not ready to serve chat.",
        "Ask an administrator to review the provider configuration.",
    ),
    "local_model_not_configured": (
        "No local model artifact has been activated.",
        "Ask an administrator to activate a governed local model and restart the engine.",
    ),
    "local_artifact_invalid": (
        "The local model artifact could not be loaded safely.",
        "Ask an administrator to replace the artifact with a valid governed model and restart the engine.",
    ),
    "local_external_fallback_denied": (
        "Local mode contains an unsupported hosted fallback configuration.",
        "Ask an administrator to remove external fallback settings from local mode.",
    ),
    "local_external_verifier_denied": (
        "Local mode contains an unsupported hosted verifier configuration.",
        "Ask an administrator to remove external verifier settings from local mode.",
    ),
    "local_configuration_invalid": (
        "The local model settings are invalid.",
        "Ask an administrator to review the local engine settings.",
    ),
    "local_model_unavailable": (
        "The activated local model is no longer ready.",
        "Ask an administrator to verify its artifact and restart the engine.",
    ),
    "no_ready_model": (
        "No configured model is ready for chat.",
        "Choose a ready model or ask an administrator to configure one.",
    ),
    "automatic_route_unavailable": (
        "Automatic model routing is unavailable.",
        "Choose a ready model from the model list.",
    ),
    "model_selection_invalid": (
        "The selected model is not in the current engine catalog.",
        "Refresh the model list and choose a configured model.",
    ),
    "model_selection_unavailable": (
        "The selected model is currently unavailable.",
        "Choose another ready model or review its readiness message.",
    ),
    "model_context_too_small": (
        "This model has too little configured context for chat policy and output reserves.",
        "Increase the local model context setting or choose another configured model.",
    ),
    "model_temperature_unsupported": (
        "The selected model does not support temperature settings.",
        "Use its default sampling settings or choose a supported model.",
    ),
}


class ModelSelectionError(ValueError):
    """A requested product selection cannot cross the engine boundary."""

    def __init__(self, code: str, *, status_code: int = 422) -> None:
        self.code = code
        self.status_code = status_code
        self.readiness = readiness(code)
        super().__init__(self.readiness["message"])


def readiness(code: str) -> dict[str, str | None]:
    """Return only allowlisted product messages, never engine exception text."""
    normalized = code if code in _READINESS else "provider_configuration_unavailable"
    message, action = _READINESS[normalized]
    return {"code": normalized, "message": message, "action": action}


def _text(value: object, *, maximum: int, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > maximum:
        raise EngineProtocolError("model catalog contains an invalid identity")
    if any(ord(character) < 32 for character in value):
        raise EngineProtocolError("model catalog identity contains control characters")
    return value


def _integer(value: object, *, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise EngineProtocolError("model catalog contains an invalid capacity")
    return value


def _activation(value: object, model_id: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise EngineProtocolError("model catalog artifact identity is invalid")
    schema = _text(value.get("schema"), maximum=128)
    if schema not in {
        "reference_ngram",
        "skeleton.numpy_recurrent_lm.v1",
        "skeleton.local_model.deployment.v1",
    }:
        raise EngineProtocolError("model catalog artifact schema is unsupported")
    artifact_model = _text(value.get("model_id"), maximum=256)
    if model_id != artifact_model:
        raise EngineProtocolError("model catalog artifact/model identity mismatch")
    digests = {}
    for key in ("model_digest", "artifact_sha256"):
        digest = value.get(key)
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise EngineProtocolError("model catalog artifact digest is invalid")
        digests[key] = digest
    if schema == "skeleton.local_model.deployment.v1":
        extra = {}
        for key in ("manifest_digest", "runtime_digest"):
            value_digest = value.get(key)
            if not isinstance(value_digest, str) or _DIGEST.fullmatch(value_digest) is None:
                raise EngineProtocolError("model catalog deployment digest is invalid")
            extra[key] = value_digest
        reference = "local-model-deployment:" + extra["manifest_digest"]
        if value.get("reference") != reference or value.get("runtime_kind") != "llama.cpp-cli":
            raise EngineProtocolError("model catalog deployment identity is invalid")
        return {
            "schema": schema,
            "model_id": artifact_model,
            **digests,
            **extra,
            "artifact_bytes": _integer(value.get("artifact_bytes"), maximum=1024**4),
            "runtime_kind": "llama.cpp-cli",
            "reference": reference,
        }
    reference = "local-model-artifact:" + digests["artifact_sha256"]
    if value.get("reference", reference) != reference:
        raise EngineProtocolError("model catalog artifact reference is invalid")
    return {
        "schema": schema,
        "model_id": artifact_model,
        **digests,
        "artifact_bytes": _integer(value.get("artifact_bytes"), maximum=128 * 1024 * 1024),
        "reference": reference,
    }


def _local_handoff(*, activated: bool) -> dict[str, Any]:
    return {
        "credential_free": True,
        "activated": activated,
        "operator_required": True,
        "configuration_keys": ["AI_PROVIDER", "AI_LOCAL_MODEL_PATH", "AI_LOCAL_DEPLOYMENT_PATH"],
        "configuration_exclusive_alternatives": [["AI_LOCAL_MODEL_PATH", "AI_LOCAL_DEPLOYMENT_PATH"]],
        "required_provider_value": "local",
        "restart_required": True,
        "instruction": "An administrator can export a governed local model, configure AI_LOCAL_MODEL_PATH or an approved AI_LOCAL_DEPLOYMENT_PATH manifest exclusively, and restart the engine. No hosted AI credentials are required.",
        "production_promotion_authorized": False,
    }


def unavailable_catalog(code: str) -> dict[str, Any]:
    return {
        "schema_version": CATALOG_SCHEMA,
        "engine": "skeleton-engine",
        "available": False,
        "automatic_available": False,
        "active": None,
        "models": [],
        "providers": [],
        "readiness": readiness(code),
        "local_activation": _local_handoff(activated=False),
    }


def catalog_from_inventory(inventory: Mapping[str, Any]) -> dict[str, Any]:
    """Project bounded explicit runtime rows; reject missing capability metadata."""
    if not isinstance(inventory, Mapping) or type(inventory.get("available")) is not bool:
        raise EngineProtocolError("model inventory availability is invalid")
    active_provider = _text(inventory.get("active"), maximum=128)
    rows = inventory.get("providers")
    if not isinstance(rows, list) or not 1 <= len(rows) <= _MAX_ROWS:
        raise EngineProtocolError("model inventory row count is invalid")
    models, providers, seen = [], [], set()
    active = None
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise EngineProtocolError("model inventory row is invalid")
        provider_id = _text(raw.get("id"), maximum=128)
        if provider_id in seen:
            raise EngineProtocolError("model inventory provider is duplicated")
        seen.add(provider_id)
        model_id = _text(raw.get("model"), maximum=256, optional=True)
        if type(raw.get("available")) is not bool or type(raw.get("architecture_acknowledged")) is not bool:
            raise EngineProtocolError("model inventory readiness is invalid")
        mode = raw.get("execution_mode")
        local = provider_id == "local"
        if (
            mode != ("local" if local else "hosted")
            or type(raw.get("credential_free")) is not bool
            or raw["credential_free"] != local
        ):
            raise EngineProtocolError("model inventory execution mode is invalid")
        available = raw["available"] and raw["architecture_acknowledged"]
        code = "ready" if available else raw.get("readiness_code", "provider_configuration_unavailable")
        if not isinstance(code, str):
            raise EngineProtocolError("model inventory readiness code is invalid")
        activation = _activation(raw.get("artifact"), model_id)
        if local and available and activation is None:
            raise EngineProtocolError("ready local model lacks activation identity")
        providers.append(
            {
                "provider_id": provider_id,
                "available": available,
                "active": provider_id == active_provider,
                "fallback": raw.get("fallback") is True,
                "credential_free": local,
                "execution_mode": mode,
                "configured": raw.get("configured") is True,
                "architecture_acknowledged": raw["architecture_acknowledged"],
                "readiness": readiness(code),
            }
        )
        if model_id is None:
            if available:
                raise EngineProtocolError("ready provider has no model identity")
            continue
        context_window = _integer(raw.get("context_window"), maximum=1_048_576)
        max_output = _integer(raw.get("max_output_tokens"), maximum=16_384)
        default_output = _integer(raw.get("default_output_tokens"), maximum=max_output)
        if raw.get("limits_source") != "engine_chat_policy":
            raise EngineProtocolError("model inventory context/output capacity is invalid")
        if max_output >= context_window or default_output + 3072 >= context_window:
            available, code = False, "model_context_too_small"
            providers[-1].update(available=False, readiness=readiness(code))
        tokenizer = raw.get("tokenizer")
        if tokenizer not in {"utf8_bytes", "reference_tokens", "approximate_text"} or (
            not local and tokenizer != "approximate_text"
        ):
            raise EngineProtocolError("model inventory tokenizer profile is invalid")
        capabilities = raw.get("capabilities")
        supports_temperature = raw.get("supports_temperature")
        if type(supports_temperature) is not bool or (local and supports_temperature):
            raise EngineProtocolError("model inventory sampling capability is invalid")
        known = {
            "text-generation",
            "image-generation",
            "image-variation",
            "image-editing",
            "speech-synthesis",
        }
        if (
            not isinstance(capabilities, list)
            or not capabilities
            or any(not isinstance(capability, str) or capability not in known for capability in capabilities)
            or len(set(capabilities)) != len(capabilities)
        ):
            raise EngineProtocolError("model inventory capabilities are invalid")
        label = (
            ("Local model" if local else "OpenAI" if provider_id == "openai" else "Hosted model")
            + " · "
            + model_id
        )
        row = {
            "id": provider_id + ":" + model_id,
            "provider_id": provider_id,
            "model_id": model_id,
            "label": label,
            "available": available,
            "selectable": available and "text-generation" in capabilities,
            "active": provider_id == active_provider,
            "credential_free": local,
            "execution_mode": mode,
            "context_window": context_window,
            "max_output_tokens": max_output,
            "default_output_tokens": default_output,
            "limits_source": "engine_chat_policy",
            "tokenizer": tokenizer,
            "capabilities": list(capabilities),
            "supports_temperature": supports_temperature,
            "readiness": readiness(code),
            "activation": activation,
        }
        models.append(row)
        if row["active"]:
            active = {"provider_id": provider_id, "model_id": model_id}
    if active_provider not in seen:
        raise EngineProtocolError("model inventory active provider is missing")
    available = any(row["selectable"] for row in models)
    issue = (
        readiness("ready")
        if available
        else next((row["readiness"] for row in providers if row["active"]), readiness("no_ready_model"))
    )
    return {
        "schema_version": CATALOG_SCHEMA,
        "engine": "skeleton-engine",
        "available": available,
        "automatic_available": inventory["available"]
        and not any(
            row["readiness"]["code"] == "model_context_too_small"
            and (
                row["active"]
                or row["provider_id"]
                in {provider["provider_id"] for provider in providers if provider["fallback"]}
            )
            for row in models
        ),
        "active": active,
        "models": models,
        "providers": providers,
        "readiness": issue,
        "local_activation": _local_handoff(
            activated=any(row["credential_free"] and row["available"] for row in models)
        ),
    }


async def model_catalog(client: EngineClient | None, *, actor_id: str, tenant_id: str) -> dict[str, Any]:
    """Read the tenant-authorized engine inventory without loading any model."""
    _text(actor_id, maximum=512)
    _text(tenant_id, maximum=512)
    if client is None:
        return unavailable_catalog("engine_not_configured")
    # The legacy provider_status() method accepts only trace_id. Its global
    # provider listing cannot authorize tenant-specific model selection.
    # Require an explicitly scoped engine capability instead of exposing it.
    scoped = getattr(client, "tenant_model_inventory", None)
    if not callable(scoped):
        return unavailable_catalog("tenant_inventory_unavailable")
    try:
        inventory = await asyncio.wait_for(scoped(actor_id=actor_id, tenant_id=tenant_id), timeout=2)
        return catalog_from_inventory(inventory)
    except EngineAuthorizationError:
        return unavailable_catalog("engine_access_denied")
    except EngineProtocolError:
        return unavailable_catalog("engine_inventory_invalid")
    except (EngineClientError, asyncio.TimeoutError):
        return unavailable_catalog("engine_unavailable")


def resolve_selection(
    catalog: Mapping[str, Any], *, provider_id: str | None = None, model_id: str | None = None
) -> dict[str, Any]:
    """Resolve an exact pair or preserve the existing automatic engine route."""
    if (provider_id is None) != (model_id is None):
        raise ModelSelectionError("model_selection_invalid")
    if catalog.get("schema_version") != CATALOG_SCHEMA:
        raise ModelSelectionError("engine_inventory_invalid", status_code=503)
    models = catalog.get("models", [])
    if provider_id is not None:
        try:
            _text(provider_id, maximum=128)
            _text(model_id, maximum=256)
        except EngineProtocolError as exc:
            raise ModelSelectionError("model_selection_invalid") from exc
        selected = next(
            (row for row in models if row["provider_id"] == provider_id and row["model_id"] == model_id), None
        )
        if selected is None:
            raise ModelSelectionError("model_selection_invalid")
        if selected["selectable"] is not True:
            raise ModelSelectionError("model_selection_unavailable", status_code=503)
        return {
            **selected,
            "context_tokenizer": selected["tokenizer"],
            "selection_mode": "explicit",
            "selection_provider_id": provider_id,
            "selection_model_id": model_id,
        }
    if catalog.get("automatic_available") is not True:
        if catalog.get("available") is True:
            raise ModelSelectionError("automatic_route_unavailable", status_code=503)
        issue = catalog.get("readiness") or {}
        raise ModelSelectionError(issue.get("code", "no_ready_model"), status_code=503)
    providers = catalog.get("providers", [])
    eligible = {row["provider_id"] for row in providers if row["active"] or row["fallback"]}
    routes = [row for row in models if row["provider_id"] in eligible]
    ready = [row for row in routes if row["selectable"]]
    if not ready:
        raise ModelSelectionError("no_ready_model", status_code=503)
    selected = next((row for row in ready if row["active"]), ready[0])
    profiles = {row["tokenizer"] for row in routes}
    context_tokenizer = next(iter(profiles)) if len(profiles) == 1 else "utf8_bytes"
    # Automatic routing can use only declared fallbacks. Compile to the lowest
    # capacity among those routes while leaving dispatch selection unset.
    return {
        **selected,
        "context_tokenizer": context_tokenizer,
        "context_window": min(row["context_window"] for row in routes),
        "max_output_tokens": min(row["max_output_tokens"] for row in routes),
        "default_output_tokens": min(row["default_output_tokens"] for row in routes),
        "supports_temperature": all(row["supports_temperature"] for row in routes),
        "selection_mode": "automatic",
        "selection_provider_id": None,
        "selection_model_id": None,
    }


def context_budget_for_selection(
    selection: Mapping[str, Any], *, output_tokens: int | None = None
) -> ContextBudget:
    """Use selected runtime limits in the canonical context compilation budget."""
    output = selection["default_output_tokens"] if output_tokens is None else output_tokens
    if type(output) is not int or not 1 <= output <= selection["max_output_tokens"]:
        raise ModelSelectionError("model_selection_invalid")
    capacity = selection["context_window"]
    if output + 3072 >= capacity:
        raise ModelSelectionError("model_selection_invalid")
    input_capacity = capacity - output - 3072
    return ContextBudget(
        max_context_tokens=capacity,
        reserved_output_tokens=output,
        reserved_tool_result_tokens=0,
        reserved_policy_tokens=2048,
        safety_margin_tokens=1024,
        max_segment_tokens=min(40_000, input_capacity),
        max_artifact_tokens=min(16_000, input_capacity),
        max_tool_result_tokens=min(16_000, input_capacity),
    )


def estimate_context_tokens(text: str, selection: Mapping[str, Any]) -> int:
    """Count a fragment; the route must also bound the final framed projection."""
    profile = selection.get("context_tokenizer", selection["tokenizer"])
    if profile == "utf8_bytes":
        return max(1, len(text.encode("utf-8")) + 1)
    if profile == "reference_tokens":
        return max(1, sum(1 for _ in _REFERENCE_TOKEN.finditer(text)))
    return max(1, (len(text) + 3) // 4)


def catalog_digest(catalog: Mapping[str, Any]) -> str:
    """Content identity for UI refresh decisions; it grants no execution authority."""
    raw = json.dumps(
        catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    return hashlib.sha256(raw).hexdigest()
