"""Bounded inert source declarations, never executable or verified content."""
from __future__ import annotations
from dataclasses import dataclass

MAX_CHARS=262144
MAX_LINES=8192
MAX_DECLS=128
MAX_IMPORTS=96


class SourceSignatureError(ValueError):
    """Source exceeds finite analysis limits or is malformed."""


@dataclass(frozen=True)
class SourceDeclaration:
    kind:str
    symbol:str
    line:int
    arity:int|None=None
    asynchronous:bool=False
    unverified:bool=True


@dataclass(frozen=True)
class SourceSignatures:
    language:str
    declarations:tuple[SourceDeclaration,...]
    imports:tuple[str,...]
    syntax_mode:str
    approximate:bool
    truncated:bool
    source_executed:bool=False
    references_fetched:bool=False
    declarations_verified:bool=False


def check_source(raw:str)->None:
    if (not isinstance(raw,str) or len(raw)>MAX_CHARS
            or len(raw.splitlines())>MAX_LINES
            or "\x00" in raw or "\x1b" in raw):
        raise SourceSignatureError("external source complexity or control-byte bound")


def capped(language,decls,imports,*,syntax_mode,approximate):
    seen={}
    for item in decls:
        if not isinstance(item,SourceDeclaration):
            raise SourceSignatureError("invalid source declaration")
        seen.setdefault((item.kind,item.symbol,item.line),item)
    definitions=sorted(seen.values(),key=lambda x:(x.line,x.kind,x.symbol))
    imports=sorted(set(imports))
    return SourceSignatures(
        language=language,declarations=tuple(definitions[:MAX_DECLS]),
        imports=tuple(imports[:MAX_IMPORTS]),syntax_mode=syntax_mode,
        approximate=approximate,
        truncated=len(definitions)>MAX_DECLS or len(imports)>MAX_IMPORTS,
    )
