"""Versioned registry for model/provider attestations used by shell planning."""

from __future__ import annotations

from dataclasses import dataclass
import json
import stat
import threading
from pathlib import Path
from typing import FrozenSet

from skeleton.shells.ai.provider_attestation import ProviderAttestation

# Licenses already admitted by registry capability evidence. Discovery and
# admission refuse every other declared license. This set is not a weight file
# and it does not measure hardware.
MODEL_LICENSE_ALLOWLIST = frozenset({"MIT", "apache-2.0"})
_DISCOVERY_SCHEMA = "skeleton.model_weight_discovery.v1"
_DTYPE_BYTES = {
    "f64": 8,
    "f32": 4,
    "bf16": 2,
    "f16": 2,
    "i64": 8,
    "i32": 4,
    "i16": 2,
    "i8": 1,
    "u8": 1,
}
_MAX_MANIFEST_BYTES = 1_048_576
_MAX_TENSORS = 4096
_MAX_DIMS = 8
_MAX_DIM = 1_000_000_000
_MAX_ESTIMATE_BYTES = 1 << 40


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
        if self.license_id not in MODEL_LICENSE_ALLOWLIST:
            raise ModelNotReadyError("model license is outside the allow-list")
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

    def discover_weights(self, manifest_path: str | Path) -> "WeightDiscoveryReport":
        """Report declared weight facts. Does not load bytes or grant readiness."""

        return discover_model_weights(manifest_path)

    def capability_report(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {
                rid: self.capability(rid).to_dict() if self.capability(rid) else {"declared": False}
                for rid in sorted(self._items)
            }


def _reject_constant(value: str) -> None:
    raise ModelNotReadyError("discovery manifest contains a non-finite constant")


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ModelNotReadyError("discovery manifest repeats a key")
        result[key] = value
    return result


def _token(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 128:
        raise ModelNotReadyError(f"{label} is not a declared token")
    if any(ord(char) < 32 for char in value):
        raise ModelNotReadyError(f"{label} is not a declared token")
    return value


def _tensor_bytes(shape: object, dtype: str) -> int:
    if not isinstance(shape, list) or not 1 <= len(shape) <= _MAX_DIMS:
        raise ModelNotReadyError("declared tensor shape is invalid")
    total = _DTYPE_BYTES[dtype]
    for dim in shape:
        if type(dim) is not int or not 1 <= dim <= _MAX_DIM:
            raise ModelNotReadyError("declared tensor shape is invalid")
        total *= dim
        if total > _MAX_ESTIMATE_BYTES:
            raise ModelNotReadyError("declared tensor table exceeds the estimate bound")
    return total


def _artifact_file(manifest: Path, declared: object) -> Path:
    if (
        not isinstance(declared, str)
        or not declared
        or declared.startswith(("/", "\\"))
        or ".." in Path(declared).parts
    ):
        raise ModelNotReadyError("artifact path is not a relative declaration")
    root = manifest.parent.resolve()
    candidate = (root / declared).resolve()
    if candidate != root and root not in candidate.parents:
        raise ModelNotReadyError("artifact path escapes the declaration directory")
    return candidate


def _artifact_present(path: Path) -> bool:
    """Stat the path only. Never open or hash the bytes."""

    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode)


@dataclass(frozen=True)
class TensorDeclaration:
    name: str
    dtype: str
    shape: tuple[int, ...]
    nbytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "nbytes": self.nbytes,
        }


@dataclass(frozen=True)
class WeightDiscoveryReport:
    """Facts from a declaration and a presence check.

    ``estimated_vram_bytes`` is the sum of the declared tensor table.
    ``weights_loaded`` and ``hardware_vram_measured`` stay false: this report
    never reads weight bytes and never queries a device.
    """

    artifact_present: bool
    architecture_id: str
    license_id: str
    license_allowed: bool
    estimated_vram_bytes: int
    tensors: tuple[TensorDeclaration, ...]
    weights_loaded: bool = False
    hardware_vram_measured: bool = False
    estimate_source: str = "declared_tensor_table"

    def __post_init__(self) -> None:
        object.__setattr__(self, "weights_loaded", False)
        object.__setattr__(self, "hardware_vram_measured", False)
        object.__setattr__(self, "estimate_source", "declared_tensor_table")
        if type(self.artifact_present) is not bool or type(self.license_allowed) is not bool:
            raise ModelNotReadyError("discovery flags must be booleans")
        if type(self.estimated_vram_bytes) is not int or self.estimated_vram_bytes < 0:
            raise ModelNotReadyError("VRAM estimate must be a non-negative integer")

    @property
    def ready(self) -> bool:
        return self.artifact_present and self.license_allowed and bool(self.tensors)

    def require_admitted(self) -> "WeightDiscoveryReport":
        if not self.artifact_present:
            raise ModelNotReadyError("model weight artifact is absent")
        if not self.license_allowed:
            raise ModelNotReadyError("model license is outside the allow-list")
        if not self.tensors:
            raise ModelNotReadyError("declared tensor table is empty")
        return self

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_present": self.artifact_present,
            "architecture_id": self.architecture_id,
            "license_id": self.license_id,
            "license_allowed": self.license_allowed,
            "estimated_vram_bytes": self.estimated_vram_bytes,
            "estimate_source": self.estimate_source,
            "weights_loaded": self.weights_loaded,
            "hardware_vram_measured": self.hardware_vram_measured,
            "ready": self.ready,
            "tensors": [item.to_dict() for item in self.tensors],
        }


