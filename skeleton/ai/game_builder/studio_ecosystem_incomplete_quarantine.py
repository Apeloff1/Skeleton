"""Operator-only quarantine of incomplete local game preview directories.

No cleanup task silently deletes, truncates, or overwrites user's artifacts.
A finished manifest, even corrupted, requires separate manual review.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets

from .studio_ecosystem_catalog import IDENT
from .studio_ecosystem_journal import TOKEN, _private_directory
from .studio_ecosystem_quest import StudioQuestError


def quarantine_incomplete_bundle(output_root: Path, project_id: str, *,
                                 operator: str, authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("manual quarantine requires operator authorization")
    if (not isinstance(project_id,str) or not IDENT.fullmatch(project_id)
            or not isinstance(operator,str) or not TOKEN.fullmatch(operator)):
        raise StudioQuestError("invalid operator or target identity")
    root=Path(output_root)
    _private_directory(root)
    target=root/project_id
    _private_directory(target)
    if (target/"manifest.json").exists() or (target/"manifest.json").is_symlink():
        raise StudioQuestError("completed or suspicious manifest requires separate review")
    quarantine=root/".studio-quarantine"
    quarantine.mkdir(mode=0o700,exist_ok=True)
    _private_directory(quarantine)
    destination=quarantine/(project_id+"-"+secrets.token_hex(12))
    if destination.exists() or destination.is_symlink():
        raise StudioQuestError("quarantine collision")
    os.rename(target,destination)
    if os.name=="posix":
        for folder in (root,quarantine):
            fd=os.open(folder,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    return {"schema":"skeleton.game_builder.studio_incomplete_quarantine.v1",
            "project_id":project_id,"operator":operator,
            "preserved_directory":str(destination),
            "files_deleted":0,"incomplete_bundle_quarantined":True,
            "release_certified":False}
