"""Master-key descriptor custody and per-tenant/user/model HKDF attenuation."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os,stat
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

class MemoryKeyError(ValueError):pass

@dataclass(frozen=True,slots=True)
class KeyMaterial:
    master:bytes
    epoch:int
    def __post_init__(self):
        if type(self.master) is not bytes or len(self.master)!=32:
            raise MemoryKeyError('memory requires exactly 256-bit independently provided master key')
        if type(self.epoch) is not int or not 1<=self.epoch<=2**32-1:
            raise MemoryKeyError('invalid key epoch')

    def derive(self,tenant:str,user:str,model_sha:str)->bytes:
        for item in (tenant,user,model_sha):
            if not isinstance(item,str) or not item or len(item)>128 or '\x00' in item:
                raise MemoryKeyError('invalid encrypted-memory identity')
        context=(tenant+'\x00'+user+'\x00'+model_sha+'\x00'+str(self.epoch)).encode()
        return HKDF(algorithm=hashes.SHA256(),length=32,
                    salt=sha256(b'Skeleton.offline.memory.kdf.v1').digest(),
                    info=b'Skeleton.sealed-memory.v1'+context).derive(self.master)


def load_key_file(path:str|Path,*,epoch:int=1)->KeyMaterial:
    p=Path(path).absolute()
    if p.is_symlink() or not p.is_file():raise MemoryKeyError('memory key file must be regular, not symlink')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|getattr(os,'O_NONBLOCK',0))
    try:
        s=os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_size!=32 or s.st_mode&0o077 or s.st_nlink!=1:
            raise MemoryKeyError('memory key file must be private 0600, exactly 32 bytes')
        raw=os.read(fd,33)
        if len(raw)!=32:raise MemoryKeyError('invalid key file length')
        return KeyMaterial(raw,epoch)
    finally:os.close(fd)
