"""Finite TAR header inventory, never extraction or symlink traversal."""
from __future__ import annotations
from collections import Counter
import re
from .research_projection import ResearchFormatError, ResearchProjection, project_lines

TAR_TYPES=frozenset({"application/x-tar","application/tar"})
_SUFFIX=re.compile(r"^\.[a-z0-9]{1,12}$")
_BLOCK=512


def _octal(data: bytes)->int:
    value=data.strip(b" \x00")
    if not value or len(value)>12 or any(x not in b"01234567" for x in value):
        raise ResearchFormatError("invalid TAR numeric field")
    return int(value,8)


def extract_tar(body: bytes, *, max_chars: int=524288)->ResearchProjection:
    if (type(body) is not bytes or len(body)>2_097_152
            or len(body)<1024 or len(body)%_BLOCK
            or type(max_chars) is not int or max_chars<1):
        raise ResearchFormatError("TAR source size/alignment invalid")
    cursor=0
    count=0
    total=0
    suffixes=Counter()
    seen=set()
    while cursor+_BLOCK<=len(body):
        header=body[cursor:cursor+_BLOCK]
        if header==b"\x00"*_BLOCK:
            if any(body[cursor:]):
                raise ResearchFormatError("TAR nonzero trailing data")
            break
        count+=1
        if count>256:
            raise ResearchFormatError("TAR member count exceeded")
        name_bytes=header[:100].split(b"\x00",1)[0]
        try:
            name=name_bytes.decode("utf-8","strict")
        except UnicodeError as exc:
            raise ResearchFormatError("TAR filename encoding invalid") from exc
        if (not name or len(name)>100 or name.startswith(("/", "\\"))
                or "\\" in name or ".." in name.split("/")):
            raise ResearchFormatError("unsafe TAR source path")
        if name.casefold() in seen:
            raise ResearchFormatError("TAR path identity collision")
        seen.add(name.casefold())
        checksum=_octal(header[148:156])
        check=sum(header[:148])+sum(b" "*8)+sum(header[156:])
        if checksum!=check:
            raise ResearchFormatError("TAR header checksum mismatch")
        size=_octal(header[124:136])
        if size>2_097_152:
            raise ResearchFormatError("TAR member declares oversized body")
        kind=header[156:157]
        if kind not in (b"0",b"\x00",b"5"):
            raise ResearchFormatError("TAR link/device/PAX entries denied")
        if kind==b"5" and size:
            raise ResearchFormatError("TAR directory with data denied")
        total+=size
        if total>2_097_152:
            raise ResearchFormatError("TAR aggregate advertised size exceeded")
        if kind!=b"5":
            base=name.rsplit("/",1)[-1]
            suffix=("."+base.rsplit(".",1)[-1].lower()) if "." in base else "[none]"
            if not _SUFFIX.fullmatch(suffix):
                suffix="[other]"
            suffixes[suffix]+=1
        cursor+=_BLOCK+((size+_BLOCK-1)//_BLOCK)*_BLOCK
        if cursor>len(body):
            raise ResearchFormatError("truncated TAR member payload")
    if not count:
        raise ResearchFormatError("TAR archive contains no indexed members")
    rows=["Archive: TAR inventory only",
          f"Finite entries: {count}; claimed bytes: {total}"]
    rows.extend(f"Extension class {key}: {value}"
                for key,value in sorted(suffixes.items()))
    rows.append("Archive members, symlinks and executable content: not opened")
    return project_lines(rows,title="TAR archive inventory",max_chars=max_chars)
