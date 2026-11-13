"""Read-only state-directory custody and ownership check before activation."""
from __future__ import annotations
import os
import stat
from pathlib import Path
from .contracts import refuse

def inspect_state(path):
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.path_policy import open_private_root
    fd=open_private_root(path)
    try:
        st=os.fstat(fd)
        if (not stat.S_ISDIR(st.st_mode) or st.st_nlink<1
            or st.st_uid!=os.getuid() or st.st_mode&0o077):
            refuse("untrusted private state root")
        return {"state_root_verified":True,"owner_uid":st.st_uid,
                "private_permissions":True,"release_certified":False}
    finally:
        os.close(fd)
