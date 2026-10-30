"""Bounded-wave concurrent *real* preview production with live resource admission.

Workers share no project writable state. New waves read live RAM/disk/cpu
pressure and stop, rather than admitting beyond measured capacity.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Sequence

from .studio_ecosystem_catalog import list_blueprints,StudioEcosystemError
from .studio_ecosystem_hardware import sample_studio_memory,memory_admission
from .studio_ecosystem_journal import _private_directory
from .studio_ecosystem_portfolio import StudioPortfolio
from .studio_ecosystem_offline_bundle import build_offline_studio_bundle
from .studio_ecosystem_offline_verify import verify_studio_bundle
from .studio_ecosystem_quest import StudioQuestError


def produce_parallel_games(portfolio: StudioPortfolio, output_root: Path, *,
                           project_ids: Sequence[str],
                           working_set_bytes: int,
                           estimated_output_bytes: int,
                           walkable_story: bool = False,
                           authorized: bool) -> dict[str,object]:
    if not authorized:
        raise PermissionError("parallel production requires operator authorization")
    root=Path(output_root)
    _private_directory(root)
    known={entry["id"] for entry in list_blueprints()}
    if (not isinstance(project_ids,(tuple,list)) or not project_ids
            or any(not isinstance(pid,str) or pid not in known for pid in project_ids)
            or len(set(project_ids))!=len(project_ids)
            or type(walkable_story) is not bool):
        raise StudioEcosystemError("invalid registered parallel producer selection")
    if any((root/pid).exists() or (root/pid).is_symlink() for pid in project_ids):
        raise StudioQuestError("parallel output already exists; never overwrite")
    def build(pid: str) -> dict[str,object]:
        supervisor=portfolio.open(pid,authorized=True)
        package=build_offline_studio_bundle(
            supervisor.journal,supervisor.spool,root,
            walkable_story=walkable_story,authorized=True)
        verified=verify_studio_bundle(Path(package["output_dir"]),authorized=True)
        expected=7 if walkable_story else 5
        if verified["files_verified"]!=expected:
            raise StudioQuestError("parallel worker produced wrong package schema")
        return {"project_id":pid,"bundle_sha256":package["manifest_sha256"],
                "files_verified":verified["files_verified"],
                "native_qualified":False}
    results=[]
    cursor=0
    batches=0
    while cursor<len(project_ids):
        telemetry=sample_studio_memory(root)
        admit=memory_admission(
            telemetry,working_bytes=working_set_bytes,
            spill_bytes=estimated_output_bytes)
        slots=admit["admitted_slots"]
        if slots<1:
            return {"schema":"skeleton.game_builder.parallel_game_batch.v1",
                    "completed_projects":results,
                    "next_unprocessed_project":project_ids[cursor],
                    "resource_pressure_paused":True,
                    "production_batches":batches,
                    "all_projects_completed":False,
                    "consumer_release_certified":False}
        tasks=list(project_ids[cursor:cursor+slots])
        # Executor only touches independent project-owned directories; a
        # worker exception propagates and cannot certify the entire wave.
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            receipts=list(pool.map(build,tasks))
        results.extend(receipts)
        cursor+=len(tasks)
        batches+=1
    return {"schema":"skeleton.game_builder.parallel_game_batch.v1",
            "completed_projects":results,"next_unprocessed_project":None,
            "resource_pressure_paused":False,
            "production_batches":batches,"all_projects_completed":True,
            "consumer_release_certified":False}
