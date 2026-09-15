"""Versioned command contracts shared by API and CLI surfaces.

The contract layer deliberately owns transport-neutral semantics only: command
names, payload validation boundaries, normalized errors, exit codes, HTTP
status mappings, and feature-parity metadata. Runtime-specific handlers are
registered by adapters in :mod:`skeleton.application.runtime_commands`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

CONTRACT_VERSION = "1.0"


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
        "admin",
        "Inspect or perform administrative runtime operations.",
        mutating=True,
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
        "contract_version": CONTRACT_VERSION,
        "commands": rows,
        "full_surface_parity": all(row["parity"] for row in rows),
    }


_ERROR_DEFAULTS: Mapping[str, tuple[int, int]] = {
    # code -> (CLI exit code, HTTP status)
    "invalid_command": (2, 404),
    "invalid_argument": (2, 422),
    "unsupported_operation": (3, 501),
    "unavailable": (3, 503),
    "forbidden": (4, 403),
    "conflict": (5, 409),
    "internal_error": (70, 500),
}


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
        super().__init__(message)
        default_exit, default_http = _ERROR_DEFAULTS.get(code, _ERROR_DEFAULTS["internal_error"])
        self.code = code
        self.message = message
        self.details = dict(details or {})
        self.exit_code = default_exit if exit_code is None else int(exit_code)
        self.http_status = default_http if http_status is None else int(http_status)

    def to_dict(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            body["details"] = self.details
        return body


@dataclass(frozen=True)
class CommandResult:
    """Normalized command result consumed by both transports."""

    command: str
    ok: bool
    data: Mapping[str, Any] = field(default_factory=dict)
    error: Optional[CommandError] = None

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else (self.error.exit_code if self.error else 70)

    @property
    def http_status(self) -> int:
        return 200 if self.ok else (self.error.http_status if self.error else 500)

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "contract_version": CONTRACT_VERSION,
            "command": self.command,
            "ok": self.ok,
        }
        if self.ok:
            payload["data"] = dict(self.data)
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
