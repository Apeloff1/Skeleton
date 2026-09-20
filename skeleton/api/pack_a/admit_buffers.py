"""admit_buffers — BufferPool staging for mutating admit paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from skeleton.kernel.pack_a.buffer_arena import (
    BodyStagingPool,
    StagingLease,
    classify_path,
    default_body_pool,
    min_size_for_route_class,
    recipe_for,
)
from skeleton.kernel.pack_a.metrics import default_meter


@dataclass
class BoundBody:
    route_class: str
    content_length: Optional[int]
    min_size: int
    size_class: str
    bytes_written: int
    payload: bytes


class AdmitBodyStager:
    """Stage mutating request bodies through Pack A BodyStagingPool."""

    def __init__(self, pool: Optional[BodyStagingPool] = None) -> None:
        self.pool = pool if pool is not None else default_body_pool()
        self.meter = default_meter()

    def stage_bytes(
        self,
        path: str,
        data: bytes,
        *,
        content_length: Optional[int] = None,
    ) -> BoundBody:
        route_class = classify_path(path)
        recipe = recipe_for(route_class, content_length if content_length is not None else len(data))
        self.meter.buffer_leases.labels(route_class).inc()
        with self.pool.stage(content_length=recipe["content_length"]) as lease:
            written = lease.write(data)
            payload = lease.written_bytes()
            self.meter.staging_active.labels(route_class).set(float(self.pool.stats()["active"]))
            return BoundBody(
                route_class=route_class,
                content_length=content_length,
                min_size=int(recipe["min_size"]),
                size_class=str(recipe["class"]),
                bytes_written=written,
                payload=payload,
            )

    def stats(self) -> Dict[str, Any]:
        return self.pool.stats()


def stage_mutating_body(path: str, data: bytes, **kwargs: Any) -> BoundBody:
    return AdmitBodyStager().stage_bytes(path, data, **kwargs)


__all__ = ["AdmitBodyStager", "BoundBody", "stage_mutating_body"]
