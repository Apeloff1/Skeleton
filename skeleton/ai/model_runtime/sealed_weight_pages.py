"""Linux sealed read-only shared memory for verified local model weight shards.

This is a bounded ephemeral view of existing canonical WeightShardStore bytes,
not a second weight authority, GPU placement policy or persistent checkpoint.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import mmap
import os
import sys
from typing import Callable, Iterator

from .flgb_model_runtime import ModelIdentity
from .weight_shard_store import WeightShardStore, WeightShardStoreError

_CHUNK = 1024 * 1024
_PROGRESS_QUANTUM = 64 * _CHUNK


class SealedWeightPagesError(WeightShardStoreError):
    """OS-backed immutable pages are unsupported or could not be verified."""


def _require_sealing() -> tuple[object, int, int]:
    if not sys.platform.startswith("linux") or not hasattr(os, "memfd_create"):
        raise SealedWeightPagesError("Linux memfd sealing unavailable")
    try:
        import fcntl
    except ImportError as exc:
        raise SealedWeightPagesError("Linux sealing API unavailable") from exc
    names = ("F_ADD_SEALS", "F_GET_SEALS", "F_SEAL_SEAL", "F_SEAL_SHRINK", "F_SEAL_GROW", "F_SEAL_WRITE")
    if any(not hasattr(fcntl, name) for name in names):
        raise SealedWeightPagesError("kernel sealing constants unavailable")
    flags = getattr(os, "MFD_CLOEXEC", None)
    allow = getattr(os, "MFD_ALLOW_SEALING", None)
    if type(flags) is not int or type(allow) is not int:
        raise SealedWeightPagesError("memfd sealing flags unavailable")
    return fcntl, flags | allow, (
        fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE
    )


def _write_all(fd: int, block: bytes) -> None:
    remaining = memoryview(block)
    while remaining:
        count = os.write(fd, remaining)
        if count <= 0:
            raise SealedWeightPagesError("memfd write made no progress")
        remaining = remaining[count:]


@contextmanager
def _open_sealed_weight_pages(
    store: WeightShardStore,
    plan_digest: str,
    *,
    model_identity: ModelIdentity,
    max_bytes: int,
    progress_check: Callable[[int, int], None] | None = None,
    expected_manifest_sha256: str | None = None,
    max_mappings: int = 256,
) -> Iterator[tuple[mmap.mmap, ...]]:
    """Copy verified shard bytes into F_SEAL_WRITE memfds, then map read-only.

    Every copied byte is hashed directly from the owned source descriptor,
    rather than trusting a separate pathname verification. No page is yielded until all shards are sealed.
    """
    if not isinstance(store, WeightShardStore):
        raise SealedWeightPagesError("canonical WeightShardStore required")
    if not isinstance(model_identity, ModelIdentity):
        raise SealedWeightPagesError("explicit canonical model identity required")
    if type(max_bytes) is not int or not 1 <= max_bytes < 1 << 63:
        raise SealedWeightPagesError("positive bounded shared-page budget required")
    if type(max_mappings) is not int or not 1 <= max_mappings <= 4096:
        raise SealedWeightPagesError("invalid sealed mapping ceiling")
    try:
        plan, manifest_sha, manifest_size = store.bound_model_manifest(
            plan_digest, model_identity=model_identity,
            expected_manifest_sha256=expected_manifest_sha256,
        )
    except WeightShardStoreError as exc:
        raise SealedWeightPagesError("sealed source model or manifest identity unavailable") from exc
    if plan.expected_total_bytes > max_bytes:
        raise SealedWeightPagesError("shared-page request exceeds explicit memory budget")
    if len(plan.shards) > max_mappings:
        raise SealedWeightPagesError("shared-page request exceeds mapping ceiling")
    if progress_check is not None and not callable(progress_check):
        raise SealedWeightPagesError("invalid sealed copy progress callback")
    fcntl, flags, seals = _require_sealing()
    pages: list[mmap.mmap] = []
    copied = 0
    last_check = 0
    try:
        if progress_check is not None:
            progress_check(0, plan.expected_total_bytes)
        # Sequential source ownership avoids opening every shard at once or
        # hashing it twice. The byte-for-byte copy itself is the verification.
        # No mapping escapes until the entire plan and manifest are checked.
        for shard in plan.shards:
            with store._object_reader(shard) as stream:
                fd = os.memfd_create("skeleton-local-weights", flags=flags)
                try:
                    digest = sha256()
                    total = 0
                    while True:
                        if progress_check is not None and copied - last_check >= _PROGRESS_QUANTUM:
                            progress_check(copied, plan.expected_total_bytes)
                            last_check = copied
                        block = stream.read(min(_CHUNK, shard.bytes - total + 1))
                        if not block:
                            break
                        total += len(block)
                        if total > shard.bytes:
                            raise SealedWeightPagesError("weight source exceeded committed shard size")
                        if progress_check is not None and copied + len(block) - last_check > _PROGRESS_QUANTUM:
                            progress_check(copied, plan.expected_total_bytes)
                            last_check = copied
                        digest.update(block)
                        _write_all(fd, block)
                        copied += len(block)
                    if total != shard.bytes or digest.hexdigest() != shard.digest:
                        raise SealedWeightPagesError("weight bytes changed after verification")
                    if os.fstat(fd).st_size != shard.bytes:
                        raise SealedWeightPagesError("memfd byte count mismatch")
                    fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
                    observed = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
                    if observed & seals != seals:
                        raise SealedWeightPagesError("kernel did not apply immutable page seals")
                    pages.append(mmap.mmap(fd, shard.bytes, access=mmap.ACCESS_READ))
                finally:
                    # mmap owns its mapping lifetime independently of the
                    # original memfd. Python may retain a duplicate handle.
                    os.close(fd)
        if copied != plan.expected_total_bytes:
            raise SealedWeightPagesError("sealed copy total differs from plan")
        if progress_check is not None and last_check != copied:
            progress_check(copied, plan.expected_total_bytes)
        _, final_sha, final_size = store.manifest_evidence(plan_digest, maximum=manifest_size)
        if final_sha != manifest_sha or final_size != manifest_size:
            raise SealedWeightPagesError("weight manifest identity changed during sealed copy")
        yield tuple(pages)
    except OSError as exc:
        raise SealedWeightPagesError("OS-backed sealed memory unavailable") from exc
    finally:
        # A consumer may incorrectly retain an exported memoryview. That
        # mapping cannot be forcibly closed, but every other mapping and
        # original descriptor must still be cleaned up.
        failures = []
        for page in reversed(pages):
            try:
                page.close()
            except (BufferError, OSError, ValueError) as exc:
                failures.append(exc)
        if failures:
            raise SealedWeightPagesError("sealed page cleanup remains incomplete") from failures[0]


@contextmanager
def open_sealed_weight_pages(
    store: WeightShardStore, plan_digest: str, *, model_identity: ModelIdentity,
    max_bytes: int, progress_check: Callable[[int, int], None] | None = None,
    expected_manifest_sha256: str | None = None, max_mappings: int = 256,
) -> Iterator[tuple[mmap.mmap, ...]]:
    """Guard managed source bytes through the synchronous sealed consumer."""
    from .managed_weight_read import managed_weight_read

    with managed_weight_read(store):
        with _open_sealed_weight_pages(
            store, plan_digest, model_identity=model_identity, max_bytes=max_bytes,
            progress_check=progress_check, expected_manifest_sha256=expected_manifest_sha256,
            max_mappings=max_mappings,
        ) as pages:
            yield pages


__all__ = ["SealedWeightPagesError", "open_sealed_weight_pages"]
