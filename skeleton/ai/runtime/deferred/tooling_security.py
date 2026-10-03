"""Tool, connector and security capabilities for the deferred AI frontier."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
import hashlib
from typing import Any, Callable, Iterable, Mapping

from .contracts import canonical_json, sha256_json


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _unique(values: Iterable[str], name: str) -> tuple[str, ...]:
    result = tuple(_text(item, name) for item in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must be unique")
    return result


@dataclass(frozen=True, slots=True)
class ToolContract:
    tool_id: str
    version: str
    effect: str
    input_schema_digest: str
    required_capabilities: tuple[str, ...] = ()
    network_policy: str = "none"

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_id", _text(self.tool_id, "tool_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        if self.effect not in {"read", "write", "external", "admin"}:
            raise ValueError("unsupported tool effect")
        if (
            not isinstance(self.input_schema_digest, str)
            or len(self.input_schema_digest) != 64
            or any(c not in "0123456789abcdef" for c in self.input_schema_digest)
        ):
            raise ValueError("input_schema_digest must be lowercase sha256")
        object.__setattr__(
            self,
            "required_capabilities",
            _unique(self.required_capabilities, "required_capabilities"),
        )
        if self.network_policy not in {"none", "allowlisted", "unrestricted"}:
            raise ValueError("unsupported network policy")

    @property
    def identity(self) -> str:
        return f"{self.tool_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class ToolGrant:
    principal_id: str
    tool_id: str
    allowed_effects: tuple[str, ...]
    capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "principal_id", _text(self.principal_id, "principal_id"))
        object.__setattr__(self, "tool_id", _text(self.tool_id, "tool_id"))
        effects = _unique(self.allowed_effects, "allowed_effects")
        if any(item not in {"read", "write", "external", "admin"} for item in effects):
            raise ValueError("unsupported granted effect")
        object.__setattr__(self, "allowed_effects", effects)
        object.__setattr__(
            self, "capabilities", _unique(self.capabilities, "capabilities")
        )


class ToolSDK:
    def __init__(self) -> None:
        self._contracts: dict[str, ToolContract] = {}
        self._handlers: dict[str, Callable[[Mapping[str, Any]], Any]] = {}

    def register(
        self,
        contract: ToolContract,
        handler: Callable[[Mapping[str, Any]], Any],
    ) -> None:
        if contract.identity in self._contracts:
            raise ValueError("tool identity already registered")
        if not callable(handler):
            raise TypeError("tool handler must be callable")
        self._contracts[contract.identity] = contract
        self._handlers[contract.identity] = handler

    def authorize(self, identity: str, grant: ToolGrant) -> ToolContract:
        try:
            contract = self._contracts[identity]
        except KeyError as exc:
            raise KeyError("unknown tool identity") from exc
        if contract.tool_id != grant.tool_id:
            raise PermissionError("grant does not target tool")
        if contract.effect not in grant.allowed_effects:
            raise PermissionError("tool effect is not granted")
        missing = set(contract.required_capabilities) - set(grant.capabilities)
        if missing:
            raise PermissionError(
                "missing tool capabilities: " + ",".join(sorted(missing))
            )
        return contract

    def invoke(
        self,
        identity: str,
        grant: ToolGrant,
        arguments: Mapping[str, Any],
    ) -> Any:
        self.authorize(identity, grant)
        if not isinstance(arguments, Mapping):
            raise TypeError("tool arguments must be a mapping")
        return self._handlers[identity](dict(arguments))


@dataclass(frozen=True, slots=True)
class ConnectorContract:
    connector_id: str
    version: str
    scopes: tuple[str, ...]
    tool_identities: tuple[str, ...]
    provider_data_classes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "connector_id", _text(self.connector_id, "connector_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(self, "scopes", _unique(self.scopes, "scopes"))
        object.__setattr__(
            self, "tool_identities", _unique(self.tool_identities, "tool_identities")
        )
        object.__setattr__(
            self,
            "provider_data_classes",
            _unique(self.provider_data_classes, "provider_data_classes"),
        )

    def allows_scope(self, scope: str) -> bool:
        return scope in self.scopes


class TrustTier(IntEnum):
    QUARANTINED = 0
    UNVERIFIED = 1
    VERIFIED = 2
    FIRST_PARTY = 3


@dataclass(frozen=True, slots=True)
class PluginManifest:
    plugin_id: str
    version: str
    trust_tier: TrustTier
    tool_identities: tuple[str, ...]
    requested_capabilities: tuple[str, ...]
    state_schema_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "plugin_id", _text(self.plugin_id, "plugin_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        if not isinstance(self.trust_tier, TrustTier):
            raise TypeError("trust_tier must be TrustTier")
        object.__setattr__(
            self, "tool_identities", _unique(self.tool_identities, "tool_identities")
        )
        object.__setattr__(
            self,
            "requested_capabilities",
            _unique(self.requested_capabilities, "requested_capabilities"),
        )
        if self.state_schema_digest is not None and (
            len(self.state_schema_digest) != 64
            or any(c not in "0123456789abcdef" for c in self.state_schema_digest)
        ):
            raise ValueError("state_schema_digest must be lowercase sha256")

    @property
    def identity(self) -> str:
        return f"{self.plugin_id}@{self.version}"


class PluginRegistry:
    def __init__(self, *, minimum_trust: TrustTier = TrustTier.VERIFIED) -> None:
        self.minimum_trust = minimum_trust
        self._plugins: dict[str, PluginManifest] = {}
        self._revoked: set[str] = set()

    def install(self, manifest: PluginManifest) -> None:
        if manifest.trust_tier < self.minimum_trust:
            raise PermissionError("plugin trust tier is below installation threshold")
        if manifest.identity in self._revoked:
            raise PermissionError("revoked plugin identity cannot be reinstalled")
        prior = self._plugins.get(manifest.plugin_id)
        if prior is not None and prior.version == manifest.version:
            if prior != manifest:
                raise ValueError("plugin identity collision")
            return
        self._plugins[manifest.plugin_id] = manifest

    def revoke(self, plugin_id: str) -> PluginManifest:
        try:
            manifest = self._plugins.pop(plugin_id)
        except KeyError as exc:
            raise KeyError("plugin is not installed") from exc
        self._revoked.add(manifest.identity)
        return manifest

    def get(self, plugin_id: str) -> PluginManifest:
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise KeyError("plugin is not installed") from exc


@dataclass(frozen=True, slots=True)
class PolicyTrace:
    trace_id: str
    subject: str
    action: str
    attributes: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _text(self.trace_id, "trace_id"))
        object.__setattr__(self, "subject", _text(self.subject, "subject"))
        object.__setattr__(self, "action", _text(self.action, "action"))
        if not isinstance(self.attributes, Mapping):
            raise TypeError("attributes must be a mapping")
        normalized = {
            _text(key, "attribute key"): _text(value, "attribute value")
            for key, value in self.attributes.items()
        }
        object.__setattr__(self, "attributes", normalized)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    trace_id: str
    allowed: bool
    reasons: tuple[str, ...]
    evaluator_digest: str

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "trace_id": self.trace_id,
                "allowed": self.allowed,
                "reasons": list(self.reasons),
                "evaluator_digest": self.evaluator_digest,
            }
        )


class PolicySimulator:
    def __init__(
        self,
        evaluator: Callable[[PolicyTrace], tuple[bool, Iterable[str]]],
        *,
        evaluator_id: str,
    ) -> None:
        if not callable(evaluator):
            raise TypeError("evaluator must be callable")
        self._evaluator = evaluator
        self.evaluator_id = _text(evaluator_id, "evaluator_id")
        self.evaluator_digest = hashlib.sha256(
            self.evaluator_id.encode("utf-8")
        ).hexdigest()

    def evaluate(self, trace: PolicyTrace) -> PolicyDecision:
        allowed, reasons = self._evaluator(trace)
        if not isinstance(allowed, bool):
            raise TypeError("policy evaluator must return bool decision")
        normalized = _unique(tuple(reasons), "policy reasons")
        if not normalized:
            normalized = ("explicit_allow" if allowed else "explicit_deny",)
        return PolicyDecision(
            trace_id=trace.trace_id,
            allowed=allowed,
            reasons=normalized,
            evaluator_digest=self.evaluator_digest,
        )

    def compare(
        self,
        traces: Iterable[PolicyTrace],
        runtime_decisions: Mapping[str, bool],
    ) -> tuple[str, ...]:
        drift: list[str] = []
        for trace in traces:
            simulated = self.evaluate(trace)
            runtime = runtime_decisions.get(trace.trace_id)
            if runtime is None or runtime != simulated.allowed:
                drift.append(trace.trace_id)
        return tuple(sorted(drift))


@dataclass(frozen=True, slots=True)
class NetworkPolicy:
    policy_id: str
    allowed_hosts: tuple[str, ...] = ()
    deny_private_ranges: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        hosts = tuple(sorted(_unique(self.allowed_hosts, "allowed_hosts")))
        object.__setattr__(self, "allowed_hosts", hosts)

    def allows(self, host: str) -> bool:
        host = _text(host, "host").lower()
        return host in {item.lower() for item in self.allowed_hosts}


@dataclass(frozen=True, slots=True)
class SecretLease:
    secret_id: str
    version: str
    principal_id: str
    issued_at: int
    expires_at: int

    def __post_init__(self) -> None:
        for name in ("secret_id", "version", "principal_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("issued_at", "expires_at"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.expires_at <= self.issued_at:
            raise ValueError("secret lease must expire after issue")

    def valid_at(self, timestamp: int) -> bool:
        return self.issued_at <= timestamp < self.expires_at


@dataclass(frozen=True, slots=True)
class KeyVersion:
    key_id: str
    version: int
    public_fingerprint: str
    revoked: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_id", _text(self.key_id, "key_id"))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("key version must be a positive integer")
        if (
            not isinstance(self.public_fingerprint, str)
            or len(self.public_fingerprint) != 64
            or any(c not in "0123456789abcdef" for c in self.public_fingerprint)
        ):
            raise ValueError("public_fingerprint must be lowercase sha256")
        if not isinstance(self.revoked, bool):
            raise TypeError("revoked must be boolean")


class KeyRing:
    def __init__(self) -> None:
        self._keys: dict[tuple[str, int], KeyVersion] = {}

    def add(self, key: KeyVersion) -> None:
        identity = (key.key_id, key.version)
        prior = self._keys.get(identity)
        if prior is not None and prior != key:
            raise ValueError("key version collision")
        self._keys[identity] = key

    def active(self, key_id: str) -> KeyVersion:
        candidates = [
            key for (identity, _), key in self._keys.items()
            if identity == key_id and not key.revoked
        ]
        if not candidates:
            raise KeyError("no active key version")
        return max(candidates, key=lambda item: item.version)


class PrivacyClass(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3

    @classmethod
    def parse(cls, value: str) -> "PrivacyClass":
        try:
            return cls[value.strip().upper()]
        except (KeyError, AttributeError) as exc:
            raise ValueError("unknown privacy class") from exc


@dataclass(frozen=True, slots=True)
class PrivacyLabel:
    classification: PrivacyClass
    purposes: tuple[str, ...]
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.classification, PrivacyClass):
            raise TypeError("classification must be PrivacyClass")
        object.__setattr__(self, "purposes", _unique(self.purposes, "purposes"))
        if self.classification >= PrivacyClass.CONFIDENTIAL and not self.tenant_id:
            raise ValueError("confidential/restricted data requires tenant_id")
        if self.tenant_id is not None:
            object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant_id"))

    def can_flow_to(self, target: "PrivacyLabel") -> bool:
        if target.classification < self.classification:
            return False
        if self.tenant_id is not None and target.tenant_id != self.tenant_id:
            return False
        return set(target.purposes).issubset(set(self.purposes))


class DeletionGraph:
    def __init__(self) -> None:
        self._children: dict[str, set[str]] = {}

    def add(self, artifact_id: str, *, derived_from: Iterable[str] = ()) -> None:
        artifact_id = _text(artifact_id, "artifact_id")
        self._children.setdefault(artifact_id, set())
        for parent in derived_from:
            parent = _text(parent, "derived_from")
            if parent == artifact_id:
                raise ValueError("artifact cannot derive from itself")
            self._children.setdefault(parent, set()).add(artifact_id)

    def cascade(self, root: str) -> tuple[str, ...]:
        root = _text(root, "root")
        if root not in self._children:
            return ()
        visiting: set[str] = set()
        visited: set[str] = set()
        order: list[str] = []

        def walk(node: str) -> None:
            if node in visiting:
                raise ValueError("deletion graph contains a cycle")
            if node in visited:
                return
            visiting.add(node)
            for child in sorted(self._children.get(node, ())):
                walk(child)
            visiting.remove(node)
            visited.add(node)
            order.append(node)

        walk(root)
        return tuple(order)


@dataclass(frozen=True, slots=True)
class SBOMComponent:
    name: str
    version: str
    digest: str
    supplier: str

    def __post_init__(self) -> None:
        for name in ("name", "version", "supplier"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if (
            not isinstance(self.digest, str)
            or len(self.digest) != 64
            or any(c not in "0123456789abcdef" for c in self.digest)
        ):
            raise ValueError("component digest must be lowercase sha256")


@dataclass(frozen=True, slots=True)
class SBOM:
    artifact_digest: str
    components: tuple[SBOMComponent, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.artifact_digest, str)
            or len(self.artifact_digest) != 64
            or any(c not in "0123456789abcdef" for c in self.artifact_digest)
        ):
            raise ValueError("artifact_digest must be lowercase sha256")
        identities = [(c.name, c.version) for c in self.components]
        if len(identities) != len(set(identities)):
            raise ValueError("SBOM component identities must be unique")

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "artifact_digest": self.artifact_digest,
                "components": [
                    {
                        "name": c.name,
                        "version": c.version,
                        "digest": c.digest,
                        "supplier": c.supplier,
                    }
                    for c in sorted(self.components, key=lambda item: (item.name, item.version))
                ],
            }
        )
