"""Private, content-addressed, streamed local producer artifact spool.

A byte digest proves local content identity only: neither rights, semantics,
native runtime nor release status. No artificial total input-file count cap.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import shutil
import stat
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
            if os.name=="posix":
                fd_dir=os.open(self.path,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
                try:
                    os.fsync(fd_dir)
                finally:
                    os.close(fd_dir)
            return {"schema":"skeleton.game_builder.studio_local_spool.v1",
                    "sha256":fingerprint,"bytes":total,
                    "local_digest_verified":True,
                    "rights_verified":False,"runtime_verified":False,
                    "release_certified":False}
        finally:
            temp.unlink(missing_ok=True)

    def _read_verified(self, fingerprint: str, *, offset: int,
                       length: int | None) -> tuple[int, bytes]:
        """Hash and read one open descriptor, rejecting pathname races."""
        target=self._target(fingerprint)
        flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)
        h=sha256()
        total=0
        selected=bytearray()
        with os.fdopen(os.open(target,flags),"rb") as stream:
            before=os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or
                    (os.name=="posix" and before.st_mode & 0o077)):
                raise StudioQuestError("unsafe object type or sharing")
            while chunk:=stream.read(1024*1024):
                h.update(chunk)
                if length is not None:
                    begin=max(0,offset-total)
                    end=min(len(chunk),offset+length-total)
                    if end>begin:
                        selected.extend(chunk[begin:end])
                total+=len(chunk)
            after=os.fstat(stream.fileno())
        if (before.st_dev!=after.st_dev or before.st_ino!=after.st_ino or
                before.st_size!=after.st_size or before.st_mtime_ns!=after.st_mtime_ns
                or h.hexdigest()!=fingerprint):
            raise StudioQuestError("object changed during read or digest mismatch")
        if length is not None and (offset>total or length>total-offset
                                   or len(selected)!=length):
            raise StudioQuestError("verified window outside object")
        return total,bytes(selected)

    def export_verified(self, fingerprint: str, destination: Path, *,
                        authorized: bool) -> dict[str, object]:
        """Stream a verified private spool object to a new owner-only output.

        A failed integrity check removes only this newly created file. Never
        overwrites or mutates an existing operator document.
        """
        if not authorized:
            raise PermissionError("verified export requires operator authorization")
        destination=Path(destination)
        _private_directory(destination.parent)
        if destination.exists() or destination.is_symlink():
            raise StudioQuestError("artifact export cannot overwrite a path")
        source=self._target(fingerprint)
        flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)
        output_flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0)
        bytes_written=0
        h=sha256()
        created=False
        try:
            with os.fdopen(os.open(source,flags),"rb") as reader:
                original=os.fstat(reader.fileno())
                if (not stat.S_ISREG(original.st_mode) or original.st_nlink!=1 or
                        (os.name=="posix" and original.st_mode & 0o077)):
                    raise StudioQuestError("unsafe object source")
                with os.fdopen(os.open(destination,output_flags,0o600),"wb") as writer:
                    created=True
                    while block:=reader.read(1024*1024):
                        h.update(block)
                        writer.write(block)
                        bytes_written+=len(block)
                    writer.flush()
                    os.fsync(writer.fileno())
                after=os.fstat(reader.fileno())
            if (original.st_dev!=after.st_dev or original.st_ino!=after.st_ino or
                    original.st_size!=after.st_size or
                    original.st_mtime_ns!=after.st_mtime_ns or
                    h.hexdigest()!=fingerprint):
                raise StudioQuestError("exported source failed full verification")
            return {"sha256":fingerprint,"bytes":bytes_written,
                    "content_verified":True,"external_rights_verified":False}
        except BaseException:
            if created:
                destination.unlink(missing_ok=True)
            raise

    def verify(self, fingerprint: str) -> int:
        return self._read_verified(fingerprint,offset=0,length=None)[0]

    def read_window(self, fingerprint: str, *, offset: int, length: int,
                    memory_budget_bytes: int, authorized: bool) -> bytes:
        if not authorized:
            raise PermissionError("spool read requires operator authorization")
        if any(type(v) is not int for v in (offset,length,memory_budget_bytes)) or (
            offset<0 or length<0 or memory_budget_bytes<=0 or length>memory_budget_bytes
        ):
            raise StudioQuestError("window exceeds operator memory budget")
        return self._read_verified(fingerprint,offset=offset,length=length)[1]
