"""Finite inert proto3 declaration and service-interface inventory.

This is deliberately a conservative textual structural projection, not a
Protocol Buffers compiler. Imported files, source-defined options,
extensions, descriptors, services and remote references cannot be loaded,
compiled, invoked or transformed into authorized clients.
"""
from __future__ import annotations

from collections import Counter
import re

from .research_projection import ResearchFormatError,ResearchProjection,check_text,project_lines

PROTO_MEDIA_TYPES=frozenset({"text/x-protobuf","application/x-protobuf-schema"})
_MAGIC=re.compile(r'^\s*syntax\s*=\s*"proto3"\s*;\s*$')
_PACKAGE=re.compile(r"^\s*package\s+([A-Za-z_][A-Za-z0-9_.]{0,255})\s*;\s*$")
_CLASS=re.compile(r"^\s*(message|enum|service)\s+([A-Za-z_][A-Za-z0-9_]{0,127})\s*\{\s*$")
_RPC=re.compile(
    r"^\s*rpc\s+([A-Za-z_][A-Za-z0-9_]{0,127})\s*"
    r"\(\s*(?:stream\s+)?([.A-Za-z_][A-Za-z0-9_.]{0,127})\s*\)"
    r"\s+returns\s*\(\s*(?:stream\s+)?([.A-Za-z_][A-Za-z0-9_.]{0,127})\s*\)\s*;\s*$"
)
_MAX_ROWS=16384
_MAX_DECLS=256
_MAX_RPCS=512


def _strip_comment(line:str)->str:
    quote=False
    escaped=False
    for index,char in enumerate(line):
        if char=='"' and not escaped:
            quote=not quote
        if char=="\\" and not escaped:
            escaped=True
            continue
        if char=="/" and not quote and line[index:index+2]=="//":
            return line[:index]
        escaped=False
    return line


def extract_proto(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    lines=raw.lstrip("\ufeff").splitlines()
    if not 1<=len(lines)<=_MAX_ROWS:
        raise ResearchFormatError("protobuf source line capacity exceeded")
    observed_magic=False
    package=""
    types=Counter()
    declarations=[]
    rpc_count=0
    import_count=0
    depth=0
    in_multiline_comment=False
    for line_number,original in enumerate(lines,1):
        if len(original)>8192:
            raise ResearchFormatError("protobuf source line width exceeded")
        text=original.strip()
        if in_multiline_comment:
            if "*/" in text:
                in_multiline_comment=False
            continue
        if text.startswith("/*"):
            if "*/" not in text:
                in_multiline_comment=True
            continue
        text=_strip_comment(original).strip()
        if not text:
            continue
        if not observed_magic:
            if not _MAGIC.fullmatch(text):
                raise ResearchFormatError("proto3 syntax declaration required first")
            observed_magic=True
            continue
        match=_PACKAGE.fullmatch(text)
        if match and depth==0:
            if package:
                raise ResearchFormatError("duplicate protobuf package declaration")
            package=match.group(1)
            continue
        if text.startswith("import "):
            import_count+=1
            if import_count>64:
                raise ResearchFormatError("protobuf import declaration count exceeded")
            # Imports are never loaded, inspected, or returned as paths.
            continue
        match=_CLASS.fullmatch(text)
        if match:
            typ,name=match.groups()
            types[typ]+=1
            declarations.append((typ,name,line_number))
            depth+=1
            if depth>32 or len(declarations)>_MAX_DECLS:
                raise ResearchFormatError("protobuf declaration nesting/count exceeded")
            continue
        match=_RPC.fullmatch(text)
        if match:
            rpc_count+=1
            if rpc_count>_MAX_RPCS or types["service"]==0:
                raise ResearchFormatError("protobuf RPC capacity or service context invalid")
            declarations.append(("rpc",match.group(1),line_number))
            if len(declarations)>_MAX_DECLS:
                raise ResearchFormatError("protobuf declaration count exceeded")
            continue
        if text=="}":
            if depth<1:
                raise ResearchFormatError("protobuf source closes unknown scope")
            depth-=1
            continue
        # Field options, custom annotations, imports, extension URLs and
        # arbitrary unrecognized language syntax do not grant authority.
    if not observed_magic or depth!=0 or not types:
        raise ResearchFormatError("incomplete proto3 declaration inventory")
    retained=[
        "Protocol Buffers: proto3 inert declaration inventory",
        f"Declared package: {package or '[unspecified]'}",
        f"Messages: {types['message']}; enums: {types['enum']}; "
        f"services: {types['service']}; RPC declarations: {rpc_count}",
        f"External imports declared (not loaded): {import_count}",
    ]
    retained.extend(f"Declaration {kind}: {name}; source_line: {line}"
                    for kind,name,line in declarations[:128])
    retained.append("Source not compiled, executed, linked or authorized for RPC")
    return project_lines(retained,title="Protocol Buffer schema",max_chars=max_chars)
