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
