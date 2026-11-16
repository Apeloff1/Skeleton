"""Bounded CPU source custody using the recovered Linux sealed-page owner.

A private, operator-controlled process must own the store and this context.
The pages are not tensors or proof of an initialized inference backend.
No unsealed fallback is permitted.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import time
from typing import Iterator, Any

from skeleton.ai.model_runtime.flgb_model_runtime import ModelIdentity
from skeleton.ai.model_runtime.weight_shard_store import WeightShardStore
from skeleton.app.offline_runtime_preflight import (
    RuntimePolicy, digest, inspect_source, integer, plan_preflight, require,
    sample_hardware,
)


@contextmanager
def sealed_cpu_custody(store_path: Path, *, plan_digest: str, model: ModelIdentity,
                       policy: RuntimePolicy, maximum_sealed_bytes: int,
                       maximum_mappings: int = 256) -> Iterator[tuple[tuple[Any, ...], dict]]:
    """Pin exact bytes for a synchronous trusted consumer.

    Before copying, reserve room for the entire sealed copy separately
    from the model placement and worker headroom. This is deliberately
    conservative because opening the source can also populate page cache.
    Fresh physical evidence is sampled after copying, prior to publication.
    The native owner rehashes bytes as it copies them and applies OS seals.
    """
    require(isinstance(model, ModelIdentity) and isinstance(policy, RuntimePolicy),
            "canonical model identity and runtime policy required")
    require(policy.backend == "cpu", "sealed CPU custody does not qualify GPU placement")
    maximum = integer(maximum_sealed_bytes, 1, policy.maximum_source_bytes, "sealed byte ceiling")
    mapping_limit = integer(maximum_mappings, 1, 4096, "sealed mapping ceiling")
    source = inspect_source(store_path, plan_digest=plan_digest,
                            model_identity_digest=model.identity_digest, policy=policy)
    size = source.plan.expected_total_bytes
    require(source.manifest_sha256 is not None, "selected manifest pin required for sealed custody")
    require(size <= maximum, "selected model exceeds sealed page budget")
    require(len(source.plan.shards) <= mapping_limit, "selected model exceeds sealed mapping ceiling")
    copying_policy = replace(policy, host_reserve_bytes=policy.host_reserve_bytes + size)
    before = sample_hardware()
    require(before.origin == "local_probe", "real local probe required for sealed custody")
    first = plan_preflight(source, before, copying_policy, now_ns=time.monotonic_ns())
    require(first["status"] == "candidate", "insufficient headroom for sealed copy")
    store = WeightShardStore(store_path, maximum_bytes=policy.maximum_source_bytes, read_only=True)
    checks = 0
    last_copied = 0
    last_digest = None

    def checkpoint(copied: int, total: int) -> None:
        nonlocal checks, last_copied, last_digest
        require(type(total) is int and total == size, "sealed copy total changed")
        integer(copied, last_copied, size, "sealed copy progress")
        remaining = size - copied
        # Previously allocated pages may already appear in the measured
        # usage. Charge outstanding sealed-copy bytes, not those twice.
        # Still preserve separate downstream model/worker placement headroom.
        outstanding = replace(policy, host_reserve_bytes=policy.host_reserve_bytes + remaining)
        observation = sample_hardware()
        require(observation.origin == "local_probe", "real local probe required during sealed copy")
        check = plan_preflight(source, observation, outstanding, now_ns=time.monotonic_ns())
        require(check["status"] == "candidate", "resource pressure during sealed copy")
        last_copied = copied
        last_digest = check["preflight_digest"]
        checks += 1

    with store.open_sealed_pages(plan_digest, model_identity=model, max_bytes=maximum,
                                 progress_check=checkpoint, expected_manifest_sha256=source.manifest_sha256,
                                 max_mappings=mapping_limit) as pages:
        require(last_copied == size and checks >= 2 and last_digest is not None,
                "sealed copy did not complete resource checkpoints")
        require(len(pages) == len(source.plan.shards) and
                all(len(page) == shard.bytes for page, shard in zip(pages, source.plan.shards)),
                "sealed page count or size drift")
        after = sample_hardware()
        require(after.origin == "local_probe", "real local probe required after sealing")
        second = plan_preflight(source, after, policy, now_ns=time.monotonic_ns())
        require(second["status"] == "candidate", "resource pressure after sealed copy")
        body = {"schema": "skeleton.offline.sealed-custody.v1",
                "source_digest": digest(source.snapshot()), "plan_digest": plan_digest,
                "model_identity_digest": model.identity_digest, "sealed_bytes": size,
                "manifest_sha256": source.manifest_sha256, "maximum_mappings": mapping_limit,
                "shard_count": len(pages), "before_digest": first["preflight_digest"],
                "after_digest": second["preflight_digest"],
                "copy_checks": checks, "final_copy_check_digest": last_digest,
                "custody": "linux_sealed_read_only_pages",
                "tensor_validation": "not_assessed", "native_qualified": False,
                "release_qualified": False}
        yield pages, {**body, "custody_digest": digest(body)}
