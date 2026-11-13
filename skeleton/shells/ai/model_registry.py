"""Versioned registry for model/provider attestations used by shell planning."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import FrozenSet

from skeleton.shells.ai.provider_attestation import ProviderAttestation


@dataclass(frozen=True)
class RegisteredModel:
    registry_id: str
    revision: int
    attestation: ProviderAttestation
    active: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "registry_id": self.registry_id,
            "revision": self.revision,
            "active": self.active,
            "attestation_digest": self.attestation.digest,
            "provider_id": self.attestation.provider_id,
            "model_id": self.attestation.model_id,
            "model_version": self.attestation.model_version,
            "adapter_version": self.attestation.adapter_version,
        }


class ModelRegistryConflict(RuntimeError):
    pass


class ModelNotReadyError(RuntimeError):
    """A registered model lacks verified operator admission facts."""


@dataclass(frozen=True)
class ModelCapability:
    """Explicit, revision-bound evidence; never an implicit cloud-provider grant.

    weights_ready is an operator claim, not a cryptographic verification of bytes.
    Native loader custody must independently verify the declared digest on disk.
    """

    weights_ready: bool = False
    weights_digest: str | None = None
    license_id: str | None = None
    allowed_uses: FrozenSet[str] = frozenset()
    vram_required_mb: int = 0

    def __post_init__(self) -> None:
        if type(self.vram_required_mb) is not int or self.vram_required_mb < 0 or self.vram_required_mb > 1_048_576:
            raise ValueError("VRAM requirement must be bounded non-negative MiB")
        if type(self.weights_ready) is not bool:
            raise ValueError("weights_ready must be a bool")
        if not isinstance(self.allowed_uses, (frozenset, set, tuple, list)) or any(
            not isinstance(x, str) or not x or len(x) > 96 for x in self.allowed_uses
        ):
            raise ValueError("allowed uses must be bounded non-empty tokens")
        object.__setattr__(self, "allowed_uses", frozenset(self.allowed_uses))

    def check(self, *, use: str, available_vram_mb: int | None) -> None:
        if not self.weights_ready or not isinstance(self.weights_digest, str) or not self.weights_digest.strip():
            raise ModelNotReadyError("model weights are not ready")
        if not isinstance(self.license_id, str) or not self.license_id.strip():
            raise ModelNotReadyError("model rights are not declared")
        if use not in self.allowed_uses:
            raise ModelNotReadyError("model rights do not permit requested use")
        if self.vram_required_mb:
            if type(available_vram_mb) is not int or available_vram_mb < 0:
                raise ModelNotReadyError("VRAM capacity is unknown")
            if available_vram_mb < self.vram_required_mb:
                raise ModelNotReadyError("insufficient VRAM for model")

    def to_dict(self) -> dict[str, object]:
        return {
            "weights_ready": self.weights_ready,
            "weights_digest": self.weights_digest,
            "license_id": self.license_id,
            "allowed_uses": sorted(self.allowed_uses),
            "vram_required_mb": self.vram_required_mb,
        }


class AIModelRegistry:
    """Attestation revisions are explicit; old versions remain inspectable."""

    def __init__(
        self,
        *,
        max_models: int = 1024,
        max_versions_per_model: int = 128,
    ) -> None:
        if max_models <= 0 or max_versions_per_model <= 0:
            raise ValueError("model registry limits must be positive")
        self.max_models = max_models
        self.max_versions_per_model = max_versions_per_model
        self._items: dict[str, list[RegisteredModel]] = {}
        self._capabilities: dict[str, tuple[int, str, ModelCapability]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def registry_id(attestation: ProviderAttestation) -> str:
        return f"{attestation.provider_id}:{attestation.model_id}"

    def register(
        self,
        attestation: ProviderAttestation,
        *,
        expected_revision: int | None = None,
        activate: bool = True,
    ) -> RegisteredModel:
        registry_id = self.registry_id(attestation)
        with self._lock:
            history = self._items.get(registry_id)
            if history is None:
                if len(self._items) >= self.max_models:
                    raise RuntimeError("model registry capacity exhausted")
                if expected_revision not in {None, 0}:
                    raise ModelRegistryConflict("model is not registered")
                item = RegisteredModel(registry_id, 1, attestation, activate)
                self._items[registry_id] = [item]
                return item
            current = history[-1]
            if expected_revision is not None and current.revision != expected_revision:
                raise ModelRegistryConflict("model registry revision conflict")
            if current.attestation.digest == attestation.digest and current.active == activate:
                return current
            item = RegisteredModel(
                registry_id,
                current.revision + 1,
                attestation,
                activate,
            )
            history.append(item)
            self._capabilities.pop(registry_id, None)  # revision/weights change revokes grant
            if len(history) > self.max_versions_per_model:
                del history[:-self.max_versions_per_model]
            return item

    def current(self, registry_id: str) -> RegisteredModel:
        with self._lock:
            return self._items[registry_id][-1]

    def deactivate(
        self,
        registry_id: str,
        *,
        expected_revision: int | None = None,
    ) -> RegisteredModel:
        with self._lock:
            current = self.current(registry_id)
            if expected_revision is not None and current.revision != expected_revision:
                raise ModelRegistryConflict("model registry revision conflict")
            if not current.active:
                return current
            item = RegisteredModel(
                registry_id,
                current.revision + 1,
                current.attestation,
                False,
            )
            self._items[registry_id].append(item)
            self._capabilities.pop(registry_id, None)  # activation transitions revoke grants
            return item

    def activate(
        self,
        registry_id: str,
        *,
        expected_revision: int | None = None,
    ) -> RegisteredModel:
        with self._lock:
            current = self.current(registry_id)
            if expected_revision is not None and current.revision != expected_revision:
                raise ModelRegistryConflict("model registry revision conflict")
            if current.active:
                return current
            item = RegisteredModel(
                registry_id,
                current.revision + 1,
                current.attestation,
                True,
            )
            self._items[registry_id].append(item)
            self._capabilities.pop(registry_id, None)  # activation transitions revoke grants
            return item

    def history(self, registry_id: str) -> tuple[RegisteredModel, ...]:
        with self._lock:
            return tuple(self._items[registry_id])

    def active(self) -> tuple[RegisteredModel, ...]:
        with self._lock:
            result = [
                history[-1]
                for history in self._items.values()
                if history[-1].active
            ]
        result.sort(key=lambda item: item.registry_id)
        return tuple(result)

    def set_capability(
        self, registry_id: str, capability: ModelCapability, *,
        expected_revision: int | None = None,
    ) -> None:
        if not isinstance(capability, ModelCapability):
            raise TypeError("capability must be a ModelCapability")
        with self._lock:
            history = self._items.get(registry_id)
            if not history:
                raise KeyError(registry_id)
            current = history[-1]
            if not current.active:
                raise ModelNotReadyError("inactive models cannot receive an admission grant")
            if expected_revision is not None and expected_revision != current.revision:
                raise ModelRegistryConflict("model readiness source revision changed")
            self._capabilities[registry_id] = (
                current.revision, current.attestation.digest, capability,
            )

    def capability(self, registry_id: str) -> ModelCapability | None:
        with self._lock:
            history = self._items.get(registry_id)
            grant = self._capabilities.get(registry_id)
            if not history or not grant:
                return None
            current = history[-1]
            return grant[2] if current.active and grant[:2] == (
                current.revision, current.attestation.digest
            ) else None

    def require_ready(
        self, registry_id: str, *, use: str, available_vram_mb: int | None = None,
    ) -> RegisteredModel:
        with self._lock:
            history = self._items.get(registry_id)
            if not history:
                raise ModelNotReadyError("model is not registered")
            current = history[-1]
            if not current.active:
                raise ModelNotReadyError("model is not active")
            capability = self.capability(registry_id)
            if capability is None:
                raise ModelNotReadyError("model capability is not declared for this revision")
            capability.check(use=use, available_vram_mb=available_vram_mb)
            return current

    def capability_report(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {
                rid: self.capability(rid).to_dict() if self.capability(rid) else {"declared": False}
                for rid in sorted(self._items)
            }
