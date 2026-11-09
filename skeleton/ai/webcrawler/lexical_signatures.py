"""Conservative lexical candidates from Rust, Go, JS, TS, Java, C and C++.

Comment and literal stripping is finite and intentionally not a compiler:
no source code executes, imported modules are not opened, and reported
declarations are unverified, possibly approximate source observations.
"""
from __future__ import annotations
import re

from .source_signatures import (
    SourceSignatureError,SourceDeclaration,SourceSignatures,check_source,capped,
)
_NAME=r"([A-Za-z_][A-Za-z0-9_]{0,100})"
_JS=re.compile(r"^\s*(?:(?:export|default|declare|async|abstract)\s+){0,4}"
               r"(function|class|interface|type|enum)\s+"+_NAME+r"\b")
_JS_ARROW=re.compile(r"^\s*(?:export\s+)?(?:const|let)\s+"+_NAME+
                     r"\s*=\s*(?:async\s+)?(?:\([^=]{0,256}\)|[A-Za-z_][A-Za-z0-9_]*)\s*=>")
_RUST=re.compile(r"^\s*(?:pub(?:\([^)]{1,64}\))?\s+)?(?:async\s+)?"
                 r"(fn|struct|enum|trait|mod|type)\s+"+_NAME+r"\b")
_RUST_IMPORT=re.compile(r"^\s*(?:pub\s+)?use\s+([A-Za-z_][A-Za-z0-9_:]{0,255})\s*;")
_GO_FN=re.compile(r"^\s*func\s+(?:\([^)]{0,128}\)\s*)?"+_NAME+r"\s*\(")
_GO_TYPE=re.compile(r"^\s*type\s+"+_NAME+r"\s+(struct|interface)\b")
_JAVA=re.compile(r"^\s*(?:(?:public|private|protected|abstract|final|static|sealed)\s+){0,5}"
                 r"(?:class|interface|enum|record)\s+"+_NAME+r"\b")
_C_DECL=re.compile(r"^\s*(?:(?:static|inline|extern|unsigned|signed|const)\s+){0,6}"
                   r"(?:(?:[A-Za-z_][A-Za-z0-9_*&:<>]*)\s+){1,5}"+_NAME+r"\s*\(")
_IMPORT=re.compile(r"^\s*(?:import|from|include)\s+([A-Za-z_@][A-Za-z0-9_@./:-]{0,255})")
_SKIP=frozenset(("if","for","while","switch","catch","return","else","sizeof"))
_LANGS=frozenset(("typescript","javascript","rust","go","java","c","cpp"))


def strip_literals(raw:str)->str:
    out=[]
    i=0
    mode="code"
    escape=False
    while i<len(raw):
        c=raw[i]
        n=raw[i+1] if i+1<len(raw) else ""
        if mode=="code":
            if c=="/" and n in ("/","*"):
                mode="line" if n=="/" else "block"
                out.extend((" "," "));i+=2;continue
            if c in ("'",'"',chr(96)):
                mode=c;escape=False;out.append(" ");i+=1;continue
            out.append(c);i+=1;continue
        if mode=="line":
            out.append("\n" if c=="\n" else " ")
            if c=="\n":mode="code"
            i+=1;continue
        if mode=="block":
            if c=="*" and n=="/":
                out.extend((" "," "));i+=2;mode="code";continue
            out.append("\n" if c=="\n" else " ");i+=1;continue
        if escape:
            escape=False
        elif c=="\\":
            escape=True
        elif c==mode:
            mode="code"
        out.append("\n" if c=="\n" else " ")
        i+=1
    return "".join(out)


def extract_lexical_signatures(raw:str,language:str)->SourceSignatures:
    check_source(raw)
    if language not in _LANGS:
        raise SourceSignatureError("unsupported lexical language")
    source=strip_literals(raw)
    declarations=[]
    imports=[]
    for number,line in enumerate(source.splitlines(),1):
        if len(line)>8192:
            raise SourceSignatureError("lexical source line exceeds bound")
        found=[]
        if language in ("javascript","typescript"):
            m=_JS.match(line)
            if m:found.append((m.group(1),m.group(2)))
            m=_JS_ARROW.match(line)
            if m:found.append(("arrow_function",m.group(1)))
            m=_IMPORT.match(line)
            if m:imports.append(m.group(1))
        elif language=="rust":
            m=_RUST.match(line)
            if m:found.append((m.group(1),m.group(2)))
            m=_RUST_IMPORT.match(line)
            if m:imports.append(m.group(1))
        elif language=="go":
            m=_GO_FN.match(line)
            if m:found.append(("function",m.group(1)))
            m=_GO_TYPE.match(line)
            if m:found.append((m.group(2),m.group(1)))
        else:
            m=_JAVA.match(line)
            if m:found.append(("type",m.group(1)))
            m=_C_DECL.match(line)
            if m and m.group(1) not in _SKIP:
                found.append(("callable_candidate",m.group(1)))
        declarations.extend(SourceDeclaration(kind,symbol,number) for kind,symbol in found)
    return capped(language,declarations,imports,
                  syntax_mode="bounded_lexical_candidates",approximate=True)
