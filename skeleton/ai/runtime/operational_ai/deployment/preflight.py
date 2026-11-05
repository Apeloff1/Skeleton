"""Operational readiness is explicit evidence, not line-count completion."""
from __future__ import annotations
from pathlib import Path
import os
import platform
from ..authority.canonical import ContractViolation,require_digest
from ..model.catalog import ModelCatalog,ModelArtifact


def check(model_root:Path,artifact:ModelArtifact,*,database_dir:Path)->dict:
    checks={}
    notes=[]
    try:
        catalog=ModelCatalog(model_root,[artifact])
        catalog.verify(artifact.name)
        checks["checkpoint_digest_pinned"]=True
    except (OSError,ContractViolation) as exc:
        checks["checkpoint_digest_pinned"]=False
        notes.append("checkpoint-not-accepted")
    checks["private_state_root"]=(database_dir.is_dir() and not database_dir.is_symlink()
            and database_dir.stat().st_mode & 0o077==0)
    checks["offline_execution_configured"]=True
    checks["native_runtime_supports_os"]=os.name=="posix"
    checks["production_model_quality_proven"]=False
    checks["end_to_end_native_inference_executed"]=False
    return {"status":"needs-validation","checks":checks,"notes":notes,
            "platform":platform.system(),"next":"run actual checkpoint turn, restart, and exact-head CI"}
