"""Canonical typed creator command surface for #807 B014.

The creator command surface is intentionally transport-neutral. CLI, API and UI
adapters all compile into the same versioned CreatorCommand and consume the
same operation catalog. This module does not grant execution, filesystem,
network, engine, deployment, or release authority; callers must supply explicit
operation handlers and enforce downstream policy boundaries.

B014 operations are fixed to the batch contract: create, edit, test, preview
and export.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Final, NoReturn

from skeleton.kernel.errors import SkeletonError


COMMAND_SCHEMA: Final = "creator.command.v1"
COMMAND_VERSION: Final = 1
SURFACE_SCHEMA: Final = "creator.command_surface.v1"
SURFACE_VERSION: Final = 1

OPERATIONS: Final = ("create", "edit", "test", "preview", "export")
SURFACES: Final = ("cli", "api", "ui")

MAX_PROJECT_ID_CHARS: Final = 128
MAX_IDENTIFIER_CHARS: Final = 160
MAX_TEXT_CHARS: Final = 32_768
MAX_LIST_ITEMS: Final = 256
MAX_OBJECT_FIELDS: Final = 512
MAX_JSON_DEPTH: Final = 16
MAX_JSON_NODES: Final = 8_192
MAX_COMMAND_BYTES: Final = 512 * 1024
MAX_RESULT_BYTES: Final = 512 * 1024

_ID_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,159}$")
_PROJECT_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$")
_TOKEN_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,159}$")


class CreatorCommandError(SkeletonError):
    """Creator command data is malformed, ambiguous, or unsupported."""

    code = "CRE.COMMAND_SURFACE"
    http_status = 400


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    kind: str
    required: bool
    description: str
    enum: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "required": self.required,
            "description": self.description,
            "enum": list(self.enum),
        }


@dataclass(frozen=True, slots=True)
class OperationSpec:
    name: str
    description: str
    fields: tuple[FieldSpec, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "fields": [field.to_dict() for field in self.fields],
        }


@dataclass(frozen=True, slots=True)
class SurfaceManifest:
    surface: str
    operations: tuple[OperationSpec, ...]
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SURFACE_SCHEMA,
            "schema_version": SURFACE_VERSION,
            "surface": self.surface,
            "operations": [operation.to_dict() for operation in self.operations],
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class CreatorCommand:
    operation: str
    project_id: str
    payload: Mapping[str, object]
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": COMMAND_SCHEMA,
            "schema_version": COMMAND_VERSION,
            "operation": self.operation,
            "project_id": self.project_id,
            "payload": dict(self.payload),
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class CreatorCommandReceipt:
    command_digest: str
    operation: str
    status: str
    output: Mapping[str, object]
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": COMMAND_SCHEMA,
            "schema_version": COMMAND_VERSION,
            "command_digest": self.command_digest,
            "operation": self.operation,
            "status": self.status,
            "output": dict(self.output),
            "digest": self.digest,
        }


_OPERATION_SPECS: Final = (
    OperationSpec(
        name="create",
        description="Compile a new creator project intent into downstream design work.",
        fields=(
            FieldSpec(
                "intent",
                "object",
                True,
                "Structured engine-neutral creator intent consumed by downstream compiler adapters.",
            ),
        ),
    ),
    OperationSpec(
        name="edit",
        description="Describe one bounded edit against an existing creator project.",
        fields=(
            FieldSpec(
                "target_id",
                "identifier",
                True,
                "Stable project/design node identifier to edit.",
            ),
            FieldSpec(
                "expected_revision",
                "non_negative_integer",
                True,
                "Optimistic-concurrency revision expected by the caller.",
            ),
            FieldSpec(
                "patch",
                "object",
                True,
                "Structured edit payload interpreted by the selected downstream editor.",
            ),
        ),
    ),
    OperationSpec(
        name="test",
        description="Request deterministic validation for selected creator scopes.",
        fields=(
            FieldSpec(
                "scopes",
                "identifier_list",
                True,
                "One or more project/design scopes to validate.",
            ),
            FieldSpec(
                "profile",
                "enum",
                True,
                "Validation breadth.",
                ("smoke", "focused", "full"),
            ),
        ),
    ),
    OperationSpec(
        name="preview",
        description="Request a preview for selected creator scopes without promotion authority.",
        fields=(
            FieldSpec(
                "scopes",
                "identifier_list",
                True,
                "One or more project/design scopes to preview.",
            ),
            FieldSpec(
                "mode",
                "enum",
                True,
                "Preview mode; runtime execution remains downstream and policy-bound.",
                ("static", "runtime"),
            ),
        ),
    ),
    OperationSpec(
        name="export",
        description="Request a bounded creator export from downstream export adapters.",
        fields=(
            FieldSpec(
                "format",
                "token",
                True,
                "Export format or adapter identifier.",
            ),
            FieldSpec(
                "artifact_name",
                "token",
                True,
                "Logical artifact name; this is not a filesystem path.",
            ),
        ),
    ),
)

_OPERATION_BY_NAME: Final = {spec.name: spec for spec in _OPERATION_SPECS}


def _fail(message: str, *, reason: str, **context: object) -> NoReturn:
    raise CreatorCommandError(message, context={"reason": reason, **context})


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("creator command contains non-canonical JSON data", reason="json_type")
        raise AssertionError("unreachable") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate JSON object field", reason="duplicate_field", field=key)
        result[key] = value
    return result


def _load_json_object(raw: str | bytes, *, label: str) -> dict[str, object]:
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            _fail(f"{label} is not valid UTF-8", reason="encoding")
            raise AssertionError("unreachable") from exc
    elif isinstance(raw, str):
        text = raw
    else:
        _fail(f"{label} must be text or UTF-8 bytes", reason="malformed")
    if not text or len(text.encode("utf-8")) > MAX_COMMAND_BYTES:
        _fail(f"{label} byte size is invalid", reason="bound")
    try:
        value = json.loads(text, object_pairs_hook=_unique_object)
    except CreatorCommandError:
        raise
    except json.JSONDecodeError:
        _fail(f"{label} is not valid JSON", reason="json")
    if not isinstance(value, dict):
        _fail(f"{label} root must be an object", reason="malformed")
    return value


def _project_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > MAX_PROJECT_ID_CHARS
        or _PROJECT_RE.fullmatch(value) is None
    ):
        _fail("project_id is not a canonical identifier", reason="project_id")
    return value


def _identifier(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > MAX_IDENTIFIER_CHARS
        or _ID_RE.fullmatch(value) is None
    ):
        _fail(
            f"{field} is not a canonical identifier",
            reason="field_type",
            field=field,
        )
    return value


def _token(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > MAX_IDENTIFIER_CHARS
        or _TOKEN_RE.fullmatch(value) is None
    ):
        _fail(
            f"{field} is not a canonical token",
            reason="field_type",
            field=field,
        )
    return value


def _bounded_json(value: object, *, field: str) -> object:
    nodes = 0

    def visit(current: object, depth: int) -> object:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_JSON_NODES:
            _fail(f"{field} exceeds JSON node bound", reason="bound", field=field)
        if depth > MAX_JSON_DEPTH:
            _fail(f"{field} exceeds JSON depth bound", reason="bound", field=field)
        if current is None or isinstance(current, bool):
            return current
        if isinstance(current, int):
            if abs(current) > 2**63 - 1:
                _fail(f"{field} integer exceeds supported range", reason="bound", field=field)
            return current
        if isinstance(current, float):
            if current != current or current in (float("inf"), float("-inf")):
                _fail(f"{field} contains non-finite number", reason="json_type", field=field)
            return current
        if isinstance(current, str):
            if len(current) > MAX_TEXT_CHARS:
                _fail(f"{field} text exceeds character bound", reason="bound", field=field)
            if any(ord(character) < 32 and character not in "\t\n\r" for character in current):
                _fail(f"{field} contains control characters", reason="malformed", field=field)
            return current
        if isinstance(current, list):
            if len(current) > MAX_LIST_ITEMS:
                _fail(f"{field} list exceeds item bound", reason="bound", field=field)
            return [visit(item, depth + 1) for item in current]
        if isinstance(current, dict):
            if len(current) > MAX_OBJECT_FIELDS:
                _fail(f"{field} object exceeds field bound", reason="bound", field=field)
            checked: list[tuple[str, object]] = []
            for key, item in current.items():
                if not isinstance(key, str) or not key or key != key.strip():
                    _fail(f"{field} contains invalid object key", reason="field_type", field=field)
                if len(key) > MAX_IDENTIFIER_CHARS:
                    _fail(f"{field} object key exceeds bound", reason="bound", field=field)
                checked.append((key, item))
            normalized: dict[str, object] = {}
            for key, item in sorted(checked, key=lambda pair: pair[0]):
                normalized[key] = visit(item, depth + 1)
            return normalized
        _fail(f"{field} contains unsupported JSON type", reason="json_type", field=field)

    normalized = visit(value, 0)
    if len(_canonical_json_bytes(normalized)) > MAX_COMMAND_BYTES:
        _fail(f"{field} exceeds serialized byte bound", reason="bound", field=field)
    return normalized


def _identifier_list(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        _fail(f"{field} must be a non-empty list", reason="field_type", field=field)
    if len(value) > MAX_LIST_ITEMS:
        _fail(f"{field} exceeds item bound", reason="bound", field=field)
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        identifier = _identifier(item, field=field)
        if identifier in seen:
            _fail(
                f"{field} contains duplicate identifier",
                reason="duplicate",
                field=field,
                identifier=identifier,
            )
        seen.add(identifier)
        result.append(identifier)
    return tuple(sorted(result))


def _validate_payload(operation: str, payload: object) -> dict[str, object]:
    if operation not in _OPERATION_BY_NAME:
        _fail("unsupported creator operation", reason="unknown_operation", operation=operation)
    if not isinstance(payload, dict):
        _fail("creator payload must be an object", reason="malformed")

    spec = _OPERATION_BY_NAME[operation]
    expected = {field.name for field in spec.fields}
    required = {field.name for field in spec.fields if field.required}
    actual = set(payload)
    missing = sorted(required - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        _fail(
            "creator payload field set does not match operation contract",
            reason="field_set",
            operation=operation,
            missing=missing,
            unknown=unknown,
        )

    normalized: dict[str, object] = {}
    for field_spec in spec.fields:
        value = payload[field_spec.name]
        if field_spec.kind == "object":
            if not isinstance(value, dict):
                _fail(
                    f"{field_spec.name} must be an object",
                    reason="field_type",
                    field=field_spec.name,
                )
            normalized[field_spec.name] = _bounded_json(value, field=field_spec.name)
        elif field_spec.kind == "identifier":
            normalized[field_spec.name] = _identifier(value, field=field_spec.name)
        elif field_spec.kind == "identifier_list":
            normalized[field_spec.name] = list(
                _identifier_list(value, field=field_spec.name)
            )
        elif field_spec.kind == "token":
            normalized[field_spec.name] = _token(
                value,
                field=field_spec.name,
            )
        elif field_spec.kind == "non_negative_integer":
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
                or value > 2**63 - 1
            ):
                _fail(
                    f"{field_spec.name} must be a non-negative integer",
                    reason="field_type",
                    field=field_spec.name,
                )
            normalized[field_spec.name] = value
        elif field_spec.kind == "enum":
            if not isinstance(value, str) or value not in field_spec.enum:
                _fail(
                    f"{field_spec.name} has unsupported value",
                    reason="field_type",
                    field=field_spec.name,
                    allowed=list(field_spec.enum),
                )
            normalized[field_spec.name] = value
        else:
            _fail(
                "operation specification contains unsupported field kind",
                reason="contract",
                kind=field_spec.kind,
            )
    return normalized


def _command_payload(
    *,
    operation: str,
    project_id: str,
    payload: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema": COMMAND_SCHEMA,
        "schema_version": COMMAND_VERSION,
        "operation": operation,
        "project_id": project_id,
        "payload": dict(payload),
    }


def build_creator_command(
    operation: str,
    *,
    project_id: str,
    payload: Mapping[str, object],
) -> CreatorCommand:
    """Build one canonical typed creator command."""

    if not isinstance(operation, str) or operation not in OPERATIONS:
        _fail("unsupported creator operation", reason="unknown_operation", operation=operation)
    canonical_project = _project_id(project_id)
    if not isinstance(payload, Mapping):
        _fail("creator payload must be an object", reason="malformed")
    normalized_payload = _validate_payload(operation, dict(payload))
    command_payload = _command_payload(
        operation=operation,
        project_id=canonical_project,
        payload=normalized_payload,
    )
    encoded = _canonical_json_bytes(command_payload)
    if len(encoded) > MAX_COMMAND_BYTES:
        _fail("creator command exceeds serialized byte bound", reason="bound")
    return CreatorCommand(
        operation=operation,
        project_id=canonical_project,
        payload=normalized_payload,
        digest=hashlib.sha256(encoded).hexdigest(),
    )


def validate_creator_command(command: CreatorCommand) -> None:
    """Recompute a command's typed payload and content identity."""

    if not isinstance(command, CreatorCommand):
        _fail("command must be CreatorCommand", reason="malformed")
    rebuilt = build_creator_command(
        command.operation,
        project_id=command.project_id,
        payload=command.payload,
    )
    if rebuilt != command:
        _fail("creator command derived identity mismatch", reason="digest_mismatch")


