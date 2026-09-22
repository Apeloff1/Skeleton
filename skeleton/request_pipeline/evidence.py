"""Evidence digests for Throughput request-pipeline pack."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict

from skeleton.request_pipeline.catalog import PIPELINE_CATALOG
from skeleton.request_pipeline.operations import digest_registry, playbook_smoke, registry
from skeleton.request_pipeline.pipeline import default_pipeline


@dataclass(frozen=True)
class PipelineEvidence:
    plane: str
    digest: str
    stages: int
    catalog: int
    registry: int

    def as_dict(self) -> Dict[str, object]:
        return {
            "plane": self.plane,
            "digest": self.digest,
            "stages": self.stages,
            "catalog": self.catalog,
            "registry": self.registry,
        }


def digest_plane() -> str:
    payload = {
        "pipeline": default_pipeline().as_dict(),
        "catalog": len(PIPELINE_CATALOG),
        "registry": sorted(registry().keys())[:50],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def render_evidence() -> PipelineEvidence:
    smoke = playbook_smoke()
    return PipelineEvidence(
        plane="request_pipeline",
        digest=digest_plane(),
        stages=len(default_pipeline().stages),
        catalog=int(smoke["catalog_size"]),
        registry=int(smoke["registry_size"]),
    )


def pack_manifest() -> dict:
    return {
        "pack": "Throughput MW request pipeline",
        "branch": "feat/throughput-mw-request-pipeline-20260920",
        "theme": "request pipeline / authN-Z glue extend-only",
        "no_lifespan_clobber": True,
        "digest": digest_plane(),
        "registry_digest": digest_registry(),
        "catalog": len(PIPELINE_CATALOG),
        "registry": len(registry()),
    }
