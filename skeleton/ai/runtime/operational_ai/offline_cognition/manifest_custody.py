"""Authenticated source manifest and descriptor-anchored, bounded original-byte ingestion.

The manifest HMAC records explicit trusted operator source approval, but never
proves third-party legal rights. Only independently provisioned operator keys
can authenticate it. No LLM output, network fetch, Path.resolve, symlink
following, recursive traversal or unbounded file read is permitted.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import re
import stat
from dataclasses import dataclass

from .core.contracts import (
    CognitionError, Scope, canonical, hash_bytes, identifier, integer, loads,
    sha, refuse,
)
from .core.sources import bind_source
from .core.evidence_pipeline import EvidenceDocument, EvidenceIndex

MAX_MANIFEST_BYTES=32768
MAX_SOURCE_BYTES=262144
MAX_SOURCES=8
_NAME=re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z",re.ASCII)
_HEX64=re.compile(r"[a-f0-9]{64}\Z",re.ASCII)
_HEX32=re.compile(r"[a-f0-9]{32}\Z",re.ASCII)
_PREFIX=b"skeleton-offline-source-manifest-v1\x00"


def _operator_key(value):
    if type(value) is not bytes or not 32<=len(value)<=4096:
        refuse("external operator secret must be at least 256 bits")
    return value


def _basename(value):
    if (type(value) is not str or _NAME.fullmatch(value) is None or
            value in (".","..") or ".." in value or "\\" in value):
        refuse("source filename must be a strict non-traversing basename")
    return value


@dataclass(frozen=True, slots=True)
class ManifestSource:
    source_id: str
    filename: str
    sha256: str
    rights_receipt_sha256: str
    approved: bool

    def __post_init__(self):
        identifier(self.source_id)
        _basename(self.filename)
        sha(self.sha256)
        sha(self.rights_receipt_sha256)
        if self.approved is not True:
            refuse("operator source approval must be explicit")


@dataclass(frozen=True, slots=True)
class SignedSourceManifest:
    scope: Scope
    issued_at: int
    expires_at: int
    nonce: str
    sources: tuple[ManifestSource, ...]
    signed_record_sha256: str

    def __post_init__(self):
        if type(self.scope) is not Scope:
            refuse("exact signed source principal and model required")
        integer(self.issued_at,minimum=1)
        integer(self.expires_at,minimum=self.issued_at+1)
        if self.expires_at>self.issued_at+3600:
            refuse("source manifest approval exceeds one-hour fence")
        if type(self.nonce) is not str or _HEX32.fullmatch(self.nonce) is None:
            refuse("source nonce malformed")
        if type(self.sources) is not tuple or not 1<=len(self.sources)<=MAX_SOURCES:
            refuse("bounded source manifest required")
        if len({s.source_id for s in self.sources})!=len(self.sources):
            refuse("duplicate source receipts forbidden")
        if len({s.filename for s in self.sources})!=len(self.sources):
            refuse("duplicate source filenames forbidden")
        sha(self.signed_record_sha256)


def verify_signed_manifest(raw, operator_key, *, observed_at):
    """Authenticate HMAC and strict model/principal scope before source reading."""
    key=_operator_key(operator_key)
    integer(observed_at,minimum=1)
    envelope=loads(raw,maximum=MAX_MANIFEST_BYTES)
    if type(envelope) is not dict or set(envelope)!={"record","mac"}:
        refuse("closed signed source-manifest envelope required")
    record=envelope["record"]
    if type(record) is not dict or set(record)!={
        "schema","tenant","subject","model_sha256","tokenizer_sha256",
        "issued_at","expires_at","nonce","sources",
    }:
        refuse("source manifest contains unknown authority fields")
    mac=envelope["mac"]
    if type(mac) is not str or _HEX64.fullmatch(mac) is None:
        refuse("malformed manifest HMAC")
    raw_record=canonical(record,maximum=MAX_MANIFEST_BYTES)
    digest=hmac.new(key,_PREFIX+raw_record,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest,mac):
        refuse("source manifest signature does not match operator key")
    if record["schema"]!="offline-signed-source-manifest.v1":
        refuse("unknown source manifest schema")
    scope=Scope(record["tenant"],record["subject"],
                record["model_sha256"],record["tokenizer_sha256"])
    issued=integer(record["issued_at"],minimum=1)
    expires=integer(record["expires_at"],minimum=issued+1)
    if expires>issued+3600 or not issued<=observed_at<expires:
        refuse("source manifest is expired, premature or unbounded")
    rows=record["sources"]
    if type(rows) is not list or not 1<=len(rows)<=MAX_SOURCES:
        refuse("finite source receipts required")
    checked=[]
    for item in rows:
        if type(item) is not dict or set(item)!={
            "source_id","filename","sha256","rights_receipt_sha256","approved",
        }:
            refuse("unrecognized source receipt fields")
        checked.append(ManifestSource(**item))
    return SignedSourceManifest(scope,issued,expires,record["nonce"],
                                tuple(checked),hash_bytes(raw_record))


def sign_manifest_for_operator(record, operator_key):
    """Used exclusively by a trusted operator CLI, never a model/tool response."""
    _operator_key(operator_key)
    if type(record) is not dict:
        refuse("typed source approval record required")
    raw=canonical(record,maximum=MAX_MANIFEST_BYTES)
    mac=hmac.new(operator_key,_PREFIX+raw,hashlib.sha256).hexdigest()
    return canonical({"record":record,"mac":mac},maximum=MAX_MANIFEST_BYTES)


def _verify_regular(st, *, operator_uid):
    if not stat.S_ISREG(st.st_mode):
        refuse("source must be regular file, not symlink, FIFO or device")
    if st.st_nlink!=1 or st.st_uid!=operator_uid:
        refuse("source must be singly linked and owned by operator")
    if st.st_mode & 0o022:
        refuse("source has group/world write permissions")
    if not 1<=st.st_size<=MAX_SOURCE_BYTES:
        refuse("source exceeds bounded byte ceiling")


def _read_file_anchored(root_fd, entry, *, operator_uid):
    flags=os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd=os.open(entry.filename,flags,dir_fd=root_fd)
    except OSError as exc:
        raise CognitionError("source cannot be safely opened") from exc
    try:
        before=os.fstat(fd)
        _verify_regular(before,operator_uid=operator_uid)
        content=bytearray()
        while len(content)<=before.st_size:
            chunk=os.read(fd,min(65536,before.st_size+1-len(content)))
            if not chunk:
                break
            content.extend(chunk)
        after=os.fstat(fd)
        try:
            current=os.stat(entry.filename,dir_fd=root_fd,follow_symlinks=False)
        except OSError as exc:
            raise CognitionError("source path changed during read") from exc
        stable=("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns","st_mode")
        if any(getattr(before,field)!=getattr(after,field) for field in stable):
            refuse("original source changed while read")
        if any(getattr(after,field)!=getattr(current,field) for field in stable):
            refuse("source path replaced between open and verification")
        if len(content)!=before.st_size:
            refuse("source read size differs from stable original")
        raw=bytes(content)
        if hash_bytes(raw)!=entry.sha256:
            refuse("source bytes differ from signed manifest digest")
        return raw
    finally:
        os.close(fd)


def ingest_authorized_sources(source_root,manifest,*,scope,observed_at):
    """Read each signed original from a single pinned directory descriptor."""
    if type(manifest) is not SignedSourceManifest or type(scope) is not Scope:
        refuse("typed signed source and caller scope required")
    scope.assert_same(manifest.scope)
    integer(observed_at,minimum=1)
    if not manifest.issued_at<=observed_at<manifest.expires_at:
        refuse("signed source approval expired before file read")
    if not isinstance(source_root,(str,Path)):
        refuse("trusted absolute source root required")
    path=os.fspath(source_root)
    if not os.path.isabs(path) or "\x00" in path:
        refuse("source root must be an explicit absolute path")
    # Pin EVERY path component, including intermediate parents. A final-
    # component O_NOFOLLOW alone would allow a malicious symlink ancestor.
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.path_policy import open_private_root
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import SpineError
    try:
        root_fd=open_private_root(path)
    except (OSError,ValueError,SpineError) as exc:
        raise CognitionError("operator source directory cannot be safely anchored") from exc
    try:
        directory=os.fstat(root_fd)
        if (not stat.S_ISDIR(directory.st_mode) or
            directory.st_uid!=os.getuid() or directory.st_mode&0o022):
            refuse("operator source directory cannot be group/world writable")
        documents=[]
        for entry in manifest.sources:
            raw=_read_file_anchored(root_fd,entry,operator_uid=os.getuid())
            receipt=bind_source(raw,source_id=entry.source_id,
                   tenant=scope.tenant,subject=scope.subject,approved=True)
            documents.append(EvidenceDocument(receipt,raw))
        current=os.stat(path,follow_symlinks=False)
        if (directory.st_dev,directory.st_ino)!=(current.st_dev,current.st_ino):
            refuse("source root replaced during source read")
        return EvidenceIndex(tuple(documents),tenant=scope.tenant,
                             subject=scope.subject)
    except OSError as exc:
        raise CognitionError("source root changed during read") from exc
    finally:
        os.close(root_fd)