def serialize_creator_command(command: CreatorCommand) -> str:
    validate_creator_command(command)
    return _canonical_json_bytes(command.to_dict()).decode("ascii")


def command_from_api(value: Mapping[str, object] | str | bytes) -> CreatorCommand:
    """Compile an API request into the exact canonical command type."""

    if isinstance(value, (str, bytes)):
        root = _load_json_object(value, label="API creator command")
    elif isinstance(value, Mapping):
        root = dict(value)
    else:
        _fail("API creator command must be an object", reason="malformed")

    expected = {"schema", "schema_version", "operation", "project_id", "payload"}
    if set(root) != expected:
        _fail(
            "API creator command has invalid field set",
            reason="field_set",
            missing=sorted(expected - set(root)),
            unknown=sorted(set(root) - expected),
        )
    if root["schema"] != COMMAND_SCHEMA:
        _fail("unsupported creator command schema", reason="schema")
    version = root["schema_version"]
    if isinstance(version, bool) or version != COMMAND_VERSION:
        _fail("unsupported creator command version", reason="version")
    operation = root["operation"]
    project_id = root["project_id"]
    payload = root["payload"]
    if not isinstance(operation, str):
        _fail("creator operation must be text", reason="field_type", field="operation")
    if not isinstance(project_id, str):
        _fail("project_id must be text", reason="field_type", field="project_id")
    if not isinstance(payload, Mapping):
        _fail("payload must be an object", reason="field_type", field="payload")
    return build_creator_command(
        operation,
        project_id=project_id,
        payload=dict(payload),
    )


