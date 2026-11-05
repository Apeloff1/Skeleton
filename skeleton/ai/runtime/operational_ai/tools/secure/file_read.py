"""Descriptor-anchored, read-only tools for explicit operator source scopes."""
from __future__ import annotations
import os,stat
from pathlib import Path
from .spec import ToolError

class BoundedFileReader:
    def __init__(self,root:str|Path,*,max_bytes:int=128_000):
        if os.name!='posix' or not hasattr(os,'O_NOFOLLOW'):
            raise ToolError('read-only file tool requires POSIX nofollow')
        if type(max_bytes) is not int or not 1<=max_bytes<=1_048_576:
            raise ToolError('invalid file read cap')
        self.root=Path(root).absolute();self.maximum=max_bytes
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
        try:
            for part in self.root.parts[1:]:
                nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=nxt
            self._rootfd=fd
        except BaseException:
            os.close(fd);raise

    def read_text(self,relative:str)->dict:
        if not isinstance(relative,str) or not relative or len(relative)>512 or '\\' in relative:
            raise ToolError('noncanonical requested path')
        parts=relative.split('/')
        if any(x in ('','.','..') or not x.isascii() for x in parts):
            raise ToolError('invalid tool path segments')
        fd=os.dup(self._rootfd)
        child=None
        try:
            for part in parts[:-1]:
                nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=nxt
            child=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
            st=os.fstat(child)
            if not stat.S_ISREG(st.st_mode) or st.st_size>self.maximum:
                raise ToolError('requested input not a bounded regular file')
            chunks=[];left=self.maximum+1
            while left:
                data=os.read(child,min(left,65536))
                if not data:break
                chunks.append(data);left-=len(data)
            raw=b''.join(chunks)
            if len(raw)>self.maximum:raise ToolError('read exceeded file ceiling')
            import hashlib
            return {'text':raw.decode('utf-8'),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
        finally:
            if child is not None:os.close(child)
            os.close(fd)

    def close(self)->None:os.close(self._rootfd)
