"""Cross-process session fencing by held flock, not merely SQLite CAS."""
from __future__ import annotations
import os,hashlib,time,stat
from contextlib import contextmanager
from pathlib import Path
from .contracts import identifier,Busy,SpineError
from .path_policy import open_private_root,private_file_at

class SessionGate:
    def __init__(self,lock_root:str|Path):
        if os.name!='posix':raise SpineError('session gate requires POSIX')
        import fcntl
        self._fcntl=fcntl
        self._fd=open_private_root(lock_root)
        self._closed=False

    @contextmanager
    def hold(self,session:str,*,deadline_ms:int):
        identifier(session,'session')
        if self._closed:raise SpineError('session gate closed')
        if type(deadline_ms)is not int or not 1<=deadline_ms<=600000:raise SpineError('invalid gate timeout')
        name=hashlib.sha256(session.encode('ascii')).hexdigest()+'.gate'
        try:fd=private_file_at(self._fd,name)
        except FileNotFoundError:
            try:fd=private_file_at(self._fd,name,create=True)
            except FileExistsError:fd=private_file_at(self._fd,name)
        locked=False
        try:
            end=time.monotonic_ns()+deadline_ms*1_000_000
            while True:
                try:self._fcntl.flock(fd,self._fcntl.LOCK_EX|self._fcntl.LOCK_NB);locked=True;break
                except BlockingIOError:
                    if time.monotonic_ns()>=end:raise Busy('session execution gate deadline')
                    time.sleep(.01)
            yield
        finally:
            if locked:self._fcntl.flock(fd,self._fcntl.LOCK_UN)
            os.close(fd)

    def close(self):
        if not self._closed:self._closed=True;os.close(self._fd)
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
