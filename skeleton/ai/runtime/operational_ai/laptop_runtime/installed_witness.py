"""Bind acceptance claims to the already-inspected installed GGUF runtime.

This check is a post-activation evidence fence. It never substitutes for
the install doctor's descriptor-based reads, the isolated native process,
or the canonical SQLite transaction. It cannot certify physical devices,
reliability, model quality or software release readiness.
"""
from __future__ import annotations

from skeleton.ai.runtime.operational_ai.deployment.install.doctor import (
    InstalledModelReport,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import (
    ExecutionSpine,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import (
    SupervisedAI,
)
from skeleton.ai.runtime.operational_ai.model.admission.wrapper import (
    AdmittedBackend,
)
from skeleton.ai.runtime.operational_ai.model.isolation.client import (
    IsolatedGGUFBackend,
)

from .contracts import identity_hash, refuse
from .identity import ActiveModel


def require_activated_source(worker: object, receipt: object) -> dict[str, object]:
    """Refuse a fabricated source report or noncanonical synthetic worker.

    The only supported positive entry point obtains both values from the
    existing activate_checked() source verification and model startup.
    Reading the report never obtains third-party rights or proves a device.
    """
    if type(worker) is not SupervisedAI:
        refuse("real acceptance requires the canonical supervised native worker")
    if type(getattr(worker, "spine", None)) is not ExecutionSpine:
        refuse("real acceptance requires the canonical SQLite execution spine")
    # A typed wrapper alone can never elevate a synthetic model to a real
    # inference witness. The actual activation path always owns a live,
    # capacity-fenced isolated GGUF child with an immutable source manifest.
    backend = getattr(worker.spine, "backend", None)
    if (type(backend) is not AdmittedBackend
            or type(getattr(backend, "backend", None)) is not IsolatedGGUFBackend):
        refuse("isolated capacity-fenced GGUF model required")
    if type(receipt) is not InstalledModelReport:
        refuse("approved installed model receipt required")
    if (receipt.content_verified is not True
            or receipt.rights_approved is not True
            or receipt.release_certified is not False):
        refuse("installed source content or rights are not verified")
    if (type(receipt.shard_count) is not int
            or not 1 <= receipt.shard_count <= 65536
            or type(receipt.model_bytes) is not int
            or not 1 <= receipt.model_bytes <= 10**12):
        refuse("finite nonempty installed model inventory required")
    model_sha = identity_hash(receipt.model_sha256)
    manifest_sha = identity_hash(receipt.manifest_sha256)
    archive_sha = identity_hash(receipt.archive_sha256)
    origin = receipt.source_sha
    if (type(origin) is not str
            or len(origin) not in (40, 64)
            or any(ch not in "0123456789abcdef" for ch in origin)):
        refuse("source revision custody not verifiable")
    current = ActiveModel.from_supervisor(worker)
    if model_sha != current.model_sha256:
        refuse("installed model digest differs from active native principal")
    backend.lease.assert_live()
    native = backend.backend
    if native.healthy is not True:
        refuse("isolated GGUF native child is not healthy")
    running = native.health()
    if (type(running) is not dict
            or running.get("status") != "running"
            or running.get("manifest_sha256") != manifest_sha
            or running.get("model_sha256") != model_sha
            or running.get("tokenizer_sha256") != current.tokenizer_sha256
            or running.get("isolation") != "dedicated-local-child-no-provider"):
        refuse("installed source differs from live native GGUF child")
    return {
        "model_sha256": current.model_sha256,
        "tokenizer_sha256": current.tokenizer_sha256,
        "manifest_sha256": manifest_sha,
        "archive_sha256": archive_sha,
        "source_sha": origin,
        "installed_model_bytes": receipt.model_bytes,
        "installed_shard_count": receipt.shard_count,
    }


__all__ = ["require_activated_source"]
