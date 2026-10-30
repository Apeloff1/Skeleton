"""Resumable source-fenced multi-game offline production with no silent skips."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .studio_ecosystem_catalog import list_blueprints, read_blueprint, StudioEcosystemError
from .studio_ecosystem_capacity import observe_producer_capacity, plan_producer_admission
from .studio_ecosystem_journal import _private_directory
from .studio_ecosystem_manifest import source_manifest
from .studio_ecosystem_portfolio import StudioPortfolio
from .studio_ecosystem_offline_verify import verify_studio_bundle
from .studio_ecosystem_offline_bundle import build_offline_studio_bundle
from .studio_ecosystem_quest import StudioQuestError


def resume_catalog_preview_batch(portfolio: StudioPortfolio, output_root: Path, *,
                                 project_ids: Sequence[str],
                                 working_set_bytes: int,
                                 estimated_output_bytes: int,
                                 authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("portfolio resume requires operator authorization")
    root=Path(output_root)
    _private_directory(root)
    registered={record["id"] for record in list_blueprints()}
    if (not isinstance(project_ids,(tuple,list)) or not project_ids or
            len(set(project_ids))!=len(project_ids) or
            any(not isinstance(pid,str) or pid not in registered for pid in project_ids)):
        raise StudioEcosystemError("unknown or duplicate resume source")
    reused=[]
    built=[]
    for pid in project_ids:
        target=root/pid
        if target.exists() or target.is_symlink():
            report=verify_studio_bundle(target,authorized=True)
            current=source_manifest(read_blueprint(pid))["source_chain_sha256"]
            if report["source_chain_sha256"]!=current:
                raise StudioQuestError("existing package source differs from current canon")
            reused.append(pid)
            continue
        capacity=observe_producer_capacity(root)
        admitted=plan_producer_admission(capacity,
            working_set_bytes=working_set_bytes,
            output_bytes=estimated_output_bytes)["admitted_worker_slots"]
        if not admitted:
            return {"schema":"skeleton.game_builder.studio_resume_batch.v1",
                    "reused_verified":reused,"built_now":built,
                    "next_unprocessed_project":pid,
                    "all_projects_complete":False,
                    "pause_reason":"measured_resource_pressure",
                    "release_certified":False}
        supervisor=portfolio.open(pid,authorized=True)
        package=build_offline_studio_bundle(supervisor.journal,supervisor.spool,
                                             root,authorized=True)
        verified=verify_studio_bundle(Path(package["output_dir"]),authorized=True)
        if verified["source_chain_sha256"]!=source_manifest(read_blueprint(pid))["source_chain_sha256"]:
            raise StudioQuestError("source drift during resumed package")
        built.append(pid)
    return {"schema":"skeleton.game_builder.studio_resume_batch.v1",
            "reused_verified":reused,"built_now":built,
            "next_unprocessed_project":None,
            "all_projects_complete":True,
            "pause_reason":None,"release_certified":False}
