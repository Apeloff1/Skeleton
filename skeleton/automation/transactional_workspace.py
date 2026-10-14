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
MAX_LEASE_PATHS = 256
MAX_ID_BYTES = 256

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
class EditLease:
    lease_id: str
    owner_id: str
    base_digest: str
    paths: tuple[str, ...]
    authority_scope: str = "workspace-edit-proposal-only"

    def __post_init__(self):
        for field, value in (("lease_id", self.lease_id), ("owner_id", self.owner_id)):
            if not isinstance(value, str) or not value or len(value.encode()) > MAX_ID_BYTES:
                raise WorkspaceError(f"invalid {field}")
        if (
            not isinstance(self.base_digest, str)
            or len(self.base_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.base_digest)
        ):
            raise WorkspaceError("invalid lease base digest")
        if (
            not isinstance(self.paths, tuple)
            or not self.paths
            or len(self.paths) > MAX_LEASE_PATHS
        ):
            raise WorkspaceError("invalid lease path set")
        normalized = tuple(sorted(_path(path) for path in self.paths))
        if len(normalized) != len(set(normalized)):
            raise WorkspaceError("duplicate lease path")
        object.__setattr__(self, "paths", normalized)
        if self.authority_scope != "workspace-edit-proposal-only":
            raise WorkspaceError("edit lease cannot grant repository authority")

    @property
    def digest(self) -> str:
        return _digest({
            "lease_id": self.lease_id,
            "owner_id": self.owner_id,
            "base_digest": self.base_digest,
            "paths": self.paths,
            "authority_scope": self.authority_scope,
        })