def command_from_cli(argv: Sequence[str]) -> CreatorCommand:
    """Compile operation/project/payload JSON from CLI tokens."""

    if isinstance(argv, (str, bytes, bytearray)):
        _fail("CLI creator arguments must be a sequence", reason="malformed")
    values = list(argv)
    if len(values) != 3:
        _fail(
            "creator CLI requires exactly: <operation> <project_id> <payload-json>",
            reason="cli_arity",
            received=len(values),
        )
    if not all(isinstance(value, str) for value in values):
        _fail("creator CLI arguments must be text", reason="malformed")
    operation, project_id, raw_payload = values
    payload = _load_json_object(raw_payload, label="CLI creator payload")
    return build_creator_command(operation, project_id=project_id, payload=payload)


def command_from_ui(
    *,
    operation: str,
    project_id: str,
    payload: Mapping[str, object],
) -> CreatorCommand:
    """Compile a UI submission through the same canonical validator."""

    return build_creator_command(operation, project_id=project_id, payload=payload)


def operation_specs() -> tuple[OperationSpec, ...]:
    """Return the immutable operation catalog in canonical order."""

    return _OPERATION_SPECS


def operation_spec(operation: str) -> OperationSpec:
    try:
        return _OPERATION_BY_NAME[operation]
    except (KeyError, TypeError):
        _fail("unsupported creator operation", reason="unknown_operation", operation=operation)


