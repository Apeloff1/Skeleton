"""Read only exact tracked Git objects, never working-tree files or symlinks."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import re
import subprocess
import selectors
import time
from .contracts import GitSourceError,commit_sha,git_path

_OID=re.compile(r'^[0-9a-f]{40}(?:[0-9a-f]{24})?$')


@dataclass(frozen=True,slots=True)
class GitBlob:
    path:str
    oid:str
    mode:str
    raw:bytes
    sha256:str


class GitSource:
    def __init__(self, root:str|Path, *, commit:str, maximum_paths:int=100000,
                 maximum_inventory_bytes:int=20*1024*1024):
        self.root=Path(root).absolute()
        self.commit=commit_sha(commit)
        if (type(maximum_paths)is not int or not 1<=maximum_paths<=1000000 or
            type(maximum_inventory_bytes)is not int or not 1024<=maximum_inventory_bytes<=64*1024*1024):
            raise GitSourceError('invalid bounded Git inventory policy')
        self.maximum_paths=maximum_paths
        self.maximum_inventory_bytes=maximum_inventory_bytes
        if not self.root.is_dir() or self.root.is_symlink():
            raise GitSourceError('Git source root must be an existing directory')
        resolved=self._command('rev-parse','--verify',self.commit+'^{commit}',ceiling=256).decode().strip()
        if resolved!=self.commit:
            raise GitSourceError('Git source must name an exact full commit object')

    def _command(self,*args:str,ceiling:int=1024*1024)->bytes:
        if type(ceiling)is not int or not 0<ceiling<=64*1024*1024:
            raise GitSourceError('invalid Git read ceiling')
        env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
        env.update(GIT_NO_REPLACE_OBJECTS='1',GIT_CONFIG_NOSYSTEM='1',
                   GIT_CONFIG_GLOBAL=os.devnull,GIT_OPTIONAL_LOCKS='0',
                   GIT_TERMINAL_PROMPT='0')
        command=['git','-C',str(self.root),*args]
        try:
            proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,env=env)
        except (OSError,subprocess.SubprocessError) as exc:
            raise GitSourceError('Git source read unavailable') from exc
        parts=[];received=0;errors=bytearray();code=None
        deadline=time.monotonic()+20
        selector=selectors.DefaultSelector()
        try:
            for pipe,role in ((proc.stdout,'stdout'),(proc.stderr,'stderr')):
                os.set_blocking(pipe.fileno(),False)
                selector.register(pipe,selectors.EVENT_READ,role)
            while selector.get_map():
                remain=deadline-time.monotonic()
                if remain<=0:raise GitSourceError('bounded Git command timed out')
                for key,_ in selector.select(timeout=min(remain,.2)):
                    chunk=os.read(key.fileobj.fileno(),65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif key.data=='stdout':
                        received+=len(chunk)
                        if received>ceiling:
                            raise GitSourceError('Git output exceeds bounded source read')
                        parts.append(chunk)
                    else:
                        errors.extend(chunk)
                        if len(errors)>8192:
                            raise GitSourceError('Git stderr exceeds finite bound')
            remain=deadline-time.monotonic()
            if remain<=0:raise GitSourceError('Git command timeout')
            code=proc.wait(timeout=remain)
        except (OSError,subprocess.SubprocessError) as exc:
            raise GitSourceError('Git source read failed') from exc
        finally:
            selector.close()
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
            proc.stdout.close();proc.stderr.close()
        output=b''.join(parts)
        if code:
            raise GitSourceError('Git object not accessible or malformed')
        return output

    def inventory(self)->dict[str,tuple[str,str]]:
        raw=self._command('ls-tree','-r','-z','--full-tree',self.commit,
                          ceiling=self.maximum_inventory_bytes)
        records={}
        for entry in raw.split(b'\x00'):
            if not entry:continue
            try:
                left,path_raw=entry.split(b'\t',1)
                mode,kind,oid=left.decode('ascii').split(' ')
                path=path_raw.decode('utf8','strict')
            except (ValueError,UnicodeError) as exc:
                raise GitSourceError('Git tree entry encoding is not canonical') from exc
            if path in records or not _OID.fullmatch(oid):
                raise GitSourceError('duplicate or invalid Git tree object')
            records[path]=(mode,oid)
            if len(records)>self.maximum_paths:
                raise GitSourceError('Git inventory exceeds bounded file count')
        return records

    def read(self,path:str, inventory:dict[str,tuple[str,str]], *, maximum_bytes:int)->GitBlob:
        git_path(path)
        if path not in inventory:raise GitSourceError('source path is not tracked at pinned commit')
        mode,oid=inventory[path]
        if mode not in ('100644','100755'):
            raise GitSourceError('symlink, submodule or nonregular Git object excluded')
        size_raw=self._command('cat-file','-s',oid,ceiling=32).strip()
        try:size=int(size_raw)
        except ValueError as exc:raise GitSourceError('invalid Git blob byte count') from exc
        if not 0<size<=maximum_bytes:
            raise GitSourceError('tracked AI source exceeds authorized byte budget')
        raw=self._command('cat-file','blob',oid,ceiling=maximum_bytes)
        if len(raw)!=size:raise GitSourceError('Git blob changed between size and read')
        return GitBlob(path,oid,mode,raw,sha256(raw).hexdigest())