class EditLeaseRegistry:
    """Shared deterministic path-lease registry for proposal workspaces."""

    def __init__(self):
        self._leases: dict[str, EditLease] = {}
        self._path_owners: dict[str, str] = {}

    def acquire(
        self,
        *,
        lease_id: str,
        owner_id: str,
        base_digest: str,
        paths: tuple[str, ...],
    ) -> EditLease:
        lease = EditLease(lease_id, owner_id, base_digest, paths)
        if lease.lease_id in self._leases:
            raise WorkspaceConflict("lease_id already active")
        conflicts = tuple(path for path in lease.paths if path in self._path_owners)
        if conflicts:
            raise WorkspaceConflict("edit lease path conflict")
        self._leases[lease.lease_id] = lease
        for path in lease.paths:
            self._path_owners[path] = lease.lease_id
        return lease

    def require_active(self, lease: EditLease, *, path: str, base_digest: str) -> None:
        if not isinstance(lease, EditLease):
            raise WorkspaceError("typed edit lease required")
        canonical_path = _path(path)
        active = self._leases.get(lease.lease_id)
        if active != lease:
            raise WorkspaceConflict("edit lease is stale or inactive")
        if lease.base_digest != base_digest:
            raise WorkspaceConflict("edit lease base digest mismatch")
        if canonical_path not in lease.paths:
            raise WorkspaceConflict("path is outside edit lease")
        if self._path_owners.get(canonical_path) != lease.lease_id:
            raise WorkspaceConflict("edit lease path ownership drift")

    def release(self, lease: EditLease) -> None:
        if not isinstance(lease, EditLease):
            raise WorkspaceError("typed edit lease required")
        active = self._leases.get(lease.lease_id)
        if active != lease:
            raise WorkspaceConflict("edit lease is stale or inactive")
        del self._leases[lease.lease_id]
        for path in lease.paths:
            if self._path_owners.get(path) == lease.lease_id:
                del self._path_owners[path]


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
    def __init__(
        self,
        files: Mapping[str, bytes],
        *,
        lease_registry: EditLeaseRegistry | None = None,
    ):
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
        if lease_registry is not None and not isinstance(lease_registry, EditLeaseRegistry):
            raise TypeError("lease_registry must be EditLeaseRegistry")
        self._lease_registry=lease_registry

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

    def _write(self, path: str, content: bytes, *, expected_digest: str | None=None) -> None:
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

    def write(self, path: str, content: bytes, *, expected_digest: str | None=None) -> None:
        if self._lease_registry is not None:
            raise WorkspaceError("lease-aware workspace requires write_leased")
        self._write(path, content, expected_digest=expected_digest)

    def write_leased(
        self,
        lease: EditLease,
        path: str,
        content: bytes,
        *,
        expected_digest: str | None=None,
    ) -> None:
        if self._lease_registry is None:
            raise WorkspaceError("lease registry required")
        self._lease_registry.require_active(
            lease,
            path=path,
            base_digest=self.base_digest,
        )
        self._write(path, content, expected_digest=expected_digest)
        self._ops.append(("lease-bind", _path(path), lease.digest))

    def _delete(self, path: str, *, expected_digest: str) -> None:
        if self._closed: raise WorkspaceError("transaction closed")
        path=_path(path)
        if path not in self._working: raise WorkspaceConflict("unknown path")
        actual=sha256(self._working[path]).hexdigest()
        if expected_digest != actual: raise WorkspaceConflict("stale expected digest")
        del self._working[path]
        self._ops.append(("delete",path,actual,None))

    def delete(self, path: str, *, expected_digest: str) -> None:
        if self._lease_registry is not None:
            raise WorkspaceError("lease-aware workspace requires delete_leased")
        self._delete(path, expected_digest=expected_digest)

    def delete_leased(self, lease: EditLease, path: str, *, expected_digest: str) -> None:
        if self._lease_registry is None:
            raise WorkspaceError("lease registry required")
        self._lease_registry.require_active(
            lease,
            path=path,
            base_digest=self.base_digest,
        )
        self._delete(path, expected_digest=expected_digest)
        self._ops.append(("lease-bind", _path(path), lease.digest))

    def acquire_lease(
        self,
        *,
        lease_id: str,
        owner_id: str,
        paths: tuple[str, ...],
    ) -> EditLease:
        if self._lease_registry is None:
            raise WorkspaceError("lease registry required")
        return self._lease_registry.acquire(
            lease_id=lease_id,
            owner_id=owner_id,
            base_digest=self.base_digest,
            paths=paths,
        )

    def _rollback(self) -> None:
        if self._closed: raise WorkspaceError("transaction closed")
        self._working=dict(self._base); self._ops.clear()

    def rollback(self) -> None:
        if self._lease_registry is not None:
            raise WorkspaceError("lease-aware workspace requires rollback_leased")
        self._rollback()

    def rollback_leased(self, lease: EditLease) -> None:
        if self._lease_registry is None:
            raise WorkspaceError("lease registry required")
        for path in lease.paths:
            self._lease_registry.require_active(
                lease,
                path=path,
                base_digest=self.base_digest,
            )
        self._rollback()
        self._lease_registry.release(lease)

    def _commit(self) -> WorkspaceReceipt:
        if self._closed: raise WorkspaceError("transaction closed")
        changed=tuple(sorted(p for p in set(self._base)|set(self._working) if self._base.get(p)!=self._working.get(p)))
        receipt=WorkspaceReceipt(self.base_digest,self.result_digest,changed,_digest(self._ops))
        self._closed=True
        return receipt

    def commit(self) -> WorkspaceReceipt:
        if self._lease_registry is not None:
            raise WorkspaceError("lease-aware workspace requires commit_leased")
        return self._commit()

    def commit_leased(self, lease: EditLease) -> WorkspaceReceipt:
        if self._lease_registry is None:
            raise WorkspaceError("lease registry required")
        changed=tuple(sorted(p for p in set(self._base)|set(self._working) if self._base.get(p)!=self._working.get(p)))
        for path in changed:
            self._lease_registry.require_active(
                lease,
                path=path,
                base_digest=self.base_digest,
            )
        receipt=self._commit()
        self._lease_registry.release(lease)
        return receipt
