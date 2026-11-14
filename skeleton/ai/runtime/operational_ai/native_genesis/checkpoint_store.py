"""POSIX descriptor-bound, private and immutable native genesis checkpoint store."""
from __future__ import annotations
from pathlib import Path
import os
import stat
import hashlib

from .canonical import bytes_sha, required_sha, encode
from .errors import refuse
from ..model.gguf.file_guard import open_trusted_root, regular_beneath


def _open_private_root(directory: Path) -> int:
    if type(directory) is not Path or not directory.is_absolute():
        refuse("store-absolute-directory")
    try:
        root = open_trusted_root(directory)
    except (OSError, ValueError):
        refuse("store-untrusted-directory")
    metadata = os.fstat(root)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_mode & 0o077:
        os.close(root)
        refuse("store-private-only")
    if metadata.st_uid != os.geteuid():
        os.close(root)
        refuse("store-owner-mismatch")
    return root


def _write_exclusive(root: int, leaf: str, content: bytes) -> None:
    child = os.open(
        leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
        os.O_CLOEXEC, 0o600, dir_fd=root,
    )
    try:
        with os.fdopen(child, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.unlink(leaf, dir_fd=root)
        except OSError:
            pass
        raise


def publish_genesis(directory: Path, genesis, *, refuse_existing: bool = True) -> dict:
    from .factory import GenesisInstance
    from .manifest import from_instance
    if type(genesis) is not GenesisInstance or refuse_existing is not True:
        refuse("genesis-exclusive-publication")
    manifest = from_instance(genesis)
    raw = genesis.checkpoint
    if not 1 <= len(raw) <= genesis.policy.maximum_model_bytes:
        refuse("genesis-output-budget")
    if bytes_sha(raw) != manifest.checkpoint_sha256:
        refuse("genesis-checkpoint-mismatch")
    directory.mkdir(mode=0o700, parents=False, exist_ok=True)
    root = _open_private_root(directory)
    try:
        checkpoint_leaf = manifest.checkpoint_sha256 + ".native.json"
        manifest_leaf = manifest.checkpoint_sha256 + ".manifest.json"
        raw_manifest = encode(manifest.record())
        # Check both names before writing any; uncertain previous writes fail.
        for leaf in (checkpoint_leaf, manifest_leaf):
            try:
                os.stat(leaf, dir_fd=root, follow_symlinks=False)
            except FileNotFoundError:
                continue
            refuse("genesis-path-already-exists")
        _write_exclusive(root, checkpoint_leaf, raw)
        try:
            _write_exclusive(root, manifest_leaf, raw_manifest)
            os.fsync(root)
        except BaseException:
            # A partial publication must remain held; operator must audit it.
            # Do not silently overwrite existing checkpoint on retry.
            raise
        return {
            "schema": "skeleton.native-genesis.publication.v1",
            "checkpoint_path": str(directory / checkpoint_leaf),
            "manifest_path": str(directory / manifest_leaf),
            "checkpoint_sha256": manifest.checkpoint_sha256,
            "manifest_sha256": bytes_sha(raw_manifest),
            "model_sha256": manifest.model_sha256,
            "tokenizer_sha256": manifest.tokenizer_sha256,
            "candidate_only": True, "release_certified": False,
        }
    finally:
        os.close(root)


def read_verified(directory: Path, expected_checkpoint_sha256: str, *,
                  byte_ceiling: int = 256_000_000) -> bytes:
    required_sha(expected_checkpoint_sha256, "checkpoint")
    if type(byte_ceiling) is not int or not 1 <= byte_ceiling <= 256_000_000:
        refuse("checkpoint-byte-ceiling")
    root = _open_private_root(directory)
    try:
        leaf = expected_checkpoint_sha256 + ".native.json"
        stat_info = os.stat(leaf, dir_fd=root, follow_symlinks=False)
        if stat_info.st_size < 1 or stat_info.st_size > byte_ceiling:
            refuse("checkpoint-file-budget")
        digest = hashlib.sha256()
        parts = []
        with regular_beneath(root, leaf, stat_info.st_size) as child:
            remaining = stat_info.st_size
            while remaining:
                block = os.read(child, min(65536, remaining))
                if not block:
                    refuse("checkpoint-short-read")
                parts.append(block)
                digest.update(block)
                remaining -= len(block)
            if os.read(child, 1):
                refuse("checkpoint-extra-bytes")
        if digest.hexdigest() != expected_checkpoint_sha256:
            refuse("checkpoint-hash-mismatch")
        return b"".join(parts)
    finally:
        os.close(root)
