"""Owner-bound Jeeves action routing across the assembled application.

Tool discovery and execution have separate authorities:
 * canonical machine registry declares the feature and its owner;
 * the host explicitly binds that declared feature to an existing ToolSpec;
 * live readiness is proven by a host callback, never guessed from code/files;
 * a per-invocation host authorization callback approves the exact intent;
 * the existing ToolExecutor enforces the expiring, argument-bound grant.

No tool is created from an arbitrary filename, prompt, URL or feature label.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping, Sequence

from skeleton.jeeves.agent.tools import (
    ToolExecutionContext, ToolExecutor, ToolGrant, ToolRegistry,
)
from skeleton.jeeves.agent.types import RiskTier, ToolCall, ToolObservation, stable_fingerprint


class AppDispatchError(ValueError):
    """Capability execution lacks declared owner, readiness or authorization."""


MAX_FEATURES = 10_000
MAX_BINDINGS = 2048
MAX_JSON = 64 * 1024


def _digest(value: Any) -> str:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AppDispatchError("app action must be canonical JSON") from exc
    if len(encoded) > MAX_JSON:
        raise AppDispatchError("capability action payload exceeds byte budget")
    return sha256(encoded).hexdigest()


def _identifier(value: Any, name: str, *, maximum: int = 192) -> str:
    if (not isinstance(value, str) or not value or value.strip() != value
            or len(value) > maximum or any(ord(x) < 33 for x in value)):
        raise AppDispatchError(f"{name} must be bounded canonical identifier")
    return value


def _sha(value: Any, name: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(x not in "0123456789abcdef" for x in value)):
        raise AppDispatchError(f"{name} must be SHA-256")
    return value


@dataclass(frozen=True, slots=True)
class HostCapabilityBinding:
    capability_id: str
    owner_plane: str
    tool_name: str
    allowed_risk: RiskTier
    binding_version: str

    def __post_init__(self) -> None:
        for field in ("capability_id", "owner_plane", "tool_name", "binding_version"):
            _identifier(getattr(self, field), field)
        if not isinstance(self.allowed_risk, RiskTier):
            raise AppDispatchError("binding risk tier must be exact")

    @property
    def digest(self) -> str:
        return _digest({
            "capability_id": self.capability_id,
            "owner_plane": self.owner_plane,
            "tool_name": self.tool_name,
            "risk": self.allowed_risk.value,
            "binding_version": self.binding_version,
        })


@dataclass(frozen=True, slots=True)
class ReadinessReceipt:
    capability_id: str
    owner_plane: str
    proof_digest: str
    healthy: bool
    valid_until_ns: int

    def __post_init__(self) -> None:
        _identifier(self.capability_id, "capability_id")
        _identifier(self.owner_plane, "owner_plane")
        _sha(self.proof_digest, "proof_digest")
        if type(self.healthy) is not bool:
            raise AppDispatchError("readiness receipt healthy must be boolean")
        if type(self.valid_until_ns) is not int or self.valid_until_ns < 0:
            raise AppDispatchError("invalid readiness expiration")

    @property
    def digest(self) -> str:
        return _digest({
            "capability_id": self.capability_id,
            "owner_plane": self.owner_plane,
            "proof_digest": self.proof_digest,
            "healthy": self.healthy,
            "valid_until_ns": self.valid_until_ns,
        })


@dataclass(frozen=True, slots=True)
class CapabilityIntent:
    capability_id: str
    owner_plane: str
    tool_name: str
    binding_digest: str
    readiness_digest: str
    user_id: str
    project_id: str
    run_id: str
    arguments: Mapping[str, Any]
    arguments_digest: str

    def __post_init__(self) -> None:
        for field in ("capability_id", "owner_plane", "tool_name",
                      "user_id", "project_id", "run_id"):
            _identifier(getattr(self, field), field)
        _sha(self.binding_digest, "binding_digest")
        _sha(self.readiness_digest, "readiness_digest")
        _sha(self.arguments_digest, "arguments_digest")
        if not isinstance(self.arguments, Mapping):
            raise AppDispatchError("capability arguments must be a mapping")
        if stable_fingerprint(dict(self.arguments)) != self.arguments_digest:
            raise AppDispatchError("capability intent argument identity mismatch")

    @property
    def digest(self) -> str:
        return _digest({
            "capability_id": self.capability_id,
            "owner_plane": self.owner_plane, "tool_name": self.tool_name,
            "binding_digest": self.binding_digest,
            "readiness_digest": self.readiness_digest,
            "user_id": self.user_id, "project_id": self.project_id,
            "run_id": self.run_id, "arguments_digest": self.arguments_digest,
        })


# Host-specific functions operate outside this module's model-facing surface.
ReadinessAuthority = Callable[[str, str, ToolExecutionContext], ReadinessReceipt]
AuthorizationAuthority = Callable[[CapabilityIntent, ToolExecutionContext], bool]


class JeevesCapabilityDispatcher:
    """Prepare exact target-plane intents and execute only already-granted tools."""

    def __init__(
        self, *,
        registry: ToolRegistry,
        executor: ToolExecutor,
        bindings: Sequence[HostCapabilityBinding],
        readiness: ReadinessAuthority,
        authorize: AuthorizationAuthority,
        root: Path | str | None = None,
    ) -> None:
        if not isinstance(registry, ToolRegistry) or not isinstance(executor, ToolExecutor):
            raise AppDispatchError("caller must inject the host tool registry and executor")
        if not callable(readiness) or not callable(authorize):
            raise AppDispatchError("independent host readiness and authorization required")
        if not isinstance(bindings, (list, tuple)) or len(bindings) > MAX_BINDINGS:
            raise AppDispatchError("binding table exceeds capacity")
        from skeleton.jeeves.app_capability_bridge import _manifest, _root
        home = _root(root)
        raw = _manifest(home / "machine" / "ai_capabilities.json").get("capabilities")
        if not isinstance(raw, list) or len(raw) > MAX_FEATURES:
            raise AppDispatchError("canonical AI feature list is unavailable")
        declared: dict[str, dict[str, Any]] = {}
        for item in raw:
            if not isinstance(item, dict):
                raise AppDispatchError("canonical feature descriptor is invalid")
            name = _identifier(item.get("capability_id"), "capability_id")
            if name in declared:
                raise AppDispatchError("canonical features include duplicate IDs")
            declared[name] = item
        configured: dict[str, HostCapabilityBinding] = {}
        for binding in bindings:
            if not isinstance(binding, HostCapabilityBinding):
                raise AppDispatchError("binding must be typed")
            feature = declared.get(binding.capability_id)
            if feature is None:
                raise AppDispatchError("host bound an undeclared AI capability")
            if feature.get("owner_plane") != binding.owner_plane:
                raise AppDispatchError("host binding would transfer feature ownership")
            if feature.get("enabled") is not True:
                raise AppDispatchError("disabled feature cannot be tool-bound")
            if binding.capability_id in configured:
                raise AppDispatchError("duplicate host binding")
            spec = registry.get(binding.tool_name)
            if spec is None or spec.spec.risk is not binding.allowed_risk:
                raise AppDispatchError("host binding must resolve exact registered risk")
            configured[binding.capability_id] = binding
        self._bindings = configured
        self._registry = registry
        self._executor = executor
        self._readiness = readiness
        self._authorize = authorize
        self._lock = RLock()

    def catalog(self) -> tuple[dict[str, str], ...]:
        return tuple({
            "capability_id": item.capability_id,
            "owner_plane": item.owner_plane,
            "tool_name": item.tool_name,
            "risk": item.allowed_risk.value,
            "binding_digest": item.digest,
            "status": "bound_unverified",
        } for item in sorted(self._bindings.values(), key=lambda x: x.capability_id))

    def prepare(
        self, capability_id: str, *,
        context: ToolExecutionContext,
        project_id: str,
        arguments: Mapping[str, Any],
        now_ns: int,
    ) -> CapabilityIntent:
        with self._lock:
            feature_id = _identifier(capability_id, "capability_id")
            binding = self._bindings.get(feature_id)
            if binding is None:
                raise AppDispatchError("AI feature is not bound to a trusted host tool")
            if not isinstance(context, ToolExecutionContext):
                raise AppDispatchError("host execution context is required")
            _identifier(project_id, "project_id")
            if type(now_ns) is not int or now_ns < 0:
                raise AppDispatchError("now_ns must be host-observed nanoseconds")
            spec = self._registry.get(binding.tool_name)
            if spec is None or spec.spec.risk is not binding.allowed_risk:
                raise AppDispatchError("host binding became stale")
            normalized = spec.spec.validate_arguments(arguments)
            receipt = self._readiness(feature_id, binding.owner_plane, context)
            if not isinstance(receipt, ReadinessReceipt):
                raise AppDispatchError("host returned untyped readiness proof")
            if (receipt.capability_id != feature_id
                    or receipt.owner_plane != binding.owner_plane
                    or not receipt.healthy or receipt.valid_until_ns <= now_ns):
                raise AppDispatchError("live owner readiness is absent or expired")
            _digest(normalized)
            return CapabilityIntent(
                capability_id=feature_id, owner_plane=binding.owner_plane,
                tool_name=binding.tool_name, binding_digest=binding.digest,
                readiness_digest=receipt.digest,
                user_id=context.user_id, project_id=project_id,
                run_id=context.run_id, arguments=normalized,
                arguments_digest=stable_fingerprint(normalized),
            )

    def execute(
        self, intent: CapabilityIntent, *,
        context: ToolExecutionContext,
        grant: ToolGrant,
        now_ns: int,
    ) -> ToolObservation:
        """Never manufacture a ToolGrant. The host must pass an exact one-shot grant."""
        with self._lock:
            if not isinstance(intent, CapabilityIntent):
                raise AppDispatchError("typed capability intent required")
            if not isinstance(context, ToolExecutionContext) or not isinstance(grant, ToolGrant):
                raise AppDispatchError("host context and ToolGrant required")
            if type(now_ns) is not int or now_ns < 0:
                raise AppDispatchError("invalid host observed time")
            binding = self._bindings.get(intent.capability_id)
            if binding is None or binding.digest != intent.binding_digest:
                raise AppDispatchError("capability binding changed after planning")
            if (intent.owner_plane != binding.owner_plane
                    or intent.tool_name != binding.tool_name
                    or intent.run_id != context.run_id
                    or intent.user_id != context.user_id):
                raise AppDispatchError("intent crosses user, run or owner boundary")
            receipt = self._readiness(intent.capability_id, intent.owner_plane, context)
            if (not isinstance(receipt, ReadinessReceipt)
                    or receipt.digest != intent.readiness_digest
                    or not receipt.healthy or receipt.valid_until_ns <= now_ns):
                raise AppDispatchError("readiness expired or changed since planning")
            if (grant.tool_name != intent.tool_name
                    or binding.allowed_risk not in grant.allowed_risks
                    or grant.argument_fingerprint != intent.arguments_digest
                    or grant.max_calls != 1 or grant.expires_at is None):
                raise AppDispatchError("capability requires exact expiring one-shot grant")
            if self._authorize(intent, context) is not True:
                raise AppDispatchError("host rejected exact capability intent")
            call = ToolCall(
                call_id="capability-" + intent.digest[:32],
                name=intent.tool_name,
                arguments=dict(intent.arguments),
                reason="host-authorized exact app capability action",
            )
            return self._executor.execute(call, context, grants=(grant,))


__all__ = [
    "AppDispatchError", "HostCapabilityBinding", "ReadinessReceipt",
    "CapabilityIntent", "JeevesCapabilityDispatcher",
]
