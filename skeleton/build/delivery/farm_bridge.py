"""Bridge build-farm reproducible artifacts into release artifact entries.

Extends :mod:`skeleton.ai.build.build_farm`: a release artifact is only
admitted when at least two attested workers produced the same digest.
"""

from __future__ import annotations

import re
from typing import Sequence

from skeleton.ai.build.build_farm import BuildFarmArtifact
from skeleton.build.delivery._util import DeliveryError, require_id
from skeleton.build.delivery.artifact_manifest import ArtifactEntry

MIN_WITNESSES = 2
MAX_WITNESSES = 128
MAX_WITNESS_METADATA_CHARS = 512
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _checked_witnesses(artifacts: Sequence[BuildFarmArtifact]) -> tuple[BuildFarmArtifact, ...]:
    if not isinstance(artifacts, Sequence) or len(artifacts) > MAX_WITNESSES:
        raise DeliveryError("build farm witness count exceeds bound")
    items = tuple(artifacts)
    if len(items) < MIN_WITNESSES:
        raise DeliveryError("reproducible artifact requires at least two witnesses")
    if any(not isinstance(a, BuildFarmArtifact) for a in items):
        raise DeliveryError("build farm artifacts required")
    for artifact in items:
        require_id(artifact.job_id, field="farm job id")
        require_id(artifact.worker_id, field="farm worker id")
        require_id(artifact.attestation_evidence, field="farm attestation evidence id")
    if len({a.job_id for a in items}) != 1:
        raise DeliveryError("witnesses must share one job")
    if len({a.worker_id for a in items}) != len(items):
        raise DeliveryError("witnesses must be distinct workers")
    if (any(type(a.attestation_evidence) is not str or not a.attestation_evidence
            or type(a.environment_digest) is not str or not _SHA256.fullmatch(a.environment_digest)
            or type(a.output_digest) is not str or not _SHA256.fullmatch(a.output_digest)
            for a in items)
            or len({a.attestation_evidence for a in items}) != len(items)):
        raise DeliveryError("independent attestation evidence required")
    if len({a.output_digest for a in items}) != 1:
        raise DeliveryError("witness digests disagree")
    return items


def entry_from_reproducible(
    artifacts: Sequence[BuildFarmArtifact],
    *,
    path: str,
    kind: str,
    size: int,
    platform: str = "any",
) -> ArtifactEntry:
    items = _checked_witnesses(artifacts)
    return ArtifactEntry(path, kind, size, items[0].output_digest, platform)


def witness_metadata(artifacts: Sequence[BuildFarmArtifact]) -> dict[str, str]:
    """Manifest metadata recording which workers attested an artifact."""
    items = sorted(_checked_witnesses(artifacts), key=lambda a: a.worker_id)
    workers = ",".join(a.worker_id for a in items)
    evidence = ",".join(a.attestation_evidence for a in items)
    if len(workers) > MAX_WITNESS_METADATA_CHARS or len(evidence) > MAX_WITNESS_METADATA_CHARS:
        raise DeliveryError("farm witness metadata exceeds manifest bound")
    return {"farm.job": items[0].job_id, "farm.workers": workers, "farm.evidence": evidence}
