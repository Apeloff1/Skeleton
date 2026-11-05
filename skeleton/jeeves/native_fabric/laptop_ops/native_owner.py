"""Bind read-only checks to the existing native worker, never instantiate one."""
from __future__ import annotations
from typing import Any
from .contracts import LaptopGateHold, sha, fingerprint


def inspect(worker: Any, installed_receipt: Any) -> dict[str, object]:
    # Reuse the exact source-bound supervisor and trusted installer gates.
    from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
    from skeleton.jeeves.agent.native_readiness import inspect_native_jeeves

    try:
        active = ActiveModel.from_supervisor(worker)
        readiness = inspect_native_jeeves(worker, installed_receipt)
        if not readiness.source_bridge_ready:
            raise LaptopGateHold("canonical source bridge held")
        if sha(active.model_sha256) != sha(installed_receipt.model_sha256):
            raise LaptopGateHold("native model identity mismatch")
        if not callable(getattr(worker.spine, "replay", None)):
            raise LaptopGateHold("canonical SQLite replay authority missing")
        if not callable(getattr(worker.spine, "history", None)):
            raise LaptopGateHold("canonical conversation authority missing")
        return {"schema": "jeeves.laptop_ops.native_owner_read.v1",
                "scope_sha256": fingerprint({
                    "tenant": active.tenant, "subject": active.subject,
                    "model": active.model_sha256,
                    "tokenizer": active.tokenizer_sha256,
                }),
                "model_sha256": active.model_sha256,
                "tokenizer_sha256": active.tokenizer_sha256,
                "source_bound": True,
                "new_provider_or_storage_authority": False,
                "native_generation_witnessed": False,
                "device_qualified": False}
    except (AttributeError, TypeError, ValueError) as exc:
        raise LaptopGateHold("native supervisor or installer proof held") from exc
