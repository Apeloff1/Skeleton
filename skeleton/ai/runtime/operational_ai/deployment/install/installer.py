"""One-pass, bounded, descriptor-anchored model installer from ordered tar bundles.

The archived source code is *not executed*. Archive entries are digested as
received, the canonical final inventory is checked against observed bytes,
and approved GGUF shards are staged beneath a private directory. Only after
all archive and GGUF manifest constraints succeed is the directory published
with a no-clobber same-directory rename. A failed install leaves no
partial published model. This is content integrity, not trust in the signer.

This module deliberately does not unpack code, run pip, invoke shell utilities,
or download weights. The operator must independently trust the provenance of
this content. Model inference remains a separate, explicitly gated operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from contextlib import contextmanager
import ctypes
from typing import BinaryIO, Iterator, Mapping
import hashlib
import io
import json
import os
import secrets
import stat
import tarfile

from ...model.gguf.file_guard import open_trusted_root
from ...model.gguf.manifest import GGUFManifestError, load_manifest

BLOCK = 1024 * 1024
MAX_ARCHIVE = 2_000_000_000
MAX_FILES = 200_000
MAX_MODEL_FILES = 80
MAX_PAYLOAD_FILE = 99_000_000
MAX_MANIFEST = 40 * 1024 * 1024
PREFIX = "bundle/stages/MBW-02/payload/models/"
FINAL = "bundle/manifest.json"
WAVES = tuple(f"MBW-{i:02d}" for i in range(8))
ZERO = "0" * 64


class InstallError(RuntimeError):
    """Fail-closed archive/IO/identity/authorization boundary."""


@dataclass(frozen=True, slots=True)
class InstallReceipt:
    model_id: str
    model_sha256: str
    manifest_sha256: str
    source_sha: str
    archive_sha256: str
    archive_bytes: int
    verified_entries: int
    installed_files: int
    installed_bytes: int
    destination: str
    status: str = "integrity-verified-not-release-certified"

    def to_record(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


def _valid_name(name: object) -> str:
    if (not isinstance(name, str) or not 1 <= len(name) <= 100
        or not name[0].isalnum() or not name.isascii()
        or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for c in name)
        or name in {".", ".."}):
        raise InstallError("invalid model or install identifier")
    return name


def _valid_path(path: str) -> list[str]:
    if (not isinstance(path, str) or not 1 <= len(path) <= 700
        or path.startswith("-") or path.startswith("/")
        or "\\" in path or any(ord(c) < 32 or ord(c) == 127 for c in path)):
        raise InstallError("unsafe archive member path")
    parts = path.split("/")
    if (any(x in ("", ".", "..") for x in parts)
        or str(PurePosixPath(path)) != path):
        raise InstallError("noncanonical archive member path")
    return parts


def _json_object(raw: bytes, *, maximum: int) -> dict:
    if not 0 < len(raw) <= maximum:
        raise InstallError("manifest size outside limit")
    def pairs(rows):
        out = {}
        for k, value in rows:
            if k in out:
                raise InstallError("duplicate manifest key")
            out[k] = value
        return out
    def no_constant(v):
        raise InstallError("non-finite JSON number")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=no_constant)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise InstallError("invalid canonical manifest") from exc
    if not isinstance(value, dict):
        raise InstallError("manifest must be a JSON object")
    canonical = (json.dumps(value, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")) + "\n").encode("utf-8")
    if canonical != raw:
        raise InstallError("manifest is not in canonical archive encoding")
    return value


def _read_exact(source: BinaryIO, total: int, target: int | None = None, sink=None) -> str:
    digest = hashlib.sha256()
    remaining = total
    while remaining:
        chunk = source.read(min(BLOCK, remaining))
        if not chunk:
            raise InstallError("archive truncated within a file")
        digest.update(chunk)
        if sink is not None:
            view = memoryview(chunk)
            while view:
                written = os.write(sink, view)
                if written <= 0:
                    raise InstallError("model staging write failed")
                view = view[written:]
        remaining -= len(chunk)
    if target is not None and total != target:
        raise InstallError("declared file size changed")
    return digest.hexdigest()


def _trusted_archive(path: Path) -> tuple[BinaryIO, int]:
    # Descriptor anchors the object throughout the verification pass.
    p = path.absolute()
    parent_fd = open_trusted_root(p.parent)
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(p.name, flags, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or not 1 <= s.st_size <= MAX_ARCHIVE:
            raise InstallError("archive is not a bounded regular file")
        return os.fdopen(fd, "rb", buffering=0), s.st_size
    except BaseException:
        os.close(fd)
        raise


def _mkdir_at(parent: int, name: str) -> int:
    os.mkdir(name, mode=0o700, dir_fd=parent)
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    if os.fstat(fd).st_mode & 0o077:
        os.close(fd)
        raise InstallError("private staging directory permissions drifted")
    return fd


def _remove_staging(parent_fd: int, name: str) -> None:
    """Delete only our freshly-created directory tree through anchored fds."""
    try:
        directory_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                               dir_fd=parent_fd)
    except FileNotFoundError:
        return
    def remove_contents(fd: int) -> None:
        for entry in os.listdir(fd):
            info = os.stat(entry, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISREG(info.st_mode):
                os.unlink(entry, dir_fd=fd)
            elif stat.S_ISDIR(info.st_mode):
                child = os.open(entry, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    remove_contents(child)
                finally:
                    os.close(child)
                os.rmdir(entry, dir_fd=fd)
            else:
                raise InstallError("unexpected staging entry type")
    try:
        remove_contents(directory_fd)
    finally:
        os.close(directory_fd)
    os.rmdir(name, dir_fd=parent_fd)


def _verify_inventory(manifest: dict, observed: list[dict], *, model_id: str,
                      model_names: dict[str, tuple[int, str]]) -> tuple[str, str]:
    if (manifest.get("schema_version") != 1 or manifest.get("package") != "skeleton-ai-ecosystem"
        or manifest.get("status") != "content-only-no-release-attestation"):
        raise InstallError("invalid archive identity, schema or release hold")
    records = manifest.get("entries")
    if not isinstance(records, list) or len(records) != len(observed):
        raise InstallError("archive inventory has missing or extra entries")
    for expected, actual in zip(records, observed):
        if (not isinstance(expected, dict)
            or any(expected.get(key) != val for key, val in actual.items())):
            raise InstallError("archive content digest, order or size drift")
    graph = manifest.get("stage_graph")
    if (not isinstance(graph, list) or len(graph) != 8
        or [x.get("id") for x in graph if isinstance(x, dict)] != list(WAVES)):
        raise InstallError("archive dependency graph absent or reordered")
    for idx, wave in enumerate(graph):
        deps = wave.get("dependencies")
        if not isinstance(deps, list) or any(dep not in WAVES[:idx] for dep in deps):
            raise InstallError("invalid build wave dependency")
    source = sum(x["size"] for x in observed if x["path"].split("/")[3] == "source")
    payload = sum(x["size"] for x in observed if x["path"].split("/")[3] == "payload")
    if manifest.get("source_bytes") != source or manifest.get("approved_artifact_bytes") != payload:
        raise InstallError("archive source and payload byte accounting drift")
    artifacts = {x["path"]: x for x in records if x.get("kind") == "approved_artifact"}
    if not all(path in artifacts for path in model_names):
        raise InstallError("installed model is not declared as approved artifact")
    for path, (size, digest) in model_names.items():
        item = artifacts[path]
        if (item.get("size") != size or item.get("sha256") != digest
            or not isinstance(item.get("license"), str) or not item["license"].strip()
            or not isinstance(item.get("provenance"), str) or not item["provenance"].strip()):
            raise InstallError("model rights or provenance unavailable")
    source_sha = manifest.get("source_sha")
    if not isinstance(source_sha, str) or len(source_sha) not in (40, 64):
        raise InstallError("archive missing source Git commit identity")
    return source_sha, hashlib.sha256((json.dumps(manifest, ensure_ascii=False,
                                  sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()


def _write_staged(root_fd: int, rel: str, src: BinaryIO, length: int) -> str:
    """Create only files underneath private stage fds, rejecting path aliases."""
    parts = _valid_path(rel)
    fd = os.dup(root_fd)
    try:
        for name in parts[:-1]:
            try:
                os.mkdir(name, 0o700, dir_fd=fd)
            except FileExistsError:
                if not stat.S_ISDIR(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                    raise InstallError("staging parent not a directory")
            nxt = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        out = os.open(parts[-1], os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                      0o400, dir_fd=fd)
        try:
            digest = _read_exact(src, length, sink=out)
            os.fsync(out)
        finally:
            os.close(out)
        os.fsync(fd)
        return digest
    finally:
        os.close(fd)


def _verified_model(stage_fd: int, candidates: Mapping[str, tuple[int, str]],
                    manifest_bytes: bytes, model_id: str):
    try:
        manifest = load_manifest(manifest_bytes)
    except GGUFManifestError as exc:
        raise InstallError("installed model inventory is not a valid GGUF manifest") from exc
    if manifest.model_id != model_id:
        raise InstallError("model identity mismatches install selection")
    required = {"model.manifest.json"} | {shard.path for shard in manifest.shards}
    if set(candidates) != required:
        raise InstallError("missing, extra, or shadowed model shard")
    joined = hashlib.sha256()
    total = 0
    for shard in manifest.shards:
        expected_size, expected_hash = candidates[shard.path]
        if expected_size != shard.bytes or expected_hash != shard.sha256:
            raise InstallError("manifest and approved shard metadata differ")
        parts = _valid_path(shard.path)
        fd = os.dup(stage_fd)
        try:
            for part in parts[:-1]:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
            source = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                st = os.fstat(source)
                if not stat.S_ISREG(st.st_mode) or st.st_size != shard.bytes:
                    raise InstallError("staged model shard changed")
                remaining = shard.bytes
                while remaining:
                    data = os.read(source, min(BLOCK, remaining))
                    if not data:
                        raise InstallError("staged model shard truncated")
                    joined.update(data)
                    total += len(data)
                    remaining -= len(data)
                if os.read(source, 1):
                    raise InstallError("staged model shard expanded")
            finally:
                os.close(source)
        finally:
            os.close(fd)
    if total != manifest.total_bytes or joined.hexdigest() != manifest.model_sha256:
        raise InstallError("assembled staged model digest mismatch")
    return manifest


class _HashingStream:
    def __init__(self, source: BinaryIO):
        self.source = source
        self.digest = hashlib.sha256()
        self.size = 0
    def read(self, size: int = -1) -> bytes:
        raw = self.source.read(size)
        self.digest.update(raw)
        self.size += len(raw)
        return raw


def _publish_no_replace(root_fd: int, stage_name: str, destination: str) -> None:
    """Linux renameat2 RENAME_NOREPLACE is required, never os.replace()."""
    lib = ctypes.CDLL(None, use_errno=True)
    try:
        rename = lib.renameat2
    except AttributeError as exc:
        raise InstallError("atomic no-replace publication unavailable") from exc
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                       ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(root_fd, os.fsencode(stage_name), root_fd, os.fsencode(destination), 1) != 0:
        raise InstallError(f"atomic model publication refused (errno={ctypes.get_errno()})")
    os.fsync(root_fd)


def install_approved_model(archive: Path | str, destination_root: Path | str, *,
                           model_id: str, install_id: str,
                           maximum_archive_bytes: int = 1_920_000_000,
                           minimum_archive_bytes: int = 1_880_000_000,
                           minimum_real_bytes: int = 1_850_000_000) -> InstallReceipt:
    """Verify a complete canonical bundle and atomically install one model.

    Production defaults enforce the genuine 1.9 GB artifact envelope. Tests may
    opt into narrower small-fixture bounds. Even a verified install does not
    certify signatures, model behavior, or a device/OS qualification.
    """
    model_id = _valid_name(model_id)
    install_id = _valid_name(install_id)
    if (type(maximum_archive_bytes) is not int or type(minimum_archive_bytes) is not int
        or type(minimum_real_bytes) is not int or not 1 <= minimum_archive_bytes
        <= maximum_archive_bytes <= MAX_ARCHIVE or not 1 <= minimum_real_bytes
        <= maximum_archive_bytes):
        raise InstallError("invalid bounded installation policy")
    root_fd = open_trusted_root(Path(destination_root))
    stage_name = ".staging-" + secrets.token_hex(12)
    stage_fd: int | None = None
    staged = False
    published = False
    try:
        if os.fstat(root_fd).st_mode & 0o077:
            raise InstallError("install root must be private mode 0700")
        try:
            os.stat(install_id, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise InstallError("model install destination already exists")
        stage_fd = _mkdir_at(root_fd, stage_name)
        staged = True
        archive_file, _archive_size = _trusted_archive(Path(archive))
        with archive_file:
            archive_bytes = os.fstat(archive_file.fileno()).st_size
            if not minimum_archive_bytes <= archive_bytes <= maximum_archive_bytes:
                raise InstallError("archive bytes outside approved size window")
            stream = _HashingStream(archive_file)
            observed = []
            model_candidates: dict[str, tuple[int, str]] = {}
            declared: dict[str, tuple[int, str]] = {}
            manifest_bytes = None
            last_wave = -1
            total_real = 0
            with tarfile.open(fileobj=stream, mode="r|") as tf:
                for member in tf:
                    name = member.name
                    _valid_path(name)
                    if not member.isfile() or member.size < 0 or member.size > MAX_PAYLOAD_FILE:
                        raise InstallError("archive member must be bounded regular file")
                    if name in declared or name == FINAL and manifest_bytes is not None:
                        raise InstallError("duplicate archive member")
                    source = tf.extractfile(member)
                    if source is None:
                        raise InstallError("archive member inaccessible")
                    if name == FINAL:
                        if member.size > MAX_MANIFEST:
                            raise InstallError("archive manifest too large")
                        raw = source.read(member.size+1)
                        if len(raw) != member.size:
                            raise InstallError("archive manifest truncated")
                        manifest_bytes = raw
                        continue
                    if manifest_bytes is not None:
                        raise InstallError("manifest must be the final archive member")
                    tokens = name.split("/")
                    if (len(tokens) < 6 or tokens[:2] != ["bundle", "stages"]
                        or tokens[2] not in WAVES or tokens[3] not in ("source", "payload")):
                        raise InstallError("archive member is outside canonical build tree")
                    wave = WAVES.index(tokens[2])
                    if wave < last_wave:
                        raise InstallError("out-of-order build-wave member")
                    last_wave = wave
                    selected = name.startswith(PREFIX + model_id + "/")
                    if name.startswith(PREFIX) and not selected:
                        # Allow multiple models in package but never install them implicitly.
                        selected = False
                    if selected:
                        local = name[len(PREFIX + model_id + "/"):]
                        _valid_path(local)
                        if local in model_candidates or len(model_candidates) >= MAX_MODEL_FILES:
                            raise InstallError("duplicate or excessive selected model files")
                        digest = _write_staged(stage_fd, local, source, member.size)
                        model_candidates[local] = (member.size, digest)
                    else:
                        digest = _read_exact(source, member.size)
                    observed.append({"path": name, "size": member.size, "sha256": digest,
                                     "wave": tokens[2]})
                    declared[name] = (member.size, digest)
                    total_real += member.size
                    if len(observed) > MAX_FILES:
                        raise InstallError("archive member count overflow")
            if manifest_bytes is None:
                raise InstallError("archive missing canonical final manifest")
            manifest = _json_object(manifest_bytes, maximum=MAX_MANIFEST)
            model_path_records = {
                PREFIX + model_id + "/" + key: value for key, value in model_candidates.items()
            }
            source_sha, manifest_sha = _verify_inventory(manifest, observed,
                model_id=model_id, model_names=model_path_records)
            if total_real < minimum_real_bytes:
                raise InstallError("archive real content below operator-approved floor")
            if "model.manifest.json" not in model_candidates:
                raise InstallError("selected model manifest absent")
            mf_fd = os.open("model.manifest.json", os.O_RDONLY | os.O_NOFOLLOW,
                            dir_fd=stage_fd)
            try:
                if os.fstat(mf_fd).st_size > 128_000:
                    raise InstallError("selected GGUF manifest too large")
                manifest_raw = os.read(mf_fd, 128_001)
            finally:
                os.close(mf_fd)
            model = _verified_model(stage_fd, model_candidates, manifest_raw, model_id)
            # Hash the exact archive descriptor bytes, including canonical padding.
            # Refuse appended arbitrary data after the TAR terminator.
            while True:
                remainder = stream.read(BLOCK)
                if not remainder:
                    break
                if any(remainder):
                    raise InstallError("archive has unexpected trailing data")
            if stream.size != archive_bytes:
                raise InstallError("archive size changed while reading")
            st = os.fstat(archive_file.fileno())
            if st.st_size != archive_bytes:
                raise InstallError("archive backing file changed size")
            receipt = InstallReceipt(model_id, model.model_sha256,
                model.manifest_digest, source_sha, stream.digest.hexdigest(),
                archive_bytes, len(observed), len(model_candidates),
                sum(s for s, _ in model_candidates.values()),
                str(Path(destination_root).absolute() / install_id))
        # Permanently bind the model directory to its verified archive and
        # canonical model manifest before publishing. The receipt is data,
        # not an approval signature, and is never inferred from model output.
        receipt_raw = (json.dumps(receipt.to_record(), sort_keys=True,
                                  ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        _write_staged(stage_fd, "install.receipt.json", io.BytesIO(receipt_raw), len(receipt_raw))
        os.fsync(stage_fd)
        _publish_no_replace(root_fd, stage_name, install_id)
        published = True
        return receipt
    except (GGUFManifestError, OSError, ValueError, tarfile.TarError) as exc:
        raise InstallError("model installation refused") from exc
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
        if staged and not published:
            _remove_staging(root_fd, stage_name)
        os.close(root_fd)
