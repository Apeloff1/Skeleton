"""Resource-admitted actual offline production across registered game briefs."""
from __future__ import annotations

from pathlib import Path
import time
from typing import Sequence

from .studio_ecosystem_catalog import list_blueprints, StudioEcosystemError
from .studio_ecosystem_capacity import (
    observe_producer_capacity, plan_producer_admission,
)
from .studio_ecosystem_journal import _private_directory
from .studio_ecosystem_portfolio import StudioPortfolio
from .studio_ecosystem_offline_bundle import build_offline_studio_bundle
from .studio_ecosystem_offline_verify import verify_studio_bundle


def build_catalog_preview_batch(portfolio: StudioPortfolio, output_root: Path, *,
                                project_ids: Sequence[str] | None = None,
                                genre: str | None = None, biome: str | None = None,
                                working_set_bytes: int,
                                estimated_output_bytes: int,
                                authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("multi-game preview output requires operator authorization")
    output_root=Path(output_root)
    _private_directory(output_root)
    indexed={p["id"] for p in list_blueprints(genre=genre,biome=biome)}
    wanted=sorted(indexed) if project_ids is None else list(project_ids)
    if (not wanted or len(wanted)!=len(set(wanted)) or
            any(not isinstance(x,str) or x not in indexed for x in wanted)):
        raise StudioEcosystemError("invalid or repeated registered selection")
    # The caller estimates per-project memory and output: actual disk headroom
    # is checked again for every project, not once for the whole batch.
    successes=[]
    for pid in wanted:
        capacity=observe_producer_capacity(output_root)
        budget=plan_producer_admission(capacity,working_set_bytes=working_set_bytes,
                                       output_bytes=estimated_output_bytes)
        if budget["admitted_worker_slots"]<1:
            return {"schema":"skeleton.game_builder.studio_batch_preview.v1",
                    "selected_projects":len(wanted),"completed_projects":len(successes),
                    "receipts":successes,"next_unprocessed_project":pid,
                    "status":"paused_by_measured_resource_capacity",
                    "all_projects_completed":False,
                    "consumer_release_certified":False}
        started=time.monotonic_ns()
        disk_before=capacity.free_disk_bytes
        supervisor=portfolio.open(pid,authorized=True)
        receipt=build_offline_studio_bundle(supervisor.journal,supervisor.spool,
                                             output_root,authorized=True)
        verification=verify_studio_bundle(Path(receipt["output_dir"]),authorized=True)
        if not verification["local_bundle_integrity_verified"]:
            raise StudioEcosystemError("post-write package integrity failed")
        elapsed=max(1,time.monotonic_ns()-started)
        disk_after=observe_producer_capacity(output_root).free_disk_bytes
        successes.append({"project_id":pid,"manifest_sha256":receipt["manifest_sha256"],
                          "local_bundle_integrity_verified":True,
                          "elapsed_monotonic_ns":elapsed,
                          "measured_disk_change_bytes":disk_before-disk_after,
                          "target_genre_qualified":False})
    return {"schema":"skeleton.game_builder.studio_batch_preview.v1",
            "selected_projects":len(wanted),"completed_projects":len(successes),
            "receipts":successes,"next_unprocessed_project":None,
            "status":"local_preview_batch_completed",
            "all_projects_completed":True,
            "consumer_release_certified":False}
