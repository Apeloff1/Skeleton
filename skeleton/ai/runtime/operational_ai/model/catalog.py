"""Operator-provisioned checkpoint registry with no downloading or fallback.

Catalogue entries are opaque paths in a trusted local directory. Admission
requires an expected SHA256, a verified license, and a strict byte budget.
No model name can resolve to an arbitrary URL or provider-backed default.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
from typing import BinaryIO
from ..authority.canonical import ContractViolation,require_digest,require_small_text
from ..authority.identity import require_id

MAX_CHECKPOINT = 256_000_000


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    name: str
    filename: str
    sha256: str
    bytes: int
    license: str
    tokenizer_sha256: str | None = None

    def __post_init__(self):
        require_id(self.name,field="model name")
        if not isinstance(self.filename,str) or not self.filename.endswith(".json") or len(self.filename)>200:
            raise ContractViolation("native checkpoint filename must be .json")
        if self.filename in {".",".."} or "/" in self.filename or "\\" in self.filename:
            raise ContractViolation("model filename cannot escape root")
        require_digest(self.sha256,field="model checkpoint SHA256")
        if type(self.bytes) is not int or not 1<=self.bytes<=MAX_CHECKPOINT:
            raise ContractViolation("model checkpoint byte ceiling exceeded")
        require_small_text(self.license,field="verified model license",maximum=256)
        if self.tokenizer_sha256 is not None:
            require_digest(self.tokenizer_sha256,field="tokenizer identity")


class ModelCatalog:
    def __init__(self,root:str|Path,artifacts:list[ModelArtifact]):
        if os.name!="posix" or not getattr(os,"O_NOFOLLOW",0):
            raise ContractViolation("descriptor-safe model loading requires POSIX")
        self.root=Path(root).absolute()
        if not self.root.is_dir() or self.root.is_symlink() or self.root.stat().st_mode & 0o022:
            raise ContractViolation("model directory must exist, be trusted and not be writable by other users")
        self.artifacts={a.name:a for a in artifacts}
        if not artifacts or len(self.artifacts)!=len(artifacts):
            raise ContractViolation("model registry cannot be empty or duplicate")

    def _open_root(self)->int:
        """Pin every ancestor via openat; reject symlinked directory swaps."""
        current=os.open("/",os.O_RDONLY|os.O_DIRECTORY)
        try:
            for part in self.root.parts[1:]:
                next_fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current)
                os.close(current)
                current=next_fd
            return current
        except BaseException:
            os.close(current)
            raise

    def verified_bytes(self,name:str)->tuple[ModelArtifact,bytes]:
        """Read and hash one immutable checkpoint from an anchored descriptor."""
        require_id(name,field="model name")
        if name not in self.artifacts:
            raise ContractViolation("unregistered model; no fallback")
        artifact=self.artifacts[name]
        fd=self._open_root()
        try:
            child=os.open(artifact.filename,os.O_RDONLY|os.O_NOFOLLOW|
                          getattr(os,"O_NONBLOCK",0),dir_fd=fd)
            try:
                info=os.fstat(child)
                if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_size!=artifact.bytes:
                    raise ContractViolation("model file is not regular, fixed-size, or write-protected")
                digest=hashlib.sha256()
                parts=[]
                remaining=artifact.bytes
                while remaining:
                    block=os.read(child,min(1024*1024,remaining))
                    if not block:
                        raise ContractViolation("checkpoint changed during verification")
                    digest.update(block)
                    parts.append(block)
                    remaining-=len(block)
                if os.read(child,1):
                    raise ContractViolation("checkpoint grew during verification")
                if digest.hexdigest()!=artifact.sha256:
                    raise ContractViolation("checkpoint digest mismatch")
                if os.fstat(child).st_size!=artifact.bytes:
                    raise ContractViolation("checkpoint changed while reading")
                return artifact,b"".join(parts)
            finally:
                os.close(child)
        finally:
            os.close(fd)

    def verify(self,name:str)->tuple[ModelArtifact,Path]:
        artifact,_=self.verified_bytes(name)
        return artifact,self.root/artifact.filename
