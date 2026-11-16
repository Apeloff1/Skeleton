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
                       policy: RuntimePolicy, maximum_sealed_bytes: int) -> Iterator[tuple[tuple[Any, ...], dict]]:
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
    source = inspect_source(store_path, plan_digest=plan_digest,
                            model_identity_digest=model.identity_digest, policy=policy)
    size = source.plan.expected_total_bytes
    require(size <= maximum, "selected model exceeds sealed page budget")
    copying_policy = replace(policy, host_reserve_bytes=policy.host_reserve_bytes + size)
    before = sample_hardware()
    require(before.origin == "local_probe", "real local probe required for sealed custody")
    first = plan_preflight(source, before, copying_policy, now_ns=time.monotonic_ns())
    require(first["status"] == "candidate", "insufficient headroom for sealed copy")
    store = WeightShardStore(store_path, maximum_bytes=policy.maximum_source_bytes)
    with store.open_sealed_pages(plan_digest, model_identity=model, max_bytes=maximum) as pages:
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
                "shard_count": len(pages), "before_digest": first["preflight_digest"],
                "after_digest": second["preflight_digest"],
                "custody": "linux_sealed_read_only_pages",
                "tensor_validation": "not_assessed", "native_qualified": False,
                "release_qualified": False}
        yield pages, {**body, "custody_digest": digest(body)}
