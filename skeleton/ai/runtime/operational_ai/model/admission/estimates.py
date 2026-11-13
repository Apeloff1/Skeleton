"""Conservative pre-load duplicate-buffer and runtime-memory accounting."""
from __future__ import annotations
from .contracts import CapacityPolicy, Reservation, AdmissionError
from .canonical import digest


def reservation_for(manifest, *, tenant: str, subject: str,
                    policy: CapacityPolicy) -> Reservation:
    """Use licensed, hash-pinned manifest metadata, never model-calculated bytes."""
    from ..gguf.manifest import GGUFModelManifest
    if not isinstance(manifest,GGUFModelManifest):
        raise AdmissionError('approved source GGUF manifest required')
    if not isinstance(tenant,str) or not tenant or not isinstance(subject,str) or not subject:
        raise AdmissionError('nonempty principal required')
    if len(tenant.encode('utf8')) > 128 or len(subject.encode('utf8')) > 128:
        raise AdmissionError('model principal exceeds bounded identity')
    if not isinstance(policy, CapacityPolicy):
        raise AdmissionError('verified model capacity policy required')
    # Private identity is hashed, never stored in the shared slot file.
    principal_sha = digest({'tenant':tenant,'subject':subject})
    reserve = max(manifest.minimum_memory_bytes,
                  2*manifest.total_bytes + policy.minimum_host_margin_bytes)
    if reserve > policy.budget_bytes:
        raise AdmissionError('model cannot fit configured per-principal capacity')
    return Reservation(manifest.model_sha256,principal_sha,manifest.manifest_digest,reserve)
