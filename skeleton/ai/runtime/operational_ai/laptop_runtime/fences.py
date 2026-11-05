"""One-shot fail-closed serving-mode preflight against real supervisor identity."""
from __future__ import annotations
from .contracts import identifier,identity_hash,refuse
from .identity import ActiveModel
from .readiness import snapshot

def preflight(worker,*,expected_tenant,expected_subject,
              expected_model_sha256,expected_tokenizer_sha256):
    active=ActiveModel.from_supervisor(worker)
    if (active.tenant!=identifier(expected_tenant,"tenant") or
        active.subject!=identifier(expected_subject,"subject")):
        refuse("runtime tenant or principal changed")
    if (active.model_sha256!=identity_hash(expected_model_sha256) or
        active.tokenizer_sha256!=identity_hash(expected_tokenizer_sha256)):
        refuse("runtime model identity changed")
    observed=snapshot(worker)
    if observed["state"]!="native-model-activated-observation-only":
        refuse("unknown runtime observation; cannot serve")
    return {"schema":"laptop-runtime-serve-fence.v1",
            "model_sha256":active.model_sha256,
            "tokenizer_sha256":active.tokenizer_sha256,
            "preflight":"native-backend-loaded-not-device-certified"}
