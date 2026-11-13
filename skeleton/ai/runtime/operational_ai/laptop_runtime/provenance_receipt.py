"""Bind installer receipt, active model and operator profile in one digest."""
from __future__ import annotations
from .contracts import digest,identity_hash,refuse
from .deployment_profile import LaptopProfile
from .identity import ActiveModel

def build(installed,worker,profile):
    if not isinstance(profile,LaptopProfile):refuse("approved runtime profile required")
    active=ActiveModel.from_supervisor(worker)
    if installed.model_sha256!=active.model_sha256:
        refuse("runtime not bound to model installer provenance")
    if not installed.content_verified or not installed.rights_approved:
        refuse("unapproved model bytes")
    body={"schema":"laptop-runtime-provenance.v1",
          "model_sha256":active.model_sha256,
          "tokenizer_sha256":active.tokenizer_sha256,
          "archive_sha256":identity_hash(installed.archive_sha256),
          "source_sha":installed.source_sha,
          "model_bytes":installed.model_bytes,
          "profile":profile.to_record(),"native_backend_loaded":True,
          "real_generation_observed":False}
    return {"record":body,"sha256":digest(body)}
