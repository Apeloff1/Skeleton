"""Deterministic transactional workspace for autonomous repository engineering."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Mapping

MAX_FILES = 512
MAX_PATH_BYTES = 512
MAX_CONTENT_BYTES = 2_000_000

class WorkspaceError(ValueError): pass
class WorkspaceConflict(WorkspaceError): pass
class WorkspaceBudgetExceeded(WorkspaceError): pass

def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def _path(path: str) -> str:
    if not isinstance(path, str) or not path or len(path.encode()) > MAX_PATH_BYTES:
        raise WorkspaceError("invalid path")
    if path.startswith(("/", "\\")) or "\\" in path:
        raise WorkspaceError("path must be repository-relative POSIX")
    parts=path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise WorkspaceError("path traversal or ambiguous path")
    return path

@dataclass(frozen=True)
class FileState:
    path: str
    content_digest: str
    content: bytes
    def __post_init__(self):
        _path(self.path)
        if not isinstance(self.content, bytes) or len(self.content) > MAX_CONTENT_BYTES:
            raise WorkspaceBudgetExceeded("content budget exceeded")
        if sha256(self.content).hexdigest() != self.content_digest:
            raise WorkspaceError("content digest mismatch")

@dataclass(frozen=True)
class WorkspaceReceipt:
    base_digest: str
    result_digest: str
    changed_paths: tuple[str, ...]
    operation_digest: str
    authority_scope: str = "workspace-proposal-only"
    def __post_init__(self):
        if self.authority_scope != "workspace-proposal-only":
            raise WorkspaceError("workspace receipt cannot grant execution authority")

class TransactionalWorkspace:
    """In-memory proposal transaction. Commit returns evidence, never repository authority."""
    def __init__(self, files: Mapping[str, bytes]):
        if not isinstance(files, Mapping) or len(files) > MAX_FILES:
            raise WorkspaceBudgetExceeded("file budget exceeded")
        normalized={}
        for p,c in files.items():
            p=_path(p)
            if not isinstance(c, bytes) or len(c)>MAX_CONTENT_BYTES:
                raise WorkspaceBudgetExceeded("content budget exceeded")
            normalized[p]=bytes(c)
        self._base=MappingProxyType(dict(normalized))
        self._working=dict(normalized)
        self._closed=False
        self._ops=[]

    @staticmethod
    def _snapshot_digest(files: Mapping[str, bytes]) -> str:
        return _digest([{"path":p,"content":sha256(files[p]).hexdigest()} for p in sorted(files)])

    @property
    def base_digest(self) -> str: return self._snapshot_digest(self._base)
    @property
    def result_digest(self) -> str: return self._snapshot_digest(self._working)

    def read(self, path: str) -> FileState:
        path=_path(path)
        if path not in self._working: raise WorkspaceError("unknown path")
        c=self._working[path]
        return FileState(path,sha256(c).hexdigest(),c)

    def write(self, path: str, content: bytes, *, expected_digest: str | None=None) -> None:
        if self._closed: raise WorkspaceError("transaction closed")
        path=_path(path)
        if not isinstance(content, bytes) or len(content)>MAX_CONTENT_BYTES:
            raise WorkspaceBudgetExceeded("content budget exceeded")
        if path not in self._working and len(self._working)>=MAX_FILES:
            raise WorkspaceBudgetExceeded("file budget exceeded")
        prior=self._working.get(path)
        actual=sha256(prior).hexdigest() if prior is not None else None
        if expected_digest != actual:
            raise WorkspaceConflict("stale or missing expected digest")
        self._working[path]=bytes(content)
        self._ops.append(("write",path,actual,sha256(content).hexdigest()))

    def delete(self, path: str, *, expected_digest: str) -> None:
        if self._closed: raise WorkspaceError("transaction closed")
        path=_path(path)
        if path not in self._working: raise WorkspaceConflict("unknown path")
        actual=sha256(self._working[path]).hexdigest()
        if expected_digest != actual: raise WorkspaceConflict("stale expected digest")
        del self._working[path]
        self._ops.append(("delete",path,actual,None))

    def rollback(self) -> None:
        if self._closed: raise WorkspaceError("transaction closed")
        self._working=dict(self._base); self._ops.clear()

    def commit(self) -> WorkspaceReceipt:
        if self._closed: raise WorkspaceError("transaction closed")
        changed=tuple(sorted(p for p in set(self._base)|set(self._working) if self._base.get(p)!=self._working.get(p)))
        receipt=WorkspaceReceipt(self.base_digest,self.result_digest,changed,_digest(self._ops))
        self._closed=True
        return receipt
