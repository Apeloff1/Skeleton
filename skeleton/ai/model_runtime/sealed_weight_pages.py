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
from typing import Iterator

from .flgb_model_runtime import ModelIdentity
from .weight_shard_store import WeightShardStore, WeightShardStoreError

_CHUNK = 1024 * 1024


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
def open_sealed_weight_pages(
    store: WeightShardStore,
    plan_digest: str,
    *,
    model_identity: ModelIdentity,
    max_bytes: int,
) -> Iterator[tuple[mmap.mmap, ...]]:
    """Copy verified shard bytes into F_SEAL_WRITE memfds, then map read-only.

    Every copied byte is hashed again after the source stream is opened, closing
    the verify/open race. No page is yielded until all shards are sealed.
    """
    if not isinstance(store, WeightShardStore):
        raise SealedWeightPagesError("canonical WeightShardStore required")
    if not isinstance(model_identity, ModelIdentity):
        raise SealedWeightPagesError("explicit canonical model identity required")
    if type(max_bytes) is not int or not 1 <= max_bytes < 1 << 63:
        raise SealedWeightPagesError("positive bounded shared-page budget required")
    plan = store.load_plan(plan_digest)
    if plan.model_identity_digest != model_identity.identity_digest:
        raise SealedWeightPagesError("model identity differs from committed weight plan")
    if plan.expected_total_bytes > max_bytes:
        raise SealedWeightPagesError("shared-page request exceeds explicit memory budget")
    fcntl, flags, seals = _require_sealing()
    fds: list[int] = []
    pages: list[mmap.mmap] = []
    try:
        with store.open_verified(plan_digest, model_identity=model_identity) as streams:
            if len(streams) != len(plan.shards):
                raise SealedWeightPagesError("weight shard count mismatch")
            for shard, stream in zip(plan.shards, streams):
                fd = os.memfd_create("skeleton-local-weights", flags=flags)
                fds.append(fd)
                digest = sha256()
                total = 0
                while True:
                    block = stream.read(min(_CHUNK, shard.bytes - total + 1))
                    if not block:
                        break
                    total += len(block)
                    if total > shard.bytes:
                        raise SealedWeightPagesError("weight source exceeded committed shard size")
                    digest.update(block)
                    _write_all(fd, block)
                if total != shard.bytes or digest.hexdigest() != shard.digest:
                    raise SealedWeightPagesError("weight bytes changed after verification")
                if os.fstat(fd).st_size != shard.bytes:
                    raise SealedWeightPagesError("memfd byte count mismatch")
                fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
                observed = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
                if observed & seals != seals:
                    raise SealedWeightPagesError("kernel did not apply immutable page seals")
                pages.append(mmap.mmap(fd, shard.bytes, access=mmap.ACCESS_READ))
        yield tuple(pages)
    except OSError as exc:
        raise SealedWeightPagesError("OS-backed sealed memory unavailable") from exc
    finally:
        for page in reversed(pages):
            page.close()
        for fd in reversed(fds):
            os.close(fd)


__all__ = ["SealedWeightPagesError", "open_sealed_weight_pages"]
