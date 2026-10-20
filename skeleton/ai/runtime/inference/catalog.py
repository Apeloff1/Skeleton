"""Operator-supplied exact local routes over the existing artifact loaders.

Catalogs configure existing files only. They neither fetch models nor create a
provider, persistence authority, inference worker, or fallback route. Serialized
artifact byte limits and the conservative fresh-memory check are admission
guards, not claims that a file's length equals its eventual resident memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
from typing import Any

from skeleton.provider_runtime import ProviderProtocolViolationError, ProviderRequest, ProviderResponse

from .artifact import LocalModelArtifactError, load_local_model_artifact
from .deployment import LocalModelDeployment, LocalModelDeploymentError, _resolve
from .local import LocalInferenceEngine, LocalModelAdapter, sample_serving_resources

CATALOG_SCHEMA = "skeleton.local_model.catalog.v1"
_MAX_CATALOG_BYTES = 1024 * 1024
_MAX_MODELS = 8
_MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
_MAX_REFERENCED_BYTES = 1024**4
_MEMORY_RESERVE_BYTES = 256 * 1024 * 1024


class LocalModelCatalogError(RuntimeError):
    """An operator catalog cannot activate its exact pinned local routes."""


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LocalModelCatalogError("local catalog contains duplicate JSON keys")
        result[key] = value
    return result


def _reject_number(value: str) -> None:
    raise LocalModelCatalogError("local catalog permits only bounded integer resource values")


def _identity(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise LocalModelCatalogError(name + " must be normalized non-empty text")
    try:
        valid = len(value.encode("utf-8", errors="strict")) <= 256
    except UnicodeEncodeError as exc:
        raise LocalModelCatalogError(name + " must be valid Unicode") from exc
    if not valid:
        raise LocalModelCatalogError(name + " exceeds the 256-byte identity bound")
    return value


def _digest(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise LocalModelCatalogError("local catalog source sha256 must be lowercase SHA-256")
    return value


def _read(path: Path) -> bytes:
    try:
        before = path.stat()
        if not path.is_file() or not 1 <= before.st_size <= _MAX_CATALOG_BYTES:
            raise LocalModelCatalogError("local catalog violates its regular-file or byte bound")
        with path.open("rb") as stream:
            raw = stream.read(_MAX_CATALOG_BYTES + 1)
        after = path.stat()
    except OSError as exc:
        raise LocalModelCatalogError("local catalog is unavailable") from exc
    if (
        len(raw) != before.st_size
        or len(raw) > _MAX_CATALOG_BYTES
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    ):
        raise LocalModelCatalogError("local catalog changed during admission")
    return raw


def _memory_admission(serialized_bytes: int) -> None:
    if not serialized_bytes:
        return
    # Python graphs, parsed JSON, native checkpoints and admission snapshots can
    # coexist during loading. This estimate deliberately reserves more than the
    # serialized payload and leaves headroom for the rest of the application.
    conservative_estimate = serialized_bytes * 12 + _MEMORY_RESERVE_BYTES
    available = sample_serving_resources().available_memory_bytes
    if type(available) is not int:
        raise LocalModelCatalogError("fresh available-memory telemetry is required for resident artifact catalogs")
    if conservative_estimate > available:
        raise LocalModelCatalogError("resident artifact catalog exceeds conservative available-memory admission")


def _verify_source(path: Path, expected: str, expected_bytes: int) -> None:
    """Bound source hashing by the admitted size, including concurrent growth."""

    digest = hashlib.sha256()
    count = 0
    try:
        before = path.stat()
        if path.is_symlink() or not path.is_file() or before.st_size != expected_bytes:
            raise LocalModelCatalogError("local catalog source changed its admitted file identity")
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(min(1024 * 1024, expected_bytes + 1 - count))
                if not chunk:
                    break
                count += len(chunk)
                if count > expected_bytes:
                    raise LocalModelCatalogError("local catalog source grew beyond its admitted byte bound")
                digest.update(chunk)
        after = path.stat()
    except OSError as exc:
        raise LocalModelCatalogError("local catalog pinned source is unavailable") from exc
    if (
        count != expected_bytes
        or digest.hexdigest() != expected
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    ):
        raise LocalModelCatalogError("local catalog source digest or file identity changed")


@dataclass(frozen=True, slots=True)
class LocalModelCatalogEntry:
    model_id: str
    kind: str
    path: Path
    sha256: str
    source_bytes: int
    entry_digest: str
    deployment: LocalModelDeployment | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class LocalModelCatalog:
    manifest_path: Path
    catalog_digest: str
    primary_model_id: str
    verifier_model_id: str | None
    max_total_artifact_bytes: int
    referenced_artifact_bytes: int
    entries: tuple[LocalModelCatalogEntry, ...]

    @classmethod
    def load(cls, path: str | Path) -> LocalModelCatalog:
        try:
            source = _resolve(Path.cwd(), str(path), "catalog path", reject_symlink=True)
            raw = _read(source)
            payload = json.loads(
                raw.decode("utf-8", errors="strict"), object_pairs_hook=_object,
                parse_constant=_reject_number, parse_float=_reject_number,
            )
        except (OSError, UnicodeDecodeError, ValueError, RecursionError, LocalModelDeploymentError) as exc:
            raise LocalModelCatalogError("local catalog could not be read safely") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != CATALOG_SCHEMA:
            raise LocalModelCatalogError("unsupported local catalog schema")
        required = {"schema_version", "primary_model_id", "max_total_artifact_bytes", "models"}
        if not required <= set(payload) or set(payload) - required - {"verifier_model_id"}:
            raise LocalModelCatalogError("local catalog has missing or unsupported fields")
        primary = _identity(payload["primary_model_id"], "primary_model_id")
        verifier = payload.get("verifier_model_id")
        if "verifier_model_id" in payload:
            verifier = _identity(verifier, "verifier_model_id")
            if verifier == primary:
                raise LocalModelCatalogError("local catalog verifier must differ from its primary route")
        limit = payload["max_total_artifact_bytes"]
        if type(limit) is not int or not 1 <= limit <= _MAX_REFERENCED_BYTES:
            raise LocalModelCatalogError("local catalog artifact budget must be an integer in [1, 1 TiB]")
        models = payload["models"]
        if not isinstance(models, list) or not 1 <= len(models) <= _MAX_MODELS:
            raise LocalModelCatalogError("local catalogs require between 1 and 8 named models")
        entries: list[LocalModelCatalogEntry] = []
        seen: set[str] = set()
        referenced: dict[Path, int] = {}
        resident_bytes = 0
        try:
            for row in models:
                if not isinstance(row, dict) or set(row) != {"model_id", "kind", "path", "sha256"}:
                    raise LocalModelCatalogError("local catalog entries require model_id, kind, path and sha256 only")
                model_id = _identity(row["model_id"], "model_id")
                if model_id in seen:
                    raise LocalModelCatalogError("local catalog model identities must be unique")
                seen.add(model_id)
                kind = row["kind"]
                if kind not in {"artifact", "deployment"}:
                    raise LocalModelCatalogError("local catalog kind must be artifact or deployment")
                expected_digest = _digest(row["sha256"])
                entry_path = _resolve(source.parent, row["path"], "catalog model path", reject_symlink=True)
                source_bytes = entry_path.stat().st_size
                if not 1 <= source_bytes <= (_MAX_ARTIFACT_BYTES if kind == "artifact" else _MAX_CATALOG_BYTES):
                    raise LocalModelCatalogError("local catalog source exceeds its existing loader byte bound")
                _verify_source(entry_path, expected_digest, source_bytes)
                referenced[entry_path] = source_bytes
                deployment = None
                if kind == "deployment":
                    deployment = LocalModelDeployment.load(
                        entry_path, expected_sha256=expected_digest, max_artifact_bytes=limit,
                    )
                    for artifact in (deployment.model_path, deployment.executable_path):
                        referenced[artifact] = artifact.stat().st_size
                else:
                    resident_bytes += source_bytes
                _verify_source(entry_path, expected_digest, source_bytes)
                if sum(referenced.values()) > limit:
                    raise LocalModelCatalogError("local catalog exceeds its declared referenced-artifact byte budget")
                entry_digest = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
                entries.append(LocalModelCatalogEntry(model_id, kind, entry_path, expected_digest, source_bytes, entry_digest, deployment))
        except (OSError, TypeError, ValueError, LocalModelDeploymentError) as exc:
            raise LocalModelCatalogError("local catalog source preflight failed") from exc
        if primary not in seen or (verifier is not None and verifier not in seen):
            raise LocalModelCatalogError("local catalog primary and verifier must name configured entries")
        _memory_admission(resident_bytes)
        if _read(source) != raw:
            raise LocalModelCatalogError("local catalog changed during source preflight")
        return cls(source, hashlib.sha256(raw).hexdigest(), primary, verifier, limit, sum(referenced.values()), tuple(entries))


class _CatalogLocalAdapter(LocalModelAdapter):
    """Bind a configured route name without changing the underlying model."""

    def __init__(self, adapter: LocalModelAdapter, catalog: LocalModelCatalog, entry: LocalModelCatalogEntry) -> None:
        source_model_id = _identity(adapter.model, "source_model_id")
        artifact = dict(adapter._artifact_status or {})
        artifact.update({
            "model_id": entry.model_id,
            "source_model_id": source_model_id,
            "catalog_digest": catalog.catalog_digest,
            "catalog_entry_digest": entry.entry_digest,
            "catalog_source_sha256": entry.sha256,
        })
        super().__init__(adapter.engine, default_seed=adapter.default_seed, artifact_status=artifact)
        self.model = entry.model_id
        self._catalog_model_id = entry.model_id
        self._source_model_id = source_model_id
        self._catalog_receipt_binding = (catalog.catalog_digest, entry.entry_digest, entry.sha256, entry.model_id)

    @property
    def available(self) -> bool:
        return self.model == self._catalog_model_id and self.engine.model.model_id == self._source_model_id and super().available

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        response = await super().generate(request)
        if response.provider != "local" or response.model != self._source_model_id:
            raise ProviderProtocolViolationError("catalog model response differs from its activated source")
        receipt = response.execution_receipt_digest
        if receipt is not None:
            receipt = hashlib.sha256(json.dumps({
                "source_receipt": receipt,
                "catalog_route": self._catalog_receipt_binding,
            }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        return replace(response, model=self.model, execution_receipt_digest=receipt)


@dataclass(frozen=True, slots=True)
class LocalModelCatalogActivation:
    catalog: LocalModelCatalog
    adapters: tuple[LocalModelAdapter, ...]
    verification_adapter: LocalModelAdapter | None


def load_local_model_catalog(
    path: str | Path,
    *,
    cache_size: int = 0,
    default_seed: int = 0,
    max_concurrency: int = 1,
    max_queue_size: int = 256,
    max_batch_size: int = 256,
) -> LocalModelCatalogActivation:
    """Activate a bounded explicit catalog, after every source passes preflight."""

    catalog = LocalModelCatalog.load(path)
    adapters: dict[str, LocalModelAdapter] = {}
    remaining_resident = sum(entry.source_bytes for entry in catalog.entries if entry.kind == "artifact")
    capacity = {"max_concurrency": max_concurrency, "max_queue_size": max_queue_size, "max_batch_size": max_batch_size}
    try:
        for entry in catalog.entries:
            _verify_source(entry.path, entry.sha256, entry.source_bytes)
            if entry.kind == "deployment":
                if entry.deployment is None:
                    raise LocalModelCatalogError("local catalog deployment preflight is missing")
                adapter = entry.deployment.adapter(cache_size=cache_size, default_seed=default_seed, rehash_artifacts_each_run=True, **capacity)
            else:
                _memory_admission(remaining_resident)
                loaded = load_local_model_artifact(entry.path, expected_sha256=entry.sha256)
                if loaded.receipt.artifact_sha256 != entry.sha256:
                    raise LocalModelCatalogError("loaded artifact differs from its catalog digest pin")
                adapter = LocalModelAdapter(LocalInferenceEngine(loaded.model, cache_size=cache_size, **capacity), default_seed=default_seed, artifact_status=loaded.receipt.as_dict())
                remaining_resident -= entry.source_bytes
            _verify_source(entry.path, entry.sha256, entry.source_bytes)
            adapters[entry.model_id] = _CatalogLocalAdapter(adapter, catalog, entry)
    except (LocalModelArtifactError, LocalModelDeploymentError, OSError, TypeError, ValueError) as exc:
        raise LocalModelCatalogError("local catalog activation failed") from exc
    primary = adapters[catalog.primary_model_id]
    verifier = None if catalog.verifier_model_id is None else adapters[catalog.verifier_model_id]
    if verifier is not None and verifier.engine.model.model_digest == primary.engine.model.model_digest:
        raise LocalModelCatalogError("local catalog semantic verifier must have different actual model weights")
    ordered = (primary, *(adapter for name, adapter in adapters.items() if name != catalog.primary_model_id))
    return LocalModelCatalogActivation(catalog, ordered, verifier)


__all__ = ["CATALOG_SCHEMA", "LocalModelCatalog", "LocalModelCatalogEntry", "LocalModelCatalogActivation", "LocalModelCatalogError", "load_local_model_catalog"]
