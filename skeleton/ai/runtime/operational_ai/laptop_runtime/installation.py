"""Read-only model installation receipt proof without assuming model quality."""
from __future__ import annotations
from .contracts import refuse,identity_hash

def source_receipt(model_root,*,expected_model_sha256=None,require_rights=True):
    from skeleton.ai.runtime.operational_ai.deployment.install.doctor import inspect_installed_model
    result=inspect_installed_model(model_root)
    if type(require_rights) is not bool:refuse("invalid rights flag")
    if expected_model_sha256 is not None and result.model_sha256!=identity_hash(expected_model_sha256):
        refuse("installed model digest changed")
    if not result.content_verified or not result.archive_sha256:
        refuse("model archive custody is unverified")
    if require_rights and not result.rights_approved:
        refuse("model rights approval not granted")
    return result
