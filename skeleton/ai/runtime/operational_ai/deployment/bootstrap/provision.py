"""Secure first-install provisioning for native offline AI.

Existing provider/model credentials are never read or replaced. Key bytes are
OS-CSPRNG generated, written exclusively to a private file, fsynced, and never
returned in a receipt or log. State directory and key parent must be on
operator-chosen trusted paths, outside source Git.
"""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
import stat
from ...model.gguf.file_guard import open_trusted_root
from ..install.installer import _valid_name, InstallError


class ProvisionError(RuntimeError):
    pass


@dataclass(frozen=True,slots=True)
class ProvisionReceipt:
    state_dir:str
    key_path:str
    key_bytes:int=32
    state_mode:str='0700'
    key_mode:str='0600'
    status:str='operator-state-provisioned-no-model-qualification'

    def to_record(self)->dict:
        return {key:getattr(self,key) for key in self.__dataclass_fields__}


def provision(state_parent:Path|str, state_name:str, key_parent:Path|str,
              key_name:str='memory.key')->ProvisionReceipt:
    """Create private state and one 256-bit key with exclusive no-follow IO."""
    try:
        state_name=_valid_name(state_name)
        key_name=_valid_name(key_name)
    except InstallError as exc:
        raise ProvisionError('invalid operator-provisioning path') from exc
    if (Path(state_parent).absolute()/state_name)==(Path(key_parent).absolute()/key_name):
        raise ProvisionError('key must be separate from state directory')
    parent_fd=open_trusted_root(state_parent)
    try:
        keys_fd=open_trusted_root(key_parent)
    except BaseException:
        os.close(parent_fd)
        raise
    try:
        for fd in (parent_fd,keys_fd):
            if os.fstat(fd).st_mode&0o077:
                raise ProvisionError('operator parents must be private directories')
        for fd,name in ((parent_fd,state_name),(keys_fd,key_name)):
            try:os.stat(name,dir_fd=fd,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise ProvisionError('operator state or key destination already exists')
        # Never emit key contents even on an exception. A failed later step may
        # leave an unreferenced private key, rather than deleting a possibly
        # externally copied secret on an ambiguous crash boundary.
        secret=os.urandom(32)
        out=os.open(key_name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                    0o600,dir_fd=keys_fd)
        try:
            offset=0
            while offset<32:
                count=os.write(out,secret[offset:])
                if count<=0:raise ProvisionError('cannot securely publish local key')
                offset+=count
            os.fsync(out)
        finally:os.close(out)
        os.fsync(keys_fd)
        os.mkdir(state_name,0o700,dir_fd=parent_fd)
        os.fsync(parent_fd)
        fd=os.open(state_name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent_fd)
        try:
            if os.fstat(fd).st_mode&0o077:
                raise ProvisionError('new AI state directory is not private')
            os.fsync(fd)
        finally:os.close(fd)
        return ProvisionReceipt(str(Path(state_parent).absolute()/state_name),
                                str(Path(key_parent).absolute()/key_name))
    except OSError as exc:
        raise ProvisionError('state or key provisioning refused; inspect private directories') from exc
    finally:
        os.close(keys_fd)
        os.close(parent_fd)
