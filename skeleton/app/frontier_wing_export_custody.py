"""Publish no-clobber local review assets, or verify independently pinned exact bytes."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import os
import stat
import tempfile

from skeleton.app.recovered_evidence import EvidenceError,pin,seal
from skeleton.app.frontier_wing_export import build_archive,MAX_ARCHIVE_BYTES


def _identity(st):
    return st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns


def read_archive(path):
    p=Path(path)
    st=p.lstat()
    if not stat.S_ISREG(st.st_mode) or not 1<=st.st_size<=MAX_ARCHIVE_BYTES:
        raise EvidenceError("unsafe reference asset archive")
    fd=os.open(p,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)|getattr(os,"O_BINARY",0))
    try:
        if _identity(os.fstat(fd))!=_identity(st):
            raise EvidenceError("reference asset changed before read")
        with os.fdopen(fd,"rb",closefd=False) as f:
            raw=f.read(MAX_ARCHIVE_BYTES+1)
        if len(raw)!=st.st_size or _identity(os.fstat(fd))!=_identity(st) or _identity(p.lstat())!=_identity(st):
            raise EvidenceError("reference asset changed during read")
        return raw
    finally:
        os.close(fd)


def publish(path,raw):
    """Same-directory staging + atomic no-clobber hard link on supported FS.

    This is cooperative filesystem custody; no hostile-parent or power-loss
    guarantee is implied. Fail closed where no-clobber link is unsupported.
    """
    p=Path(path)
    if p.suffix.lower()!=".zip" or not p.parent.is_dir() or p.parent.is_symlink():
        raise EvidenceError("existing cooperative export parent and ZIP target required")
    if p.exists() or p.is_symlink():
        raise FileExistsError("reference export cannot overwrite existing target")
    fd,temp=tempfile.mkstemp(prefix=".wing-export-",dir=p.parent)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.link(temp,p)
    finally:
        os.unlink(temp)


def operate(order,path,*,operation,sample_stride,page_frames,allow_reference_defects,
            authorized,expected_archive_sha256=None):
    if authorized is not True:
        raise PermissionError("explicit reference asset operator required")
    if operation not in ("export","verify"):
        raise EvidenceError("unknown reference asset operation")
    observed=None
    if operation=="verify":
        observed=read_archive(path)
        pin(sha256(observed).hexdigest(),expected_archive_sha256)
    elif expected_archive_sha256 is not None:
        raise EvidenceError("new export accepts no previous archive pin")
    raw,manifest=build_archive(order,sample_stride=sample_stride,page_frames=page_frames,
                               allow_reference_defects=allow_reference_defects,authorized=True)
    if operation=="verify":
        if raw!=observed:
            raise EvidenceError("independent source archive reconstruction mismatch")
    else:
        publish(path,raw)
    return seal({"schema":"skeleton.frontier-wing-export.receipt.v1","operation":operation,
                 "archive_sha256":sha256(raw).hexdigest(),"archive_bytes":len(raw),
                 "manifest_digest":manifest["digest"],"pages":len(manifest["pages"]),
                 "unique_samples":manifest["unique_sample_count"],
                 "source_replay_head":manifest["full_source_replay_head"],
                 "reference_invariants_passed":manifest["candidate_reference_invariants_passed"],
                 "native_import_verified":False,"visual_quality_certified":False,
                 "release_certified":False})