def discover_model_weights(manifest_path: str | Path) -> WeightDiscoveryReport:
    """Read a declaration and stat the named artifact.

    The artifact file is not opened. VRAM is the declared tensor table, not a
    device measurement. A missing file is not ready. A license outside
    ``MODEL_LICENSE_ALLOWLIST`` is not allowed.
    """

    if not isinstance(manifest_path, (str, Path)):
        raise ModelNotReadyError("discovery manifest path is invalid")
    manifest = Path(manifest_path)
    try:
        info = manifest.lstat()
    except OSError as exc:
        raise ModelNotReadyError("discovery manifest is absent") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_MANIFEST_BYTES:
        raise ModelNotReadyError("discovery manifest is not a bounded file")
    try:
        raw = manifest.read_bytes()
    except OSError as exc:
        raise ModelNotReadyError("discovery manifest is unreadable") from exc
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise ModelNotReadyError("discovery manifest is not a bounded file")
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ModelNotReadyError) as exc:
        raise ModelNotReadyError("discovery manifest is not strict JSON") from exc
    if not isinstance(payload, dict):
        raise ModelNotReadyError("discovery manifest is not an object")
    expected = {"schema", "architecture_id", "license_id", "artifact", "tensors"}
    if set(payload) != expected or payload.get("schema") != _DISCOVERY_SCHEMA:
        raise ModelNotReadyError("discovery manifest schema is not recognized")
    architecture_id = _token(payload.get("architecture_id"), "architecture_id")
    license_id = _token(payload.get("license_id"), "license_id")
    tensors_raw = payload.get("tensors")
    if not isinstance(tensors_raw, list) or not 1 <= len(tensors_raw) <= _MAX_TENSORS:
        raise ModelNotReadyError("declared tensor table is invalid")
    tensors: list[TensorDeclaration] = []
    names: set[str] = set()
    estimated = 0
    for item in tensors_raw:
        if not isinstance(item, dict) or set(item) != {"name", "dtype", "shape"}:
            raise ModelNotReadyError("tensor declaration must not inline weight bytes")
        name = _token(item.get("name"), "tensor name")
        dtype = item.get("dtype")
        if not isinstance(dtype, str) or dtype not in _DTYPE_BYTES:
            raise ModelNotReadyError("declared tensor dtype is unknown")
        if name in names:
            raise ModelNotReadyError("declared tensor name is duplicated")
        names.add(name)
        shape = item.get("shape")
        nbytes = _tensor_bytes(shape, dtype)
        if not isinstance(shape, list):
            raise ModelNotReadyError("declared tensor shape is invalid")
        tensors.append(TensorDeclaration(name, dtype, tuple(shape), nbytes))
        estimated += nbytes
        if estimated > _MAX_ESTIMATE_BYTES:
            raise ModelNotReadyError("declared tensor table exceeds the estimate bound")
    artifact = _artifact_file(manifest, payload.get("artifact"))
    present = _artifact_present(artifact)
    allowed = license_id in MODEL_LICENSE_ALLOWLIST
    return WeightDiscoveryReport(
        artifact_present=present,
        architecture_id=architecture_id,
        license_id=license_id,
        license_allowed=allowed,
        estimated_vram_bytes=estimated,
        tensors=tuple(tensors),
    )


def require_discovered_weights(manifest_path: str | Path) -> WeightDiscoveryReport:
    """Refuse a declaration that is absent or outside the license allow-list."""

    return discover_model_weights(manifest_path).require_admitted()
