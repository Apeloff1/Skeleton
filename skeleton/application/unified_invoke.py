"""Smallest stable unified invoke envelope over canonical subsystems.

This is an adapter, not a second orchestration plane. Callers submit one
versioned request schema; this module normalizes arguments, rejects unknown
versions and async mode, refuses secret-bearing fields, and dispatches to the
existing :class:`~skeleton.application.command_contracts.CommandService`.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, replace
from typing import Any, Mapping, Optional

from .command_contracts import (
    SCHEMA_VERSION,
    SUPPORTED_MODE,
    CommandError,
    CommandResult,
    CommandService,
)
from .contract_safety import (
    MAX_OUTPUT_DEPTH,
    is_secret_key,
    normalize_key,
    public_contract_payload,
    safe_public_message,
)
from .runtime_commands import build_runtime_command_service

ENVELOPE_KEYS = frozenset({"schema_version", "command", "arguments", "correlation_id", "mode"})
CORRELATION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
MAX_REQUEST_BYTES = 65_536
MAX_REQUEST_NODES = 256
MAX_REQUEST_STRING_CHARS = 8_192
ARGUMENT_ALIASES: Mapping[str, str] = {
    "q": "query",
    "search": "query",
    "top_k": "k",
    "limit": "k",
    "n": "k",
    "era": "vision",
}

__all__ = [
    "ENVELOPE_KEYS",
    "MAX_REQUEST_BYTES",
    "UnifiedRequest",
    "invoke_unified",
    "normalize_request",
    "public_contract_payload",
]


@dataclass(frozen=True, slots=True)
class UnifiedRequest:
    """Deterministically normalized invoke envelope."""

    schema_version: int
    command: str
    arguments: Mapping[str, Any]
    correlation_id: str
    mode: str


def _mint_correlation_id() -> str:
    return uuid.uuid4().hex[:16]


def _valid_correlation_id(value: object) -> str | None:
    if isinstance(value, str) and CORRELATION_ID_RE.fullmatch(value.strip()):
        return value.strip()
    return None


def _count_nodes(value: Any, *, budget: list[int], depth: int = 0) -> None:
    if depth > MAX_OUTPUT_DEPTH:
        raise CommandError("payload_too_large", "request structure too deep")
    budget[0] -= 1
    if budget[0] < 0:
        raise CommandError("payload_too_large", "request structure too large")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CommandError("invalid_argument", "object keys must be strings")
            if len(key) > MAX_REQUEST_STRING_CHARS:
                raise CommandError("payload_too_large", "request object key too large")
            _count_nodes(item, budget=budget, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _count_nodes(item, budget=budget, depth=depth + 1)
        return
    if isinstance(value, str) and len(value) > MAX_REQUEST_STRING_CHARS:
        raise CommandError("payload_too_large", "request string too large")


def _encoded_size(value: Any) -> int:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return len(encoded.encode("utf-8"))


def _normalize_arguments(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise CommandError("invalid_argument", "arguments must be an object")
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in raw.items():
        if not isinstance(raw_key, str):
            raise CommandError("invalid_argument", "argument keys must be strings")
        key = ARGUMENT_ALIASES.get(normalize_key(raw_key), normalize_key(raw_key))
        if not key:
            raise CommandError("invalid_argument", "argument keys must not be empty")
        if is_secret_key(key) or is_secret_key(raw_key):
            raise CommandError(
                "invalid_argument",
                "secret-bearing arguments are not permitted",
                details={"key": normalize_key(raw_key)},
            )
        if key in normalized and normalized[key] != raw_value:
            raise CommandError(
                "invalid_argument",
                "argument aliases collided",
                details={"key": key},
            )
        normalized[key] = raw_value
    return {key: normalized[key] for key in sorted(normalized)}


def normalize_request(
    raw: Any,
    *,
    correlation_id: str | None = None,
) -> UnifiedRequest:
    """Parse and normalize one versioned invoke envelope. Fail closed."""

    if not isinstance(raw, Mapping):
        raise CommandError("invalid_argument", "request must be a JSON object")
    try:
        size = _encoded_size(dict(raw))
    except (TypeError, ValueError) as exc:
        raise CommandError("invalid_argument", "request is not JSON-serializable") from exc
    if size > MAX_REQUEST_BYTES:
        raise CommandError("payload_too_large", "request exceeds the bounded envelope")
    _count_nodes(raw, budget=[MAX_REQUEST_NODES])

    unknown = sorted(str(key) for key in raw if str(key) not in ENVELOPE_KEYS)
    if unknown:
        raise CommandError(
            "invalid_argument",
            "unknown envelope fields are not permitted",
            details={"fields": unknown},
        )

    if "schema_version" not in raw:
        raise CommandError("invalid_argument", "schema_version is required")
    version_raw = raw.get("schema_version")
    if isinstance(version_raw, bool) or not isinstance(version_raw, int):
        raise CommandError("unknown_version", "schema_version must be an integer")
    if version_raw != SCHEMA_VERSION:
        raise CommandError(
            "unknown_version",
            "unsupported schema_version",
            details={"schema_version": version_raw, "supported": SCHEMA_VERSION},
        )

    command = str(raw.get("command") or "").strip().lower()
    if not command:
        raise CommandError("invalid_command", "command name is required")

    mode_raw = raw.get("mode", SUPPORTED_MODE)
    if not isinstance(mode_raw, str):
        raise CommandError("invalid_argument", "mode must be a string")
    mode = mode_raw.strip().lower()
    if not mode:
        raise CommandError("invalid_argument", "mode must not be empty")
    if mode != SUPPORTED_MODE:
        raise CommandError(
            "async_unsupported",
            "only synchronous invocation is supported",
            details={"mode": mode},
        )

    body_correlation = _valid_correlation_id(raw.get("correlation_id"))
    header_correlation = _valid_correlation_id(correlation_id)
    if raw.get("correlation_id") not in (None, "") and body_correlation is None:
        raise CommandError("invalid_argument", "correlation_id is malformed")
    resolved = body_correlation or header_correlation or _mint_correlation_id()

    arguments = _normalize_arguments(raw.get("arguments"))
    return UnifiedRequest(
        schema_version=version_raw,
        command=command,
        arguments=arguments,
        correlation_id=resolved,
        mode=mode,
    )


def _result_from_error(
    error: CommandError,
    *,
    command: str = "",
    correlation_id: str = "",
    mode: str = SUPPORTED_MODE,
    schema_version: int = SCHEMA_VERSION,
) -> CommandResult:
    return CommandResult(
        command=command,
        ok=False,
        error=error,
        correlation_id=correlation_id,
        mode=mode,
        schema_version=schema_version,
    )


def invoke_unified(
    state: Any,
    raw: Any,
    *,
    correlation_id: str | None = None,
    service: Optional[CommandService] = None,
) -> CommandResult:
    """Normalize one envelope and dispatch it through the shared command service."""

    try:
        request = normalize_request(raw, correlation_id=correlation_id)
    except CommandError as exc:
        hinted_command = ""
        hinted_correlation = _valid_correlation_id(correlation_id) or ""
        if isinstance(raw, Mapping):
            hinted_command = str(raw.get("command") or "").strip().lower()
            hinted_correlation = _valid_correlation_id(raw.get("correlation_id")) or hinted_correlation
        return _result_from_error(
            exc,
            command=hinted_command,
            correlation_id=hinted_correlation,
        )

    dispatcher = service or build_runtime_command_service(state)
    result = dispatcher.execute(request.command, request.arguments)
    return replace(
        result,
        correlation_id=request.correlation_id,
        mode=request.mode,
        schema_version=request.schema_version,
    )