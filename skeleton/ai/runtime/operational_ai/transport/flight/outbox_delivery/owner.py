"""Persistent principal/model ownership for immutable on-device event spools.

A pre-existing unowned spool is never adopted. All writes are descriptor
anchored and serialize across independent processes under a kernel flock.
"""
from __future__ import annotations
from contextlib import contextmanager
from hashlib import sha256
import fcntl, json, os, stat
from .contracts import DeliveryHeld
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import canonical

LOCK = '.spool.lock'
OWNER = '.spool.owner'


def _verify(fd:int, *, empty:bool=False)->None:
    st=os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_mode & 0o077 or st.st_uid!=os.getuid():
        raise DeliveryHeld('private spool custody is not a unique owner-only file')
    if empty and st.st_size!=0:
        raise DeliveryHeld('spool lock file was modified outside custody')
    if st.st_size>8192:
        raise DeliveryHeld('spool custody record exceeds bound')


@contextmanager
def guard(root_fd:int):
    fd=os.open(LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0),0o600,dir_fd=root_fd)
    try:
        _verify(fd,empty=True)
        fcntl.flock(fd,fcntl.LOCK_EX)
        _verify(fd,empty=True)
        yield
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)


def _read(root_fd:int,name:str)->bytes:
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0),dir_fd=root_fd)
    try:
        _verify(fd)
        size=os.fstat(fd).st_size
        raw=os.read(fd,size+1)
        if len(raw)!=size or os.fstat(fd).st_size!=size:
            raise DeliveryHeld('mutable or truncated spool identity')
        return raw
    finally:os.close(fd)


def bind(root_fd:int,identity)->dict:
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity
    if not isinstance(identity,Identity):
        raise DeliveryHeld('spool must bind a complete AI principal/model identity')
    material={'schema':'skeleton.ai.private-spool-owner.v1',
              'tenant':identity.tenant,'subject':identity.subject,
              'model_sha256':identity.model_sha256,
              'tokenizer_sha256':identity.tokenizer_sha256}
    raw=canonical(material,ceiling=8192)
    with guard(root_fd):
        try:saved=_read(root_fd,OWNER)
        except FileNotFoundError:
            existing=[name for name in os.listdir(root_fd) if name not in (LOCK,)]
            if existing:
                raise DeliveryHeld('pre-existing unbound event spool requires manual migration')
            fd=os.open(OWNER,os.O_WRONLY|os.O_NOFOLLOW|os.O_CREAT|os.O_EXCL|getattr(os,'O_CLOEXEC',0),0o600,dir_fd=root_fd)
            try:
                if os.write(fd,raw)!=len(raw):raise DeliveryHeld('incomplete spool ownership publication')
                os.fsync(fd);os.fsync(root_fd)
            finally:os.close(fd)
            saved=raw
        if saved!=raw:
            raise DeliveryHeld('AI spool tenant/user/model identity changed')
    return {'status':'bound-to-principal-and-model', 'owner_digest':sha256(raw).hexdigest()}


def require(root_fd:int,identity)->None:
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity
    if not isinstance(identity,Identity):raise DeliveryHeld('invalid spool owner authority')
    expected=canonical({'schema':'skeleton.ai.private-spool-owner.v1',
       'tenant':identity.tenant,'subject':identity.subject,
       'model_sha256':identity.model_sha256,
       'tokenizer_sha256':identity.tokenizer_sha256},ceiling=8192)
    if _read(root_fd,OWNER)!=expected:
        raise DeliveryHeld('spool owner record does not match active identity')
