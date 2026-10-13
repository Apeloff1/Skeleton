"""Content-addressed, bounded binary shard storage for model and shadow weights.

A WeightLoadPlan is a contract, not proof that any bytes were loaded. This
store streams source files into immutable SHA-256 objects and admits a manifest
only after the physical content, order and byte counts match the plan.
Decoding, tensor shape validation and GPU placement remain the model loader's
responsibility; shadow bytes never become production weights implicitly.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import BinaryIO, Iterator, Mapping
from uuid import uuid4

from .flgb_model_runtime import (
    MAX_WEIGHT_BYTES, ModelIdentity, ModelRuntimeError, WeightLoadPlan,
    WeightShard, canonical_bytes, digest_json, require_digest,
)

_CHUNK_SIZE = 4 * 1024 * 1024


class WeightShardStoreError(ModelRuntimeError):
    """Failure to ingest or read verified native or shadow model bytes."""


def _hash_file(path: Path, *, maximum: int) -> tuple[str, int]:
    digest = sha256()
    size = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(_CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            if size > maximum:
                raise WeightShardStoreError("weight object exceeds manifest byte budget")
            digest.update(chunk)
    return digest.hexdigest(), size


class WeightShardStore:
    """Immutable CAS with deterministic manifests and bounded stream memory."""

    def __init__(self, directory: str | Path, *, maximum_bytes: int = MAX_WEIGHT_BYTES) -> None:
        if isinstance(maximum_bytes, bool) or not isinstance(maximum_bytes, int) or not 1 <= maximum_bytes <= MAX_WEIGHT_BYTES:
            raise WeightShardStoreError("invalid weight-storage budget")
        self.root = Path(directory)
        self.objects = self.root / "objects"
        self.manifests = self.root / "manifests"
        self.objects.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.manifests.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.maximum_bytes = maximum_bytes

    def _object_path(self, digest: str) -> Path:
        require_digest(digest, "weight_object_digest")
        return self.objects / digest[:2] / digest

    def _manifest_path(self, digest: str) -> Path:
        require_digest(digest, "weight_manifest_digest")
        return self.manifests / (digest + ".json")

    @staticmethod
    def _write_once(path: Path, content: bytes) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != content:
                raise WeightShardStoreError("existing content-addressed manifest is inconsistent")
            return
        tmp = path.with_name("." + path.name + "." + uuid4().hex + ".tmp")
        try:
            with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            # Concurrent writers can publish identical bytes; no writer may
            # change the digest-owned contents of an existing object.
            if path.exists():
                if path.read_bytes() != content:
                    raise WeightShardStoreError("concurrent manifest content mismatch")
            else:
                os.replace(tmp, path)
                if os.name == "posix":
                    directory_fd = os.open(path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
        finally:
            tmp.unlink(missing_ok=True)

    def _ingest(self, shard: WeightShard, source: str | Path) -> Path:
        path = Path(source)
        if path.is_symlink() or not path.is_file():
            raise WeightShardStoreError("weight shard input must be a regular non-symlink file")
        target = self._object_path(shard.digest)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.exists():
            observed, size = _hash_file(target, maximum=shard.bytes)
            if observed != shard.digest or size != shard.bytes:
                raise WeightShardStoreError("existing weight object failed content identity")
            return target

        tmp = target.with_name("." + target.name + "." + uuid4().hex + ".tmp")
        try:
            digest = sha256()
            size = 0
            with path.open("rb") as reader, os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as writer:
                while True:
                    block = reader.read(_CHUNK_SIZE)
                    if not block:
                        break
                    size += len(block)
                    if size > shard.bytes:
                        raise WeightShardStoreError("source exceeds declared shard size")
                    digest.update(block)
                    writer.write(block)
                if size != shard.bytes or digest.hexdigest() != shard.digest:
                    raise WeightShardStoreError("weight shard bytes differ from committed digest")
                writer.flush()
                os.fsync(writer.fileno())
            if target.exists():
                observed, stored_size = _hash_file(target, maximum=shard.bytes)
                if observed != shard.digest or stored_size != shard.bytes:
                    raise WeightShardStoreError("concurrent weight object mismatch")
            else:
                os.replace(tmp, target)
                if os.name == "posix":
                    directory_fd = os.open(target.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
        finally:
            tmp.unlink(missing_ok=True)
        return target

    def stage_plan(
        self,
        identity: ModelIdentity,
        plan: WeightLoadPlan,
        source_paths: Mapping[int, str | Path],
    ) -> str:
        """Materialize a model's physical bytes, never activating a model."""
        if not isinstance(identity, ModelIdentity) or not isinstance(plan, WeightLoadPlan):
            raise WeightShardStoreError("model identity and weight load plan required")
        if plan.model_identity_digest != identity.identity_digest:
            raise WeightShardStoreError("model identity differs from weight load plan")
        if plan.expected_total_bytes > self.maximum_bytes:
            raise WeightShardStoreError("weight plan exceeds storage budget")
        if set(source_paths) != {shard.index for shard in plan.shards}:
            raise WeightShardStoreError("source index set does not match shard manifest")
        for shard in plan.shards:
            self._ingest(shard, source_paths[shard.index])
        manifest = {
            "schema_version": 1,
            "model_identity_digest": identity.identity_digest,
            "weights_digest": identity.weights_digest,
            "plan_digest": plan.digest,
            "expected_total_bytes": plan.expected_total_bytes,
            "shards": [asdict(shard) for shard in plan.shards],
        }
        self._write_once(self._manifest_path(plan.digest), canonical_bytes(manifest))
        return plan.digest

    def load_plan(self, plan_digest: str) -> WeightLoadPlan:
        """Reconstruct a committed plan without trusting caller-supplied paths."""
        path = self._manifest_path(plan_digest)
        try:
            raw = path.read_bytes()
            manifest = json.loads(raw)
        except (OSError, ValueError) as exc:
            raise WeightShardStoreError("weight plan manifest unavailable") from exc
        if not isinstance(manifest, dict) or set(manifest) != {
            "schema_version", "model_identity_digest", "weights_digest",
            "plan_digest", "expected_total_bytes", "shards",
        } or manifest["schema_version"] != 1:
            raise WeightShardStoreError("weight manifest schema mismatch")
        require_digest(manifest["weights_digest"], "weights_digest")
        if manifest["plan_digest"] != plan_digest or canonical_bytes(manifest) != raw:
            raise WeightShardStoreError("weight manifest is not canonical or has wrong identity")
        try:
            plan = WeightLoadPlan(
                model_identity_digest=manifest["model_identity_digest"],
                shards=tuple(WeightShard(**row) for row in manifest["shards"]),
                expected_total_bytes=manifest["expected_total_bytes"],
            )
        except (TypeError, ValueError) as exc:
            raise WeightShardStoreError("malformed weight shard manifest") from exc
        if plan.digest != plan_digest or plan.expected_total_bytes > self.maximum_bytes:
            raise WeightShardStoreError("weight manifest digest or budget mismatch")
        return plan

    def verified_paths(self, plan_digest: str) -> tuple[Path, ...]:
        """Return only shards that still match their immutable content identity."""
        plan = self.load_plan(plan_digest)
        paths = []
        for shard in plan.shards:
            path = self._object_path(shard.digest)
            try:
                digest, count = _hash_file(path, maximum=shard.bytes)
            except OSError as exc:
                raise WeightShardStoreError("referenced weight object is unavailable") from exc
            if digest != shard.digest or count != shard.bytes:
                raise WeightShardStoreError("stored weight object changed since admission")
            paths.append(path)
        return tuple(paths)

    @contextmanager
    def open_verified(
        self, plan_digest: str, *, model_identity: ModelIdentity,
    ) -> Iterator[tuple[BinaryIO, ...]]:
        """Open verified, ordered shard streams for an explicit model decoder."""
        if not isinstance(model_identity, ModelIdentity):
            raise WeightShardStoreError("model identity required for weight loading")
        plan = self.load_plan(plan_digest)
        if plan.model_identity_digest != model_identity.identity_digest:
            raise WeightShardStoreError("requested model is not bound to this weight plan")
        raw = self._manifest_path(plan_digest).read_bytes()
        data = json.loads(raw)
        if data["weights_digest"] != model_identity.weights_digest:
            raise WeightShardStoreError("weights identity mismatch")
        paths = self.verified_paths(plan_digest)
        streams: list[BinaryIO] = []
        try:
            for path in paths:
                streams.append(path.open("rb"))
            yield tuple(streams)
        finally:
            for stream in reversed(streams):
                stream.close()


__all__ = ["WeightShardStoreError", "WeightShardStore"]
