"""Verify actual source-bound installer bytes and model epoch on live backend."""
from __future__ import annotations
from ..contracts import fail

def inspect(*,model_root,worker,rights_approval_required=True):
    from skeleton.ai.runtime.operational_ai.laptop_runtime.installation import source_receipt
    from skeleton.ai.runtime.operational_ai.laptop_runtime.native_identity import verify
    if type(rights_approval_required) is not bool or not rights_approval_required:
        fail("installed model rights check may not be disabled")
    approved=source_receipt(model_root,require_rights=True)
    actual=worker.spine.identity
    if approved.model_sha256!=actual.model_sha256:
        fail("active backend is not the installed approved checkpoint")
    check=verify(worker.spine.backend,actual.model_sha256,actual.tokenizer_sha256)
    return {"source_archive_sha256":approved.archive_sha256,
            "installed_model_sha256":approved.model_sha256,
            "backend":check,"model_rights_approved":approved.rights_approved,
            "native_generation_tested":False}
