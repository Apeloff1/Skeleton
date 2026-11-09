"""Bridge build-farm reproducible artifacts into release artifact entries.

Extends :mod:`skeleton.ai.build.build_farm`: a release artifact is only
admitted when at least two attested workers produced the same digest.
"""

from __future__ import annotations

from typing import Sequence

from skeleton.ai.build.build_farm import BuildFarmArtifact
from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.artifact_manifest import ArtifactEntry

MIN_WITNESSES = 2


def entry_from_reproducible(
    artifacts: Sequence[BuildFarmArtifact],
    *,
    path: str,
    kind: str,
    size: int,
    platform: str = "any",
) -> ArtifactEntry:
    items = tuple(artifacts)
    if len(items) < MIN_WITNESSES:
        raise DeliveryError("reproducible artifact requires at least two witnesses")
    if any(not isinstance(a, BuildFarmArtifact) for a in items):
        raise DeliveryError("build farm artifacts required")
    if len({a.job_id for a in items}) != 1:
        raise DeliveryError("witnesses must share one job")
    if len({a.worker_id for a in items}) != len(items):
        raise DeliveryError("witnesses must be distinct workers")
    digests = {a.output_digest for a in items}
    if len(digests) != 1:
        raise DeliveryError("witness digests disagree")
    return ArtifactEntry(path, kind, size, digests.pop(), platform)


def witness_metadata(artifacts: Sequence[BuildFarmArtifact]) -> dict[str, str]:
    """Manifest metadata recording which workers attested an artifact."""
    items = sorted(artifacts, key=lambda a: a.worker_id)
    return {
        "farm.job": items[0].job_id if items else "",
        "farm.workers": ",".join(a.worker_id for a in items),
        "farm.evidence": ",".join(a.attestation_evidence for a in items),
    }
