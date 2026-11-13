"""Descriptor-anchored bounded read-only file tool. No symlink following."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import stat
from ..authority.canonical import ContractViolation

MAX_READ=128*1024


def safe_path(relative:str)->list[str]:
    if (type(relative) is not str or not relative or len(relative)>1024 or
        relative.startswith("/") or "\\" in relative or
        any(ord(c)<32 for c in relative) or
        any(part in {"",".",".."} for part in relative.split("/"))):
        raise ContractViolation("unsafe tool path")
    return relative.split("/")


class ReadOnlyWorkspace:
    def __init__(self,root:str|Path):
        root=Path(root).absolute()
        if not root.is_dir() or root.is_symlink():
            raise ContractViolation("file tool requires a regular workspace root")
        if os.name!="posix" or not getattr(os,"O_NOFOLLOW",0):
            raise ContractViolation("descriptor-anchored file tool is POSIX only")
        self.root=root

    def read(self,relative:str,*,maximum:int=32*1024)->dict[str,object]:
        if type(maximum) is not int or not 1<=maximum<=MAX_READ:
            raise ContractViolation("file tool read budget invalid")
        parts=safe_path(relative)
        current=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current)
                os.close(current)
                current=child
            descriptor=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|
                getattr(os,"O_NONBLOCK",0),dir_fd=current)
            try:
                info=os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_size>maximum or info.st_size<0:
                    raise ContractViolation("file tool refuses special or oversized source")
                raw=b""
                while len(raw)<info.st_size:
                    part=os.read(descriptor,min(8192,info.st_size-len(raw)))
                    if not part:
                        raise ContractViolation("file changed during read")
                    raw+=part
                if os.read(descriptor,1):
                    raise ContractViolation("file grew during read")
            finally:
                os.close(descriptor)
        finally:
            os.close(current)
        return {"path":relative,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
                "content":raw.decode("utf-8",errors="replace"),"trust":"local-file-data"}

    @staticmethod
    def definition():
        from .catalog import ToolDefinition
        return ToolDefinition("read_workspace_file",{"type":"object",
            "properties":{"path":{"type":"string","maxLength":1024},
                          "maximum":{"type":"integer","minimum":1,"maximum":MAX_READ}},
            "required":["path"]},"readonly",description="Read bounded local text; no symlinks")

    def execute(self,arguments:dict)->dict:
        return self.read(arguments["path"],maximum=arguments.get("maximum",32*1024))
