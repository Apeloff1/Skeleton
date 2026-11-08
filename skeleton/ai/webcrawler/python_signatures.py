"""Finite AST-only Python symbol and import topology, no import/compile/eval."""
from __future__ import annotations
import ast
import re

from .source_signatures import (
    SourceSignatureError,SourceDeclaration,SourceSignatures,check_source,capped,
)
_IDENT=re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,100}$")
_MODULE=re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,255}$")


def extract_python_signatures(raw:str)->SourceSignatures:
    check_source(raw)
    try:
        tree=ast.parse(raw,mode="exec",type_comments=False)
    except (SyntaxError,ValueError,RecursionError,MemoryError) as exc:
        raise SourceSignatureError("invalid or overdeep Python AST") from exc
    declarations=[]
    imports=[]
    stack=[(tree,0,())]
    visited=0
    while stack:
        node,depth,scope=stack.pop()
        visited+=1
        if visited>16384 or depth>96:
            raise SourceSignatureError("Python AST node/depth capacity exceeded")
        if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
            name=node.name
            if _IDENT.fullmatch(name):
                kind=("class" if isinstance(node,ast.ClassDef)
                      else "async_function" if isinstance(node,ast.AsyncFunctionDef)
                      else "function")
                arity=None
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    args=node.args
                    arity=(len(args.posonlyargs)+len(args.args)+len(args.kwonlyargs)
                           +int(args.vararg is not None)+int(args.kwarg is not None))
                declarations.append(SourceDeclaration(
                    kind=kind,symbol=".".join((*scope,name)),line=node.lineno,
                    arity=arity,asynchronous=isinstance(node,ast.AsyncFunctionDef),
                ))
                scope=(*scope,name)
        elif isinstance(node,ast.Import):
            for row in node.names:
                if _MODULE.fullmatch(row.name):
                    imports.append(row.name)
        elif isinstance(node,ast.ImportFrom):
            if node.module and _MODULE.fullmatch(node.module):
                imports.append("."*node.level+node.module)
        children=list(ast.iter_child_nodes(node))
        if len(children)>1024:
            raise SourceSignatureError("Python AST child fanout exceeded")
        stack.extend((child,depth+1,scope) for child in reversed(children))
    return capped(
        "python",declarations,imports,syntax_mode="python_ast",
        approximate=False,
    )
