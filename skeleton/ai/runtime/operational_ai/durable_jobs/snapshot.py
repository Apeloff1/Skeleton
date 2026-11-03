"""Read-consistent SQLite backup to a new exclusive owner-private file.

Refuses preexisting targets, links, public directories, and unsupported POSIX
custody. Backups are local operator artifacts; no cloud or model upload.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
from .canonical import require_int
from .errors import deny
from .spec import require_id
from .store import JobStore


def exclusive_backup(store:JobStore,root_fd:int,leaf:str,*,max_bytes:int=134217728)->dict:
    if type(store) is not JobStore:
        deny("backup-store")
    from .spec import require_id
    # Only lowercase safe leaf names, no path separators or dot traversal.
    require_id(leaf,"backup-leaf")
    require_int(max_bytes,4096,1073741824,"backup-limit")
    if os.name!="posix" or not hasattr(os,"O_NOFOLLOW"):
        deny("backup-unsupported-platform")
    root=os.fstat(root_fd)
    if not stat.S_ISDIR(root.st_mode) or root.st_uid!=os.geteuid() or root.st_mode & 0o077:
        deny("backup-root")
    flags=os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_RDWR
    try:
        fd=os.open(leaf,flags,0o600,dir_fd=root_fd)
    except OSError:
        deny("backup-target-exists-or-unsafe")
    try:
        # SQLite backup API requires a path. /proc/self/fd retains the open,
        # exclusive target descriptor on Linux only.
        if not Path("/proc/self/fd").is_dir():
            deny("backup-platform")
        dest_path="/proc/self/fd/"+str(fd)
        with sqlite3.connect(dest_path) as dest:
            store.db.backup(dest)
        st=os.fstat(fd)
        if st.st_size>max_bytes or st.st_nlink!=1 or st.st_mode & 0o077:
            deny("backup-boundary")
        os.fsync(fd)
        h=hashlib.sha256()
        os.lseek(fd,0,os.SEEK_SET)
        while piece:=os.read(fd,65536):
            h.update(piece)
        os.fsync(root_fd)
        return {"sha256":h.hexdigest(),"bytes":st.st_size,
                "name":leaf,"source":"sqlite-online-backup"}
    except BaseException:
        try:
            os.unlink(leaf,dir_fd=root_fd)
        except OSError:
            pass
        raise
    finally:
        os.close(fd)
