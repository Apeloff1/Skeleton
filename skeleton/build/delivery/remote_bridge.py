"""Bridge B008 verified remote-build receipts into release artifact entries.

Extends :mod:`skeleton.build.remote_build`; it does not re-verify receipts.
Callers must pass receipts returned by ``verify_remote_receipt``.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from skeleton.build.delivery._util import DeliveryError, require_id, require_sha256
from skeleton.build.delivery.artifact_manifest import ARTIFACT_KINDS, ArtifactEntry
from skeleton.build.remote_build import RemoteArtifactRef, VerifiedRemoteReceipt

MAX_REMOTE_RECEIPTS = 2048
MAX_REMOTE_OUTPUTS = 2048
MAX_REMOTE_ARTIFACTS = 16384


def _kind_for(artifact_id: str) -> str:
    lowered = artifact_id.lower()
    for suffix, kind in ((".whl", "wheel"), (".tar.gz", "tarball"), (".zip", "zip"), (".json", "config")):
        if lowered.endswith(suffix):
            return kind
    return "binary"


def entries_from_receipts(
    receipts: Iterable[VerifiedRemoteReceipt],
    *,
    paths: Mapping[str, str] | None = None,
    platform: str = "any",
) -> tuple[ArtifactEntry, ...]:
    """Convert successful receipts into manifest entries.

    ``paths`` optionally maps remote ``artifact_id`` to a release path; by
    default the artifact id is used as the path.
    """
    out: dict[str, ArtifactEntry] = {}
    source_by_path: dict[str, str] = {}
    seen_jobs: dict[str, VerifiedRemoteReceipt] = {}
    output_count = 0
    artifact_count = 0
    for count, receipt in enumerate(receipts, 1):
        if count > MAX_REMOTE_RECEIPTS:
            raise DeliveryError("remote receipt count exceeds bound")
        if not isinstance(receipt, VerifiedRemoteReceipt):
            raise DeliveryError("verified remote receipts required")
        require_id(receipt.job_id, field="remote job id")
        require_id(receipt.runner_id, field="remote runner id")
        require_sha256(receipt.receipt_digest, field="remote receipt digest")
        require_sha256(receipt.log_digest, field="remote log digest")
        if receipt.status != "success":
            raise DeliveryError(f"job {receipt.job_id} did not succeed ({receipt.status})")
        previous = seen_jobs.get(receipt.job_id)
        if previous is not None and previous != receipt:
            raise DeliveryError(f"conflicting remote receipts for job {receipt.job_id}")
        seen_jobs[receipt.job_id] = receipt
        if len(receipt.output_artifacts) > MAX_REMOTE_OUTPUTS - output_count:
            raise DeliveryError("remote output inventory exceeds bound")
        output_count += len(receipt.output_artifacts)
        for ref in receipt.output_artifacts:
            artifact_count += 1
            if artifact_count > MAX_REMOTE_ARTIFACTS:
                raise DeliveryError("remote artifact count exceeds bound")
            if not isinstance(ref, RemoteArtifactRef):
                raise DeliveryError("remote artifact reference must be verified")
            path = (paths or {}).get(ref.artifact_id, ref.artifact_id)
            if type(path) is not str or type(ref.artifact_id) is not str:
                raise DeliveryError("invalid remote artifact path identity")
            kind = _kind_for(path)
            assert kind in ARTIFACT_KINDS
            entry = ArtifactEntry(path, kind, ref.size_bytes, ref.sha256, platform)
            source = source_by_path.get(entry.path)
            if source is not None and source != ref.artifact_id:
                raise DeliveryError(f"remote artifact alias collision for {entry.path}")
            source_by_path[entry.path] = ref.artifact_id
            existing = out.get(entry.path)
            if existing is not None and existing != entry:
                raise DeliveryError(f"conflicting outputs for {entry.path}")
            out[entry.path] = entry
    return tuple(sorted(out.values(), key=lambda e: e.path))
