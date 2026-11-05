"""Stream source-bound offline game package evidence across a registered portfolio.

Missing, tampered, outdated or wrong-mode packages remain explicit failures.
No files are changed and a valid source fingerprint is NOT external attestation.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Sequence

from .studio_ecosystem_catalog import list_blueprints, read_blueprint, StudioEcosystemError
from .studio_ecosystem_manifest import source_manifest
from .studio_ecosystem_offline_verify import verify_studio_bundle
from .studio_ecosystem_journal import _private_directory
from .studio_ecosystem_quest import StudioQuestError


def audit_offline_portfolio(root: Path, *, project_ids: Sequence[str],
                            expected_version: int | None = None,
                            max_error_details: int = 64,
                            authorized: bool) -> dict[str,object]:
    if not authorized:
        raise PermissionError("portfolio evidence census requires operator authorization")
    root=Path(root)
    _private_directory(root)
    known={p["id"] for p in list_blueprints()}
    if (not isinstance(project_ids,(list,tuple)) or not project_ids
            or any(not isinstance(x,str) or x not in known for x in project_ids)
            or len(set(project_ids))!=len(project_ids)):
        raise StudioEcosystemError("duplicate or unregistered portfolio source")
    if (expected_version is not None and (
            type(expected_version) is not int or expected_version not in (1,2,3)
        )) or type(max_error_details) is not int or not 1<=max_error_details<=512:
        raise StudioEcosystemError("invalid output format or diagnostic envelope")
    success=0
    rejected=0
    absent=0
    errors=[]
    chain=sha256(b"skeleton.game_builder.offline_portfolio_census.v1\n")
    for pid in project_ids:
        target=root/pid
        outcome={"project_id":pid,"result":"unverified","source_sha256":""}
        if not target.exists() and not target.is_symlink():
            absent+=1
            outcome["result"]="missing"
        else:
            try:
                verified=verify_studio_bundle(target,authorized=True)
                wanted=source_manifest(read_blueprint(pid))["source_chain_sha256"]
                if verified["source_chain_sha256"]!=wanted:
                    raise StudioQuestError("catalog source differs from rendered output")
                if expected_version is not None and not verified["package_format"].endswith(
                    ".v"+str(expected_version)):
                    raise StudioQuestError("requested game runtime variant not present")
                success+=1
                outcome["result"]="verified_local_package"
                outcome["source_sha256"]=wanted
                outcome["package_format"]=verified["package_format"]
            except (StudioQuestError,StudioEcosystemError,OSError,ValueError,TypeError):
                rejected+=1
                outcome["result"]="source_or_integrity_rejected"
        if outcome["result"]!="verified_local_package" and len(errors)<max_error_details:
            errors.append({"project_id":pid,"failure":outcome["result"]})
        chain.update(json.dumps(outcome,sort_keys=True,ensure_ascii=True,
                                separators=(",",":"),allow_nan=False).encode("ascii")+b"\n")
    return {"schema":"skeleton.game_builder.offline_portfolio_census.v1",
            "registered_requested":len(project_ids),"valid_local_packages":success,
            "missing_packages":absent,"rejected_packages":rejected,
            "details_truncated":absent+rejected>len(errors),
            "errors":errors,"source_and_package_chain_sha256":chain.hexdigest(),
            "all_requested_valid":success==len(project_ids),
            "independent_provenance_verified":False,
            "native_gameplay_qualified":False,"consumer_release_certified":False}