def _surface_payload(surface: str) -> dict[str, object]:
    return {
        "schema": SURFACE_SCHEMA,
        "schema_version": SURFACE_VERSION,
        "surface": surface,
        "operations": [spec.to_dict() for spec in _OPERATION_SPECS],
    }


def surface_manifest(surface: str) -> SurfaceManifest:
    """Return the exact typed operation catalog exposed by one surface."""

    if not isinstance(surface, str) or surface not in SURFACES:
        _fail("unsupported creator surface", reason="unknown_surface", surface=surface)
    payload = _surface_payload(surface)
    return SurfaceManifest(
        surface=surface,
        operations=_OPERATION_SPECS,
        digest=_digest(payload),
    )


def all_surface_manifests() -> tuple[SurfaceManifest, ...]:
    return tuple(surface_manifest(surface) for surface in SURFACES)


def verify_surface_parity(
    manifests: Iterable[SurfaceManifest] | None = None,
) -> str:
    """Fail closed unless CLI/API/UI expose one identical operation contract."""

    selected = tuple(manifests) if manifests is not None else all_surface_manifests()
    if len(selected) != len(SURFACES):
        _fail(
            "surface parity requires exactly CLI, API and UI manifests",
            reason="surface_parity",
        )
    by_surface: dict[str, SurfaceManifest] = {}
    for manifest in selected:
        if not isinstance(manifest, SurfaceManifest):
            _fail("surface manifest has invalid type", reason="surface_parity")
        if manifest.surface in by_surface:
            _fail(
                "duplicate surface manifest",
                reason="surface_parity",
                surface=manifest.surface,
            )
        expected = surface_manifest(manifest.surface)
        if manifest != expected:
            _fail(
                "surface manifest derived identity mismatch",
                reason="digest_mismatch",
                surface=manifest.surface,
            )
        by_surface[manifest.surface] = manifest
    if set(by_surface) != set(SURFACES):
        _fail(
            "surface manifest set is incomplete",
            reason="surface_parity",
            surfaces=sorted(by_surface),
        )
    catalogs = {
        _canonical_json_bytes([spec.to_dict() for spec in manifest.operations])
        for manifest in by_surface.values()
    }
    if len(catalogs) != 1:
        _fail(
            "creator surfaces expose different operation catalogs",
            reason="surface_parity",
        )
    return hashlib.sha256(next(iter(catalogs))).hexdigest()


