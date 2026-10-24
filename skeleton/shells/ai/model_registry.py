"""Versioned registry for model/provider attestations used by shell planning."""

from __future__ import annotations

from dataclasses import dataclass
import threading

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


# --- GF-P0-15: model-weight readiness, rights and VRAM capability discovery ---

import os as _os
import shutil as _shutil
import subprocess as _subprocess


class ModelNotReadyError(RuntimeError):
    """Raised when a model may not be invoked (weights, rights or VRAM)."""


@dataclass(frozen=True)
class ModelCapability:
    """Operator-declared readiness facts for one registered model.

    Deny-by-default: an unknown model, unready weights, a missing licence or a
    use outside ``allowed_uses`` all fail closed in :meth:`check`.
    """

    weights_ready: bool = False
    weights_digest: str | None = None
    license_id: str | None = None
    allowed_uses: frozenset[str] = frozenset()
    vram_required_mb: int = 0

    def __post_init__(self) -> None:
        if self.vram_required_mb < 0:
            raise ValueError("vram_required_mb must be non-negative")
        object.__setattr__(self, "allowed_uses", frozenset(self.allowed_uses))

    def check(self, *, use: str, available_vram_mb: int | None) -> None:
        if not self.weights_ready or not self.weights_digest:
            raise ModelNotReadyError("model weights are not ready")
        if not self.license_id:
            raise ModelNotReadyError("model rights are not declared")
        if use not in self.allowed_uses:
            raise ModelNotReadyError(f"model rights do not permit use: {use}")
        if self.vram_required_mb:
            if available_vram_mb is None:
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


def discover_vram_mb(*, runner=None) -> int | None:
    """Best-effort free-VRAM discovery in MiB; ``None`` when unknown.

    ``SKELETON_VRAM_MB`` overrides discovery. Otherwise ``nvidia-smi`` is
    queried with a short timeout; failures return ``None`` (fail closed).
    """

    override = _os.getenv("SKELETON_VRAM_MB", "").strip()
    if override:
        try:
            value = int(override)
        except ValueError:
            return None
        return value if value >= 0 else None
    if runner is None:
        if _shutil.which("nvidia-smi") is None:
            return None

        def runner() -> str:
            return _subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout

    try:
        lines = [line.strip() for line in str(runner()).splitlines() if line.strip()]
        values = [int(float(line)) for line in lines]
    except Exception:
        return None
    return max(values) if values else None


def _registry_set_capability(
    self: AIModelRegistry, registry_id: str, capability: ModelCapability
) -> None:
    with self._lock:
        if registry_id not in self._items:
            raise KeyError(registry_id)
        caps = self.__dict__.setdefault("_capabilities", {})
        caps[registry_id] = capability


def _registry_capability(self: AIModelRegistry, registry_id: str) -> ModelCapability | None:
    with self._lock:
        return self.__dict__.get("_capabilities", {}).get(registry_id)


def _registry_require_ready(
    self: AIModelRegistry,
    registry_id: str,
    *,
    use: str,
    available_vram_mb: int | None = None,
) -> RegisteredModel:
    with self._lock:
        history = self._items.get(registry_id)
        if not history:
            raise ModelNotReadyError("model is not registered")
        current = history[-1]
        if not current.active:
            raise ModelNotReadyError("model is not active")
        capability = self.__dict__.get("_capabilities", {}).get(registry_id)
    if capability is None:
        raise ModelNotReadyError("model capability is not declared")
    capability.check(use=use, available_vram_mb=available_vram_mb)
    return current


def _registry_capability_report(self: AIModelRegistry) -> dict[str, dict[str, object]]:
    with self._lock:
        caps = dict(self.__dict__.get("_capabilities", {}))
        ids = sorted(self._items)
    return {rid: (caps[rid].to_dict() if rid in caps else {"declared": False}) for rid in ids}


AIModelRegistry.set_capability = _registry_set_capability
AIModelRegistry.capability = _registry_capability
AIModelRegistry.require_ready = _registry_require_ready
AIModelRegistry.capability_report = _registry_capability_report
