"""Bridge B008 verified remote-build receipts into release artifact entries.

Extends :mod:`skeleton.build.remote_build`; it does not re-verify receipts.
Callers must pass receipts returned by ``verify_remote_receipt``.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.artifact_manifest import ARTIFACT_KINDS, ArtifactEntry
from skeleton.build.remote_build import VerifiedRemoteReceipt

# Bound hostile or accidentally unending receipt streams before publication.
MAX_REMOTE_RECEIPTS = 4096
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
    artifact_count = 0
    for receipt_index, receipt in enumerate(receipts):
        if receipt_index >= MAX_REMOTE_RECEIPTS:
            raise DeliveryError("remote receipt count exceeds bound")
        if not isinstance(receipt, VerifiedRemoteReceipt):
            raise DeliveryError("verified remote receipts required")
        if receipt.status != "success":
            raise DeliveryError(f"job {receipt.job_id} did not succeed ({receipt.status})")
        for ref in receipt.output_artifacts:
            artifact_count += 1
            if artifact_count > MAX_REMOTE_ARTIFACTS:
                raise DeliveryError("remote artifact count exceeds bound")
            path = (paths or {}).get(ref.artifact_id, ref.artifact_id)
            kind = _kind_for(path)
            assert kind in ARTIFACT_KINDS
            entry = ArtifactEntry(path, kind, ref.size_bytes, ref.sha256, platform)
            existing = out.get(entry.path)
            if existing is not None and existing != entry:
                raise DeliveryError(f"conflicting outputs for {entry.path}")
            out[entry.path] = entry
    return tuple(sorted(out.values(), key=lambda e: e.path))
