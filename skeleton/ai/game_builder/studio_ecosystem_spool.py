"""Private, content-addressed, streamed local producer artifact spool.

A byte digest proves local content identity only: neither rights, semantics,
native runtime nor release status. No artificial total input-file count cap.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import shutil
import tempfile
from typing import Iterable

from .studio_ecosystem_journal import HEX, _private_directory
from .studio_ecosystem_quest import StudioQuestError


class ArtifactSpool:
    def __init__(self, root: Path, *, authorized: bool):
        if not authorized:
            raise PermissionError("artifact spool requires operator authorization")
        self.root=Path(root)
        _private_directory(self.root)
        self.path=self.root/"objects"
        self.path.mkdir(mode=0o700,exist_ok=True)
        _private_directory(self.path)

    def _target(self, fingerprint: str) -> Path:
        if not isinstance(fingerprint,str) or not HEX.fullmatch(fingerprint):
            raise StudioQuestError("invalid content-addressed artifact digest")
        return self.path/fingerprint

    def ingest(self, chunks: Iterable[bytes], *, authorized: bool,
               expected_sha256: str | None = None) -> dict[str, object]:
        if not authorized:
            raise PermissionError("spool ingestion requires operator authorization")
        if expected_sha256 is not None:
            self._target(expected_sha256)
        _private_directory(self.path)
        fd,name=tempfile.mkstemp(prefix=".staging-",dir=self.path)
        temp=Path(name)
        total=0
        h=sha256()
        try:
            with os.fdopen(fd,"wb") as stream:
                for data in chunks:
                    if not isinstance(data,bytes):
                        raise StudioQuestError("spool requires byte chunks")
                    capacity=shutil.disk_usage(self.path).free
                    reserve=max(4*1024*1024, capacity//20)
                    if len(data)>max(0,capacity-reserve):
                        raise StudioQuestError("protected disk reserve exhausted")
                    stream.write(data)
                    h.update(data)
                    total+=len(data)
                stream.flush()
                os.fsync(stream.fileno())
            fingerprint=h.hexdigest()
            if expected_sha256 is not None and fingerprint!=expected_sha256:
                raise StudioQuestError("submitted artifact digest differs from bytes")
            target=self._target(fingerprint)
            # A hard link is no-clobber and atomic on the same local filesystem.
            try:
                os.link(temp,target,follow_symlinks=False)
            except FileExistsError:
                self.verify(fingerprint)
            temp.unlink()
            return {"schema":"skeleton.game_builder.studio_local_spool.v1",
                    "sha256":fingerprint,"bytes":total,
                    "local_digest_verified":True,
                    "rights_verified":False,"runtime_verified":False,
                    "release_certified":False}
        finally:
            temp.unlink(missing_ok=True)

    def verify(self, fingerprint: str) -> int:
        target=self._target(fingerprint)
        if target.is_symlink() or not target.is_file():
            raise StudioQuestError("missing or linked spool object")
        flags=os.O_RDONLY
        if hasattr(os,"O_NOFOLLOW"):
            flags|=os.O_NOFOLLOW
        h=sha256()
        total=0
        with os.fdopen(os.open(target,flags),"rb") as stream:
            while block:=stream.read(1024*1024):
                h.update(block)
                total+=len(block)
        if h.hexdigest()!=fingerprint:
            raise StudioQuestError("spool content changed or hash mismatch")
        return total

    def read_window(self, fingerprint: str, *, offset: int, length: int,
                    memory_budget_bytes: int, authorized: bool) -> bytes:
        if not authorized:
            raise PermissionError("spool read requires operator authorization")
        if any(type(v) is not int for v in (offset,length,memory_budget_bytes)) or (
            offset<0 or length<0 or memory_budget_bytes<=0 or length>memory_budget_bytes
        ):
            raise StudioQuestError("window exceeds operator memory budget")
        total=self.verify(fingerprint)
        if offset>total or length>total-offset:
            raise StudioQuestError("window outside verified artifact")
        target=self._target(fingerprint)
        flags=os.O_RDONLY
        if hasattr(os,"O_NOFOLLOW"):
            flags|=os.O_NOFOLLOW
        with os.fdopen(os.open(target,flags),"rb") as stream:
            before=os.fstat(stream.fileno())
            stream.seek(offset)
            out=stream.read(length)
            after=os.fstat(stream.fileno())
        if (before.st_ino!=after.st_ino or before.st_size!=after.st_size or
                before.st_mtime_ns!=after.st_mtime_ns or len(out)!=length):
            raise StudioQuestError("artifact changed during read")
        return out
