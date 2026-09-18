"""Versioned command contracts shared by API and CLI surfaces.

The contract layer deliberately owns transport-neutral semantics only: command
names, payload validation boundaries, normalized errors, exit codes, HTTP
status mappings, and feature-parity metadata. Runtime-specific handlers are
registered by adapters in :mod:`skeleton.application.runtime_commands`.

Issue #953 adds a versioned request schema, deterministic argument
normalization, secret-safe public payloads, bounded output, and explicit
sync/async boundaries. Those envelope rules live in
:mod:`skeleton.application.unified_invoke`; this module stays the shared
command family + error lattice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from skeleton.observability.redaction import redact_payload, redact_text

CONTRACT_VERSION = "1.0"
SCHEMA_VERSION = 1
SUPPORTED_MODE = "sync"
MATERIALISE_TARGETS = ("json", "yaml", "godot")
PROGRESSION_CURVES = ("linear", "quadratic", "exponential")


def require_bool(payload: Mapping[str, Any], key: str, default: bool = False) -> bool:
    """Return a real boolean; reject truthy/falsey stand-ins such as ``1`` or ``"false"``."""

    if default is not True and default is not False:
        raise CommandError("invalid_argument", f"{key} default must be a boolean")
    if key not in payload:
        return default is True
    value = payload[key]
    if value is not True and value is not False:
        raise CommandError("invalid_argument", f"{key} must be a boolean")
    return value is True


def require_int(
    payload: Mapping[str, Any],
    key: str,
    default: int,
    *,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    """Return a real integer; reject bools, floats, and numeric strings."""

    if isinstance(default, bool) or not isinstance(default, int):
        raise CommandError("invalid_argument", f"{key} default must be an integer")
    value: Any = default if key not in payload else payload[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise CommandError("invalid_argument", f"{key} must be an integer")
    if minimum is not None and value < minimum:
        raise CommandError("invalid_argument", f"{key} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise CommandError("invalid_argument", f"{key} must be <= {maximum}")
    return value


def require_float(
    payload: Mapping[str, Any],
    key: str,
    default: float,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    """Return a finite number; reject bools, numeric strings, NaN, and infinities."""

    if isinstance(default, bool) or not isinstance(default, (int, float)) or not math.isfinite(float(default)):
        raise CommandError("invalid_argument", f"{key} default must be a finite number")
    value: Any = default if key not in payload else payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CommandError("invalid_argument", f"{key} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise CommandError("invalid_argument", f"{key} must be finite")
    if minimum is not None and number < minimum:
        raise CommandError("invalid_argument", f"{key} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise CommandError("invalid_argument", f"{key} must be <= {maximum}")
    return number


def require_text(
    payload: Mapping[str, Any],
    key: str,
    default: Optional[str] = "",
    *,
    optional: bool = False,
    allowed: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """Return a real string; reject non-strings and values outside an allow-list."""

    if default is not None and not isinstance(default, str):
        raise CommandError("invalid_argument", f"{key} default must be a string")
    if key not in payload:
        if optional:
            return default
        value: Any = "" if default is None else default
    else:
        value = payload[key]
        if optional and value is None:
            return None
    if not isinstance(value, str):
        raise CommandError("invalid_argument", f"{key} must be a string")
    if allowed is not None:
        allowed_values = tuple(item for item in allowed if isinstance(item, str))
        if value not in allowed_values:
            raise CommandError(
                "invalid_argument",
                f"{key} must be one of {', '.join(sorted(allowed_values))}",
            )
    return value


def require_mapping(
    payload: Mapping[str, Any],
    key: str,
    default: Optional[Mapping[str, Any]] = None,
    *,
    optional: bool = True,
) -> Optional[Dict[str, Any]]:
    """Return a JSON object; reject strings, arrays, and other stand-ins."""

    if default is not None and (isinstance(default, (str, bytes, list, tuple)) or not isinstance(default, Mapping)):
        raise CommandError("invalid_argument", f"{key} default must be an object")
    if key not in payload:
        if optional:
            return dict(default) if isinstance(default, Mapping) else default
        return dict(default or {})
    value = payload[key]
    if optional and value is None:
        return None
    if isinstance(value, (str, bytes, list, tuple)) or not isinstance(value, Mapping):
        raise CommandError("invalid_argument", f"{key} must be an object")
    return dict(value)


def require_list(
    payload: Mapping[str, Any],
    key: str,
    default: Optional[list[Any]] = None,
    *,
    optional: bool = True,
    item_type: type | tuple[type, ...] | None = None,
) -> Optional[list[Any]]:
    """Return a JSON array; reject strings that would otherwise iterate as characters."""

    if default is not None and not isinstance(default, (list, tuple)):
        raise CommandError("invalid_argument", f"{key} default must be an array")
    if key not in payload:
        if optional:
            return list(default) if isinstance(default, (list, tuple)) else default
        return list(default or [])
    value = payload[key]
    if optional and value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise CommandError("invalid_argument", f"{key} must be an array")
    items = list(value)
    if item_type is not None:
        for item in items:
            if isinstance(item, bool) and item_type in {int, (int,)}:
                raise CommandError("invalid_argument", f"{key} items must be integers")
            if not isinstance(item, item_type):
                raise CommandError("invalid_argument", f"{key} items have the wrong type")
    return items


@dataclass(frozen=True)
class CommandSpec:
    """Transport-neutral description of one supported operation family."""

    name: str
    summary: str
    surfaces: tuple[str, ...] = ("api", "cli")
    mutating: bool = False
    streaming: bool = False
    auth_required: bool = False
    implementation: str = "shared"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "surfaces": list(self.surfaces),
            "mutating": self.mutating,
            "streaming": self.streaming,
            "auth_required": self.auth_required,
            "implementation": self.implementation,
        }


_SPECS = (
    CommandSpec(
        "run",
        "Execute a GameForge generation request.",
        mutating=True,
        auth_required=True,
    ),
    CommandSpec(
        "tool",
        "Inspect or invoke registered tool capabilities.",
        mutating=True,
        auth_required=True,
    ),
    CommandSpec(
        "memory",
        "Query the unified memory service.",
        auth_required=True,
    ),
    CommandSpec(
        "status",
        "Inspect runtime health and initialization state.",
    ),
    CommandSpec(
        "configuration",
        "Inspect non-secret runtime configuration metadata.",
    ),
    CommandSpec(
        "capabilities",
        "Inspect the curated capability manifest, lifecycle snapshot, or structural audits.",
    ),
    CommandSpec(
        "admin",
        "Inspect or perform administrative runtime operations.",
        mutating=True,
        auth_required=True,
    ),
    CommandSpec(
        "retrieve",
        "Query the canonical four-plane retrieval subsystem.",
        auth_required=True,
    ),
    CommandSpec(
        "plan",
        "Invoke canonical creator/game planning without a second planner.",
        auth_required=True,
    ),
    CommandSpec(
        "evidence",
        "Query canonical learning evidence or provenance records.",
        auth_required=True,
    ),
)


def command_specs() -> tuple[CommandSpec, ...]:
    return _SPECS


def parity_matrix() -> Dict[str, Any]:
    """Return the machine-readable API/CLI feature-parity matrix."""

    rows = []
    for spec in _SPECS:
        surfaces = set(spec.surfaces)
        row = spec.to_dict()
        row["api"] = "api" in surfaces
        row["cli"] = "cli" in surfaces
        row["parity"] = surfaces.issuperset({"api", "cli"})
        rows.append(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "mode": SUPPORTED_MODE,
        "async_supported": False,
        "commands": rows,
        "full_surface_parity": all(row["parity"] for row in rows),
    }


_ERROR_DEFAULTS: Mapping[str, tuple[int, int]] = {
    # code -> (CLI exit code, HTTP status)
    "invalid_command": (2, 404),
    "invalid_argument": (2, 422),
    "unknown_version": (2, 422),
    "payload_too_large": (2, 413),
    "unsupported_operation": (3, 501),
    "async_unsupported": (3, 501),
    "unavailable": (3, 503),
    "forbidden": (4, 403),
    "conflict": (5, 409),
    "internal_error": (70, 500),
}

_MAX_PUBLIC_MESSAGE_CHARS = 256


def _safe_public_message(message: str) -> str:
    cleaned = redact_text(str(message or ""))
    if len(cleaned) > _MAX_PUBLIC_MESSAGE_CHARS:
        return cleaned[:_MAX_PUBLIC_MESSAGE_CHARS] + "…"
    return cleaned


class CommandError(Exception):
    """Expected command failure with identical API and CLI semantics."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Optional[Mapping[str, Any]] = None,
        exit_code: Optional[int] = None,
        http_status: Optional[int] = None,
    ) -> None:
        default_exit, default_http = _ERROR_DEFAULTS.get(code, _ERROR_DEFAULTS["internal_error"])
        self.code = code
        self.message = _safe_public_message(message)
        super().__init__(self.message)
        self.details = dict(redact_payload(dict(details or {})))
        self.exit_code = default_exit if exit_code is None else int(exit_code)
        self.http_status = default_http if http_status is None else int(http_status)

    def to_dict(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            body["details"] = dict(self.details)
        return body


@dataclass(frozen=True)
class CommandResult:
    """Normalized command result consumed by both transports."""

    command: str
    ok: bool
    data: Mapping[str, Any] = field(default_factory=dict)
    error: Optional[CommandError] = None
    correlation_id: str = ""
    mode: str = SUPPORTED_MODE
    schema_version: int = SCHEMA_VERSION

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else (self.error.exit_code if self.error else 70)

    @property
    def http_status(self) -> int:
        return 200 if self.ok else (self.error.http_status if self.error else 500)

    def to_payload(self) -> Dict[str, Any]:
        from skeleton.application.contract_safety import public_contract_payload

        payload: Dict[str, Any] = {
            "schema_version": int(self.schema_version or SCHEMA_VERSION),
            "contract_version": CONTRACT_VERSION,
            "command": self.command,
            "ok": self.ok,
            "mode": self.mode or SUPPORTED_MODE,
            "correlation_id": self.correlation_id,
        }
        if self.ok:
            payload["data"] = public_contract_payload(dict(self.data))
        else:
            payload["error"] = (self.error or CommandError("internal_error", "command failed")).to_dict()
        return payload


Handler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class CommandService:
    """Small transport-neutral dispatcher for application command handlers."""

    def __init__(self, specs: Iterable[CommandSpec] = _SPECS) -> None:
        self._specs = {spec.name: spec for spec in specs}
        self._handlers: Dict[str, Handler] = {}

    def register(self, command: str, handler: Handler) -> "CommandService":
        if command not in self._specs:
            raise ValueError(f"unknown command contract: {command}")
        self._handlers[command] = handler
        return self

    def has_handler(self, command: str) -> bool:
        return command in self._handlers

    def execute(self, command: str, payload: Optional[Mapping[str, Any]] = None) -> CommandResult:
        name = str(command or "").strip().lower()
        if name not in self._specs:
            error = CommandError("invalid_command", f"unknown command: {name or '<empty>'}")
            return CommandResult(command=name, ok=False, error=error)

        handler = self._handlers.get(name)
        if handler is None:
            error = CommandError(
                "unsupported_operation",
                f"{name} is contracted but has no runtime handler",
                details={"command": name},
            )
            return CommandResult(command=name, ok=False, error=error)

        try:
            data = handler(dict(payload or {}))
            return CommandResult(command=name, ok=True, data=dict(data))
        except CommandError as exc:
            return CommandResult(command=name, ok=False, error=exc)
        except (TypeError, ValueError) as exc:
            error = CommandError("invalid_argument", str(exc) or "invalid command argument")
            return CommandResult(command=name, ok=False, error=error)
        except Exception as exc:  # transport boundary: normalize unexpected failures
            error = CommandError(
                "internal_error",
                "command execution failed",
                details={"exception": type(exc).__name__},
            )
            return CommandResult(command=name, ok=False, error=error)
