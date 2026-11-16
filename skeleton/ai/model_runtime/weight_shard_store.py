"""Content-addressed, bounded binary shard storage for model and shadow weights.

A WeightLoadPlan is a contract, not proof that any bytes were loaded. This
store streams source files into immutable SHA-256 objects and admits a manifest
only after the physical content, order and byte counts match the plan.
Decoding, tensor shape validation and GPU placement remain the model loader's
responsibility; shadow bytes never become production weights implicitly.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from hashlib import sha256
import json
import os
import stat
from pathlib import Path
from typing import BinaryIO, Callable, Iterator, Mapping
from uuid import uuid4

from .flgb_model_runtime import (
    MAX_WEIGHT_BYTES, MAX_WEIGHT_SHARDS, ModelIdentity, ModelRuntimeError, WeightLoadPlan,
    WeightShard, canonical_bytes, digest_json, require_digest,
)

_CHUNK_SIZE = 4 * 1024 * 1024
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024


class WeightShardStoreError(ModelRuntimeError):
    """Failure to ingest or read verified native or shadow model bytes."""


def _directory_identity(path: Path) -> tuple[int, int]:
    """Observe a real directory without following its final component."""
    try:
        info = path.lstat()
    except OSError as exc:
        raise WeightShardStoreError("weight store directory unavailable") from exc
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if (not stat.S_ISDIR(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & reparse):
        raise WeightShardStoreError("weight store must use real non-reparse directories")
    return info.st_dev, info.st_ino


def _file_identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


@contextmanager
def _bounded_regular_reader(path: Path, maximum: int) -> Iterator[BinaryIO]:
    """Bound file reads and reject observed name/descriptor identity changes.

    This is portable source inspection, not an immutable descriptor held by
    the eventual model loader. The stronger Linux GGUF and sealed-page owners
    still enforce their own parent custody.
    """
    if type(maximum) is not int or maximum < 1:
        raise WeightShardStoreError("invalid weight read ceiling")
    try:
        named = path.lstat()
        if (not stat.S_ISREG(named.st_mode) or not 0 <= named.st_size <= maximum
                or getattr(named, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise WeightShardStoreError("weight source violates regular-file or byte bounds")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or _file_identity(before) != _file_identity(named):
                raise WeightShardStoreError("weight source changed during open")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                yield stream
                after = os.fstat(fd)
                if (_file_identity(after) != _file_identity(before)
                        or _file_identity(path.lstat()) != _file_identity(before)):
                    raise WeightShardStoreError("weight source changed during inspection")
        finally:
            os.close(fd)
    except OSError as exc:
        raise WeightShardStoreError("weight source unavailable during inspection") from exc


def _read_manifest(path: Path) -> bytes:
    with _bounded_regular_reader(path, _MAX_MANIFEST_BYTES) as stream:
        raw = stream.read(_MAX_MANIFEST_BYTES + 1)
        if not raw or len(raw) > _MAX_MANIFEST_BYTES:
            raise WeightShardStoreError("weight manifest exceeds byte bounds")
        return raw


def _hash_stream(stream: BinaryIO, *, maximum: int) -> tuple[str, int]:
    digest = sha256()
    size = 0
    while True:
        chunk = stream.read(min(_CHUNK_SIZE, maximum - size + 1))
        if not chunk:
            break
        size += len(chunk)
        if size > maximum:
            raise WeightShardStoreError("weight object exceeds manifest byte budget")
        digest.update(chunk)
    return digest.hexdigest(), size


def _hash_file(path: Path, *, maximum: int) -> tuple[str, int]:
    with _bounded_regular_reader(path, maximum) as stream:
        return _hash_stream(stream, maximum=maximum)


class WeightShardStore:
    """Immutable CAS with deterministic manifests and bounded stream memory."""

    def __init__(self, directory: str | Path, *, maximum_bytes: int = MAX_WEIGHT_BYTES,
                 read_only: bool = False) -> None:
        if isinstance(maximum_bytes, bool) or not isinstance(maximum_bytes, int) or not 1 <= maximum_bytes <= MAX_WEIGHT_BYTES:
            raise WeightShardStoreError("invalid weight-storage budget")
        if type(read_only) is not bool:
            raise WeightShardStoreError("read-only store selection must be boolean")
        self.root = Path(directory).absolute()
        self.objects = self.root / "objects"
        self.manifests = self.root / "manifests"
        self._read_only = read_only
        # Refuse an existing link before creating any managed child. A
        # read-only opening never invokes mkdir, even for a missing layout.
        self._layout = {}
        for path in (self.root, self.objects, self.manifests):
            if not read_only:
                try:
                    path.mkdir(mode=0o700, parents=path == self.root, exist_ok=True)
                except OSError as exc:
                    raise WeightShardStoreError("weight store layout unavailable") from exc
            self._layout[path] = _directory_identity(path)
        self.maximum_bytes = maximum_bytes

    def assert_layout(self) -> None:
        """Reject observed managed-directory replacement since opening.

        These are identity checks under the trusted store owner, not
        protection against arbitrary ancestor replacement between syscalls.
        """
        for path, expected in self._layout.items():
            if _directory_identity(path) != expected:
                raise WeightShardStoreError("weight store directory identity changed")

    def _require_write(self) -> None:
        if self._read_only:
            raise WeightShardStoreError("read-only weight store cannot stage weights")
        self.assert_layout()

    def _object_path(self, digest: str) -> Path:
        require_digest(digest, "weight_object_digest")
        self.assert_layout()
        bucket = self.objects / digest[:2]
        if bucket.exists() or bucket.is_symlink():
            _directory_identity(bucket)
        return bucket / digest

    @contextmanager
    def _object_reader(self, shard: WeightShard) -> Iterator[BinaryIO]:
        path = self._object_path(shard.digest)
        bucket = _directory_identity(path.parent)
        with _bounded_regular_reader(path, shard.bytes) as stream:
            self.assert_layout()
            if _directory_identity(path.parent) != bucket:
                raise WeightShardStoreError("weight object bucket identity changed")
            yield stream
        self.assert_layout()
        if _directory_identity(path.parent) != bucket:
            raise WeightShardStoreError("weight object bucket identity changed")

    def _manifest_path(self, digest: str) -> Path:
        require_digest(digest, "weight_manifest_digest")
        self.assert_layout()
        return self.manifests / (digest + ".json")

    @staticmethod
    def _write_once(path: Path, content: bytes) -> None:
        if not 1 <= len(content) <= _MAX_MANIFEST_BYTES:
            raise WeightShardStoreError("weight manifest exceeds byte bounds")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink():
            raise WeightShardStoreError("content-addressed path must not be a symlink")
        if path.exists():
            if _read_manifest(path) != content:
                raise WeightShardStoreError("existing content-addressed manifest is inconsistent")
            return
        tmp = path.with_name("." + path.name + "." + uuid4().hex + ".tmp")
        try:
            with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            # Hard-link creation is atomic and never replaces an existing
            # path. An os.replace race would silently rewrite immutable CAS.
            try:
                os.link(tmp, path)
            except FileExistsError:
                if _read_manifest(path) != content:
                    raise WeightShardStoreError("concurrent manifest content mismatch")
            else:
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
        target.parent.mkdir(mode=0o700, exist_ok=True)
        _directory_identity(target.parent)
        self.assert_layout()
        if target.is_symlink():
            raise WeightShardStoreError("stored weight object must not be a symlink")
        if target.exists():
            observed, size = _hash_file(target, maximum=shard.bytes)
            if observed != shard.digest or size != shard.bytes:
                raise WeightShardStoreError("existing weight object failed content identity")
            return target

        tmp = target.with_name("." + target.name + "." + uuid4().hex + ".tmp")
        try:
            digest = sha256()
            size = 0
            with _bounded_regular_reader(path, shard.bytes) as reader, os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as writer:
                while True:
                    block = reader.read(min(_CHUNK_SIZE, shard.bytes - size + 1))
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
            try:
                os.link(tmp, target)
            except FileExistsError:
                observed, stored_size = _hash_file(target, maximum=shard.bytes)
                if observed != shard.digest or stored_size != shard.bytes:
                    raise WeightShardStoreError("concurrent weight object mismatch")
            else:
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
        self._require_write()
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
        self.assert_layout()
        self._write_once(self._manifest_path(plan.digest), canonical_bytes(manifest))
        self.assert_layout()
        return plan.digest

    def _load_plan_manifest(self, plan_digest: str) -> tuple[WeightLoadPlan, dict]:
        """Reconstruct a plan and its identity fields from one bounded read."""
        path = self._manifest_path(plan_digest)
        try:
            raw = _read_manifest(path)
            manifest = json.loads(raw)
        except (OSError, ValueError, RecursionError) as exc:
            raise WeightShardStoreError("weight plan manifest unavailable") from exc
        if not isinstance(manifest, dict) or set(manifest) != {
            "schema_version", "model_identity_digest", "weights_digest",
            "plan_digest", "expected_total_bytes", "shards",
        } or manifest["schema_version"] != 1:
            raise WeightShardStoreError("weight manifest schema mismatch")
        if (type(manifest["schema_version"]) is not int
                or type(manifest["shards"]) is not list
                or not 1 <= len(manifest["shards"]) <= MAX_WEIGHT_SHARDS):
            raise WeightShardStoreError("invalid weight manifest shard declaration")
        if any(type(row) is not dict or set(row) != {"index", "digest", "bytes", "source"}
               for row in manifest["shards"]):
            raise WeightShardStoreError("invalid weight manifest shard fields")
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
        self.assert_layout()
        return plan, manifest

    def load_plan(self, plan_digest: str) -> WeightLoadPlan:
        """Reconstruct a committed plan without trusting caller-supplied paths."""
        return self._load_plan_manifest(plan_digest)[0]

    def verified_paths(self, plan_digest: str) -> tuple[Path, ...]:
        """Return only shards that still match their immutable content identity."""
        plan = self.load_plan(plan_digest)
        paths = []
        for shard in plan.shards:
            path = self._object_path(shard.digest)
            try:
                with self._object_reader(shard) as stream:
                    digest, count = _hash_stream(stream, maximum=shard.bytes)
            except OSError as exc:
                raise WeightShardStoreError("referenced weight object is unavailable") from exc
            if digest != shard.digest or count != shard.bytes:
                raise WeightShardStoreError("stored weight object changed since admission")
            paths.append(path)
        self.assert_layout()
        return tuple(paths)

    @contextmanager
    def open_sealed_pages(
        self, plan_digest: str, *, model_identity: ModelIdentity, max_bytes: int,
        progress_check: Callable[[int, int], None] | None = None,
    ) -> Iterator[tuple[object, ...]]:
        """Publish Linux read-only shared pages only after full shard verification."""
        from .sealed_weight_pages import open_sealed_weight_pages

        with open_sealed_weight_pages(
            self, plan_digest, model_identity=model_identity, max_bytes=max_bytes,
            progress_check=progress_check,
        ) as pages:
            yield pages

    @contextmanager
    def open_verified(
        self, plan_digest: str, *, model_identity: ModelIdentity,
    ) -> Iterator[tuple[BinaryIO, ...]]:
        """Open verified, ordered shard streams for an explicit model decoder."""
        if not isinstance(model_identity, ModelIdentity):
            raise WeightShardStoreError("model identity required for weight loading")
        plan, data = self._load_plan_manifest(plan_digest)
        if plan.model_identity_digest != model_identity.identity_digest:
            raise WeightShardStoreError("requested model is not bound to this weight plan")
        if data["weights_digest"] != model_identity.weights_digest:
            raise WeightShardStoreError("weights identity mismatch")
        # Verify the actual streams delivered to the decoder rather than
        # hashing a pathname, closing it, then reopening an unverified file.
        # The sealed-memory owner still hashes during its own immutable copy;
        # ordinary streams do not prevent concurrent writes by the store owner.
        with ExitStack() as stack:
            streams: list[BinaryIO] = []
            for shard in plan.shards:
                stream = stack.enter_context(
                    self._object_reader(shard)
                )
                observed, size = _hash_stream(stream, maximum=shard.bytes)
                if observed != shard.digest or size != shard.bytes:
                    raise WeightShardStoreError("stored weight object changed since admission")
                stream.seek(0)
                streams.append(stream)
            self.assert_layout()
            yield tuple(streams)
            self.assert_layout()


__all__ = ["WeightShardStoreError", "WeightShardStore"]
