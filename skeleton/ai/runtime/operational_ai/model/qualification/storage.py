"""No-clobber, owner-only durable publication of output-free model metrics."""
from __future__ import annotations
import os
from pathlib import Path
from .contracts import QualificationHeld
from ..admission.canonical import canonical
from ..admission.paths import verified_dir,open_file,write_file


def publish_private(root:Path|str,name:str,report:dict)->dict:
    if not isinstance(name,str) or not name.endswith('.json') or '/' in name or '\\' in name or len(name)>100:
        raise QualificationHeld('private report file name must be a direct JSON child')
    raw=canonical(report,maximum=131072)
    root_fd=verified_dir(root)
    try:
        # No-clobber avoids overwriting evidence from an earlier native run.
        fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=root_fd)
        try:
            written=0
            while written<len(raw):
                n=os.write(fd,raw[written:])
                if n<=0:raise QualificationHeld('incomplete private report publication')
                written+=n
            os.fsync(fd)
        finally:os.close(fd)
        os.fsync(root_fd)
    finally:os.close(root_fd)
    from hashlib import sha256
    return {'status':'private-report-created-no-clobber',
            'report_sha256':sha256(raw).hexdigest(),'bytes':len(raw)}
