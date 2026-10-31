"""Stream entire private object inventory and identify corrupt or orphaned files.

Never silently delete artifacts. This scans all entries without a hard file
count limit; only verbose error details are bounded for caller memory.
"""
from __future__ import annotations

import os

from .studio_ecosystem_journal import HEX, _private_directory
from .studio_ecosystem_spool import ArtifactSpool
from .studio_ecosystem_quest import StudioQuestError


def audit_artifact_spool(spool: ArtifactSpool, *, max_error_details: int = 64,
                         authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("spool assurance requires operator authorization")
    if type(max_error_details) is not int or not 1 <= max_error_details <= 256:
        raise StudioQuestError("invalid bounded diagnostic detail count")
    _private_directory(spool.path)
    valid=0
    corrupt=0
    incomplete=0
    unexpected=0
    total=0
    errors=[]
    # Filesystem iteration is streaming; no artificial total project count.
    with os.scandir(spool.path) as entries:
        for entry in entries:
            if entry.name.startswith(".staging-"):
                incomplete+=1
                category="incomplete_staging"
            elif not HEX.fullmatch(entry.name):
                unexpected+=1
                category="unexpected_artifact_name"
            else:
                try:
                    total+=spool.verify(entry.name)
                    valid+=1
                    continue
                except (OSError, StudioQuestError):
                    corrupt+=1
                    category="corrupt_or_missing_artifact"
            if len(errors)<max_error_details:
                errors.append({"name":entry.name,"reason":category})
    return {"schema":"skeleton.game_builder.studio_spool_audit.v1",
            "valid_artifacts":valid,"corrupted_artifacts":corrupt,
            "incomplete_staging_files":incomplete,
            "unexpected_entries":unexpected,
            "locally_verified_bytes":total,
            "error_details":errors,
            "details_truncated":corrupt+incomplete+unexpected>len(errors),
            "local_content_consistent":corrupt+incomplete+unexpected==0,
            "files_deleted":0,"external_rights_verified":False,
            "release_certified":False}
