"""Tool, connector, plugin and marketplace-security contracts for P3 deferred work.

This module materializes VOL-160 through VOL-163 with explicit separation
between declaration, admission/authorization and execution.  The reference
implementations are intentionally bounded and dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import math
import time
import threading
from typing import Any, Callable, Mapping, Protocol, Sequence


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_nonempty(value: str, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


def _require_digest(value: str, *, field_name: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{field_name} must be lowercase sha256")
    return text


def _json_schema_object(schema: Mapping[str, Any], *, field_name: str) -> dict[str, Any]:
    copied = dict(schema)
    _canonical(copied)
    if copied.get("type") not in {None, "object"}:
        raise ValueError(f"{field_name} must describe an object schema")
    return copied


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    version: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    authority_scope: frozenset[str]
    side_effect_class: str
    idempotency: str
    timeout_seconds: float
    description: str = ""

    def __post_init__(self) -> None:
        for name in ("name", "version", "side_effect_class", "idempotency"):
            object.__setattr__(self, name, _require_nonempty(getattr(self, name), field_name=name))
        object.__setattr__(self, "input_schema", _json_schema_object(self.input_schema, field_name="input_schema"))
        object.__setattr__(self, "output_schema", _json_schema_object(self.output_schema, field_name="output_schema"))
        if not self.authority_scope:
            raise ValueError("tool authority_scope must be explicit and non-empty")
        if self.side_effect_class not in {"none", "read", "write", "external"}:
            raise ValueError("unsupported side_effect_class")
        if self.idempotency not in {"idempotent", "conditional", "non_idempotent"}:
            raise ValueError("unsupported idempotency class")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "authority_scope": sorted(self.authority_scope),
            "side_effect_class": self.side_effect_class,
            "idempotency": self.idempotency,
            "timeout_seconds": self.timeout_seconds,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    invocation_id: str
    tool_digest: str
    arguments: Mapping[str, Any]
    requested_scope: frozenset[str]
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "invocation_id", _require_nonempty(self.invocation_id, field_name="invocation_id"))
        object.__setattr__(self, "tool_digest", _require_digest(self.tool_digest, field_name="tool_digest"))
        args = dict(self.arguments)
        _canonical(args)
        object.__setattr__(self, "arguments", args)
        scope = frozenset(_require_nonempty(item, field_name="requested_scope item") for item in self.requested_scope)
        if not scope:
            raise ValueError("requested_scope must be explicit")
        object.__setattr__(self, "requested_scope", scope)
        if self.idempotency_key is not None:
            object.__setattr__(
                self,
                "idempotency_key",
                _require_nonempty(self.idempotency_key, field_name="idempotency_key"),
            )

    @property
    def semantic_digest(self) -> str:
        """Identity of the intended effect, excluding transport invocation identity."""

        return _digest(
            {
                "tool_digest": self.tool_digest,
                "arguments": dict(self.arguments),
                "requested_scope": sorted(self.requested_scope),
            }
        )


@dataclass(frozen=True, slots=True)
class ToolResult:
    invocation_id: str
    tool_digest: str
    status: str
    output: Mapping[str, Any]
    started_at: float
    finished_at: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "invocation_id", _require_nonempty(self.invocation_id, field_name="invocation_id"))
        object.__setattr__(self, "tool_digest", _require_digest(self.tool_digest, field_name="tool_digest"))
        object.__setattr__(self, "status", _require_nonempty(self.status, field_name="status"))
        copied = dict(self.output)
        _canonical(copied)
        object.__setattr__(self, "output", copied)
        if not all(math.isfinite(v) for v in (self.started_at, self.finished_at)):
            raise ValueError("tool timestamps must be finite")
        if self.finished_at < self.started_at:
            raise ValueError("finished_at cannot precede started_at")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "invocation_id": self.invocation_id,
                "tool_digest": self.tool_digest,
                "status": self.status,
                "output": dict(self.output),
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }
        )


class ToolExecutor(Protocol):
    def __call__(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ToolRegistry:
    """Registry that cannot authorize itself and fail-closes duplicate side effects.

    Idempotency keys are bound to the semantic invocation (tool, arguments and
    requested authority scope). Replays are re-authorized but never execute the
    underlying tool twice. The in-memory reference ledger is deliberately
    bounded; capacity exhaustion rejects new keyed effects instead of evicting
    old receipts and reopening a duplicate-side-effect window.
    """

    def __init__(self, *, max_idempotency_records: int = 4096) -> None:
        if (
            isinstance(max_idempotency_records, bool)
            or not isinstance(max_idempotency_records, int)
            or max_idempotency_records <= 0
        ):
            raise ValueError("max_idempotency_records must be a positive integer")
        self._definitions: dict[str, ToolDefinition] = {}
        self._executors: dict[str, ToolExecutor] = {}
        self._max_idempotency_records = max_idempotency_records
        self._idempotency_lock = threading.RLock()
        self._idempotency: dict[tuple[str, str], tuple[str, ToolResult | None]] = {}

    def register(self, definition: ToolDefinition, executor: ToolExecutor) -> str:
        if definition.digest in self._definitions:
            raise ValueError("tool definition already registered")
        self._definitions[definition.digest] = definition
        self._executors[definition.digest] = executor
        return definition.digest

    def definition(self, digest: str) -> ToolDefinition:
        return self._definitions[_require_digest(digest, field_name="tool_digest")]

    def invoke(
        self,
        invocation: ToolInvocation,
        *,
        authorize: Callable[[ToolDefinition, ToolInvocation], bool],
        now: Callable[[], float] = time.monotonic,
    ) -> ToolResult:
        definition = self.definition(invocation.tool_digest)
        if not invocation.requested_scope.issubset(definition.authority_scope):
            raise PermissionError("invocation requests scope outside tool declaration")
        if definition.idempotency == "non_idempotent" and not invocation.idempotency_key:
            raise ValueError("non-idempotent tool invocation requires idempotency_key")

        replay_key: tuple[str, str] | None = None
        if invocation.idempotency_key is not None:
            replay_key = (invocation.tool_digest, invocation.idempotency_key)
            with self._idempotency_lock:
                prior = self._idempotency.get(replay_key)
                if prior is not None and prior[0] != invocation.semantic_digest:
                    raise ValueError("idempotency_key is already bound to a different semantic invocation")
                if prior is None and len(self._idempotency) >= self._max_idempotency_records:
                    raise BufferError("idempotency ledger capacity exhausted")

        # Authorization is intentionally checked on every replay so an old
        # receipt cannot bypass newly revoked or narrowed authority.
        if not authorize(definition, invocation):
            raise PermissionError("tool invocation denied by external authority")

        if replay_key is not None:
            # Claim the effect before execution. If execution later raises or
            # times out after starting, the None receipt deliberately remains:
            # a retry is fenced because the external side effect is unknown.
            with self._idempotency_lock:
                prior = self._idempotency.get(replay_key)
                if prior is not None:
                    if prior[0] != invocation.semantic_digest:
                        raise ValueError("idempotency_key is already bound to a different semantic invocation")
                    if prior[1] is None:
                        raise RuntimeError(
                            "idempotency_key has an in-flight or indeterminate prior effect"
                        )
                    return prior[1]
                if len(self._idempotency) >= self._max_idempotency_records:
                    raise BufferError("idempotency ledger capacity exhausted")
                self._idempotency[replay_key] = (invocation.semantic_digest, None)

        started = now()
        output = dict(self._executors[invocation.tool_digest](invocation.arguments))
        finished = now()
        if finished - started > definition.timeout_seconds:
            # Do not clear a keyed claim here. The executor already ran, so its
            # external effect cannot safely be assumed absent.
            raise TimeoutError("tool execution exceeded declared timeout")
        result = ToolResult(
            invocation_id=invocation.invocation_id,
            tool_digest=invocation.tool_digest,
            status="succeeded",
            output=output,
            started_at=started,
            finished_at=finished,
        )
        if replay_key is not None:
            with self._idempotency_lock:
                self._idempotency[replay_key] = (invocation.semantic_digest, result)
        return result

    @property
    def idempotency_record_count(self) -> int:
        return len(self._idempotency)


@dataclass(frozen=True, slots=True)
class ConnectorDefinition:
    connector_id: str
    version: str
    read_scopes: frozenset[str]
    write_scopes: frozenset[str]
    page_size_limit: int
    requests_per_minute: int
    error_semantics: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "connector_id", _require_nonempty(self.connector_id, field_name="connector_id"))
        object.__setattr__(self, "version", _require_nonempty(self.version, field_name="version"))
        if self.page_size_limit <= 0 or self.requests_per_minute <= 0:
            raise ValueError("connector bounds must be positive")
        errors = {str(k): str(v) for k, v in dict(self.error_semantics).items()}
        if not errors:
            raise ValueError("connector error semantics must be explicit")
        object.__setattr__(self, "error_semantics", errors)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "connector_id": self.connector_id,
                "version": self.version,
                "read_scopes": sorted(self.read_scopes),
                "write_scopes": sorted(self.write_scopes),
                "page_size_limit": self.page_size_limit,
                "requests_per_minute": self.requests_per_minute,
                "error_semantics": dict(self.error_semantics),
            }
        )


@dataclass(frozen=True, slots=True)
class ConnectorSession:
    session_id: str
    connector_digest: str
    credential_handle: str
    granted_read_scopes: frozenset[str]
    granted_write_scopes: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _require_nonempty(self.session_id, field_name="session_id"))
        object.__setattr__(self, "connector_digest", _require_digest(self.connector_digest, field_name="connector_digest"))
        object.__setattr__(self, "credential_handle", _require_nonempty(self.credential_handle, field_name="credential_handle"))
        if any(marker in self.credential_handle.lower() for marker in ("bearer ", "token=", "password=", "secret=")):
            raise ValueError("credential_handle must be an opaque handle, not credential material")


@dataclass(frozen=True, slots=True)
class ConnectorResult:
    session_id: str
    operation: str
    records: tuple[Mapping[str, Any], ...]
    next_cursor: str | None
    rate_limit_remaining: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _require_nonempty(self.session_id, field_name="session_id"))
        object.__setattr__(self, "operation", _require_nonempty(self.operation, field_name="operation"))
        normalized = tuple(dict(item) for item in self.records)
        _canonical(normalized)
        object.__setattr__(self, "records", normalized)
        if self.rate_limit_remaining < 0:
            raise ValueError("rate_limit_remaining must be non-negative")


class ConnectorRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ConnectorDefinition] = {}

    def register(self, definition: ConnectorDefinition) -> str:
        self._definitions[definition.digest] = definition
        return definition.digest

    def open_session(
        self,
        connector_digest: str,
        *,
        session_id: str,
        credential_handle: str,
        read_scopes: Sequence[str] = (),
        write_scopes: Sequence[str] = (),
    ) -> ConnectorSession:
        digest = _require_digest(connector_digest, field_name="connector_digest")
        definition = self._definitions[digest]
        reads = frozenset(read_scopes)
        writes = frozenset(write_scopes)
        if not reads.issubset(definition.read_scopes) or not writes.issubset(definition.write_scopes):
            raise PermissionError("connector session scope exceeds connector declaration")
        return ConnectorSession(
            session_id=session_id,
            connector_digest=digest,
            credential_handle=credential_handle,
            granted_read_scopes=reads,
            granted_write_scopes=writes,
        )


@dataclass(frozen=True, slots=True)
class PluginManifest:
    plugin_id: str
    version: str
    entrypoint: str
    capabilities: frozenset[str]
    permissions: frozenset[str]
    compatible_api_versions: frozenset[str]
    package_digest: str

    def __post_init__(self) -> None:
        for name in ("plugin_id", "version", "entrypoint"):
            object.__setattr__(self, name, _require_nonempty(getattr(self, name), field_name=name))
        object.__setattr__(self, "package_digest", _require_digest(self.package_digest, field_name="package_digest"))
        if not self.capabilities or not self.permissions or not self.compatible_api_versions:
            raise ValueError("plugins must declare capabilities, permissions and compatibility")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "plugin_id": self.plugin_id,
                "version": self.version,
                "entrypoint": self.entrypoint,
                "capabilities": sorted(self.capabilities),
                "permissions": sorted(self.permissions),
                "compatible_api_versions": sorted(self.compatible_api_versions),
                "package_digest": self.package_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class PluginGrant:
    plugin_digest: str
    granted_permissions: frozenset[str]
    issued_by: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "plugin_digest", _require_digest(self.plugin_digest, field_name="plugin_digest"))
        object.__setattr__(self, "issued_by", _require_nonempty(self.issued_by, field_name="issued_by"))
        if not self.granted_permissions:
            raise ValueError("plugin grant must be explicit")


@dataclass(frozen=True, slots=True)
class PluginLifecycle:
    plugin_digest: str
    state: str
    generation: int
    residue_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "plugin_digest", _require_digest(self.plugin_digest, field_name="plugin_digest"))
        if self.state not in {"installed", "enabled", "disabled", "removed"}:
            raise ValueError("unsupported plugin lifecycle state")
        if self.generation < 0:
            raise ValueError("plugin generation must be non-negative")
        if self.state == "removed" and self.residue_keys:
            raise ValueError("removed plugin cannot retain core-state residue")


class PluginRegistry:
    def __init__(self, *, api_version: str) -> None:
        self.api_version = _require_nonempty(api_version, field_name="api_version")
        self._manifests: dict[str, PluginManifest] = {}
        self._states: dict[str, PluginLifecycle] = {}
        self._versions: dict[tuple[str, str], str] = {}

    def install(self, manifest: PluginManifest) -> PluginLifecycle:
        if self.api_version not in manifest.compatible_api_versions:
            raise ValueError("plugin is incompatible with runtime API")
        version_key = (manifest.plugin_id, manifest.version)
        bound_digest = self._versions.get(version_key)
        if bound_digest is not None and bound_digest != manifest.digest:
            raise ValueError("plugin id/version is already bound to different immutable content")
        if manifest.digest in self._states:
            # Re-installing the identical immutable manifest is idempotent and
            # must never reset enabled/disabled/removed lifecycle state.
            return self._states[manifest.digest]
        self._versions[version_key] = manifest.digest
        self._manifests[manifest.digest] = manifest
        state = PluginLifecycle(manifest.digest, "installed", 0)
        self._states[manifest.digest] = state
        return state

    def enable(self, grant: PluginGrant) -> PluginLifecycle:
        manifest = self._manifests[grant.plugin_digest]
        if not grant.granted_permissions.issubset(manifest.permissions):
            raise PermissionError("plugin grant exceeds manifest permissions")
        previous = self._states[grant.plugin_digest]
        if previous.state not in {"installed", "disabled"}:
            raise ValueError("plugin cannot be enabled from current state")
        state = PluginLifecycle(grant.plugin_digest, "enabled", previous.generation + 1)
        self._states[grant.plugin_digest] = state
        return state

    def disable(self, plugin_digest: str) -> PluginLifecycle:
        digest = _require_digest(plugin_digest, field_name="plugin_digest")
        previous = self._states[digest]
        if previous.state != "enabled":
            raise ValueError("only enabled plugins can be disabled")
        state = PluginLifecycle(digest, "disabled", previous.generation + 1)
        self._states[digest] = state
        return state

    def remove(self, plugin_digest: str, *, residue_keys: Sequence[str] = ()) -> PluginLifecycle:
        digest = _require_digest(plugin_digest, field_name="plugin_digest")
        previous = self._states[digest]
        if previous.state == "enabled":
            raise ValueError("disable plugin before removal")
        state = PluginLifecycle(digest, "removed", previous.generation + 1, tuple(residue_keys))
        self._states[digest] = state
        return state

    def state(self, plugin_digest: str) -> PluginLifecycle:
        return self._states[_require_digest(plugin_digest, field_name="plugin_digest")]


@dataclass(frozen=True, slots=True)
class MarketplacePackage:
    package_id: str
    version: str
    content_digest: str
    manifest_digest: str
    provenance: Mapping[str, str]
    requested_permissions: frozenset[str]

    def __post_init__(self) -> None:
        for name in ("package_id", "version"):
            object.__setattr__(self, name, _require_nonempty(getattr(self, name), field_name=name))
        for name in ("content_digest", "manifest_digest"):
            object.__setattr__(self, name, _require_digest(getattr(self, name), field_name=name))
        provenance = {str(k): str(v) for k, v in dict(self.provenance).items()}
        if not provenance:
            raise ValueError("package provenance must be present")
        object.__setattr__(self, "provenance", provenance)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "package_id": self.package_id,
                "version": self.version,
                "content_digest": self.content_digest,
                "manifest_digest": self.manifest_digest,
                "provenance": dict(self.provenance),
                "requested_permissions": sorted(self.requested_permissions),
            }
        )


@dataclass(frozen=True, slots=True)
class PackageAttestation:
    package_digest: str
    key_id: str
    issuer: str
    signature_hex: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "package_digest", _require_digest(self.package_digest, field_name="package_digest"))
        object.__setattr__(self, "key_id", _require_nonempty(self.key_id, field_name="key_id"))
        object.__setattr__(self, "issuer", _require_nonempty(self.issuer, field_name="issuer"))
        sig = str(self.signature_hex).strip().lower()
        if len(sig) != 64 or any(ch not in "0123456789abcdef" for ch in sig):
            raise ValueError("signature_hex must be a sha256-sized hexadecimal MAC")
        object.__setattr__(self, "signature_hex", sig)


@dataclass(frozen=True, slots=True)
class RevocationRecord:
    package_digest: str
    reason: str
    revoked_by: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "package_digest", _require_digest(self.package_digest, field_name="package_digest"))
        object.__setattr__(self, "reason", _require_nonempty(self.reason, field_name="reason"))
        object.__setattr__(self, "revoked_by", _require_nonempty(self.revoked_by, field_name="revoked_by"))


class MarketplaceVerifier:
    """Reference trust-tier verifier with quarantine/revocation state.

    HMAC is used only as a deterministic stdlib reference attestation primitive.
    Production deployments may replace it with an asymmetric verifier behind the
    same package/attestation contracts.
    """

    def __init__(self, trusted_keys: Mapping[str, bytes], *, allowed_permissions: Sequence[str]) -> None:
        if not trusted_keys:
            raise ValueError("at least one trusted marketplace key is required")
        self._trusted_keys = {str(k): bytes(v) for k, v in trusted_keys.items()}
        if any(not value for value in self._trusted_keys.values()):
            raise ValueError("trusted marketplace keys cannot be empty")
        self.allowed_permissions = frozenset(allowed_permissions)
        self._quarantine: dict[str, str] = {}
        self._revoked: dict[str, RevocationRecord] = {}

    @staticmethod
    def sign_for_test(package: MarketplacePackage, *, key: bytes) -> str:
        return hmac.new(bytes(key), package.digest.encode("ascii"), hashlib.sha256).hexdigest()

    def verify(self, package: MarketplacePackage, attestation: PackageAttestation) -> bool:
        if package.digest in self._revoked:
            return False
        if attestation.package_digest != package.digest:
            self._quarantine[package.digest] = "attestation identity mismatch"
            return False
        key = self._trusted_keys.get(attestation.key_id)
        if key is None:
            self._quarantine[package.digest] = "untrusted signing key"
            return False
        if not package.requested_permissions.issubset(self.allowed_permissions):
            self._quarantine[package.digest] = "permission request exceeds marketplace policy"
            return False
        expected = hmac.new(key, package.digest.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, attestation.signature_hex):
            self._quarantine[package.digest] = "invalid package attestation"
            return False
        self._quarantine.pop(package.digest, None)
        return True

    def quarantine_reason(self, package_digest: str) -> str | None:
        return self._quarantine.get(_require_digest(package_digest, field_name="package_digest"))

    def revoke(self, package_digest: str, *, reason: str, revoked_by: str) -> RevocationRecord:
        record = RevocationRecord(package_digest, reason, revoked_by)
        self._revoked[record.package_digest] = record
        self._quarantine.pop(record.package_digest, None)
        return record

    def is_revoked(self, package_digest: str) -> bool:
        return _require_digest(package_digest, field_name="package_digest") in self._revoked