def dispatch_creator_command(
    command: CreatorCommand,
    *,
    handlers: Mapping[str, Callable[[CreatorCommand], Mapping[str, object]]],
) -> CreatorCommandReceipt:
    """Dispatch through an explicit caller-owned handler map."""

    validate_creator_command(command)
    if not isinstance(handlers, Mapping):
        _fail("handlers must be a mapping", reason="handler")
    unknown_handlers = sorted(set(handlers) - set(OPERATIONS))
    if unknown_handlers:
        _fail(
            "handler map contains unsupported operations",
            reason="handler",
            unknown=unknown_handlers,
        )
    handler = handlers.get(command.operation)
    if handler is None or not callable(handler):
        _fail(
            "no explicit handler is available for creator operation",
            reason="handler_unavailable",
            operation=command.operation,
        )
    output = handler(command)
    if not isinstance(output, Mapping):
        _fail("creator handler result must be an object", reason="handler_result")
    normalized = _bounded_json(dict(output), field="handler_output")
    if not isinstance(normalized, dict):
        _fail("creator handler result must be an object", reason="handler_result")
    receipt_payload = {
        "schema": COMMAND_SCHEMA,
        "schema_version": COMMAND_VERSION,
        "command_digest": command.digest,
        "operation": command.operation,
        "status": "completed",
        "output": normalized,
    }
    encoded = _canonical_json_bytes(receipt_payload)
    if len(encoded) > MAX_RESULT_BYTES:
        _fail("creator handler result exceeds serialized byte bound", reason="bound")
    return CreatorCommandReceipt(
        command_digest=command.digest,
        operation=command.operation,
        status="completed",
        output=normalized,
        digest=hashlib.sha256(encoded).hexdigest(),
    )


def validate_creator_receipt(
    receipt: CreatorCommandReceipt,
    command: CreatorCommand,
) -> None:
    if not isinstance(receipt, CreatorCommandReceipt):
        _fail("receipt must be CreatorCommandReceipt", reason="malformed")
    validate_creator_command(command)
    if receipt.command_digest != command.digest or receipt.operation != command.operation:
        _fail("creator receipt is bound to another command", reason="command_mismatch")
    if receipt.status != "completed":
        _fail("unsupported creator receipt status", reason="receipt_status")
    normalized = _bounded_json(dict(receipt.output), field="handler_output")
    if not isinstance(normalized, dict):
        _fail("creator receipt output must be an object", reason="handler_result")
    payload = {
        "schema": COMMAND_SCHEMA,
        "schema_version": COMMAND_VERSION,
        "command_digest": command.digest,
        "operation": command.operation,
        "status": "completed",
        "output": normalized,
    }
    if receipt.digest != _digest(payload):
        _fail("creator receipt digest mismatch", reason="digest_mismatch")


def creator_cli_payload(argv: Sequence[str]) -> dict[str, object]:
    """Convenience adapter used by python -m skeleton creator."""

    return command_from_cli(argv).to_dict()


__all__ = [
    "COMMAND_SCHEMA",
    "COMMAND_VERSION",
    "CreatorCommand",
    "CreatorCommandError",
    "CreatorCommandReceipt",
    "FieldSpec",
    "MAX_COMMAND_BYTES",
    "MAX_JSON_DEPTH",
    "MAX_JSON_NODES",
    "MAX_LIST_ITEMS",
    "MAX_OBJECT_FIELDS",
    "MAX_RESULT_BYTES",
    "OPERATIONS",
    "OperationSpec",
    "SURFACES",
    "SURFACE_SCHEMA",
    "SURFACE_VERSION",
    "SurfaceManifest",
    "all_surface_manifests",
    "build_creator_command",
    "command_from_api",
    "command_from_cli",
    "command_from_ui",
    "creator_cli_payload",
    "dispatch_creator_command",
    "operation_spec",
    "operation_specs",
    "serialize_creator_command",
    "surface_manifest",
    "validate_creator_command",
    "validate_creator_receipt",
    "verify_surface_parity",
]
