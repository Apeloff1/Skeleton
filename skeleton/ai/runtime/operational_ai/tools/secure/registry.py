"""Static handler registration with frozen spec hashes and no dynamic imports."""
from __future__ import annotations
from typing import Any,Callable
from .spec import ToolSpec,ToolInvocation,ToolError
from .arguments import validate_arguments

class SecureRegistry:
    def __init__(self):
        self._specs={};self._handlers={};self._frozen=False

    def register(self,spec:ToolSpec,handler:Callable[[dict],dict])->None:
        if self._frozen:raise ToolError('tool registry is frozen')
        if spec.name in self._specs:raise ToolError('tool already registered')
        if not callable(handler):raise ToolError('tool handler must be callable')
        self._specs[spec.name]=spec;self._handlers[spec.name]=handler

    def freeze(self)->None:
        if not self._specs:raise ToolError('cannot freeze empty registry')
        self._frozen=True

    def resolve(self,invocation:ToolInvocation)->tuple[ToolSpec,Callable,dict]:
        if not self._frozen:raise ToolError('tools must be frozen before execution')
        spec=self._specs.get(invocation.tool_name)
        if spec is None or spec.digest!=invocation.expected_spec_sha:
            raise ToolError('unregistered or changed tool contract')
        return spec,self._handlers[spec.name],validate_arguments(spec,invocation.arguments)

    def listing(self)->tuple[tuple[str,str,str],...]:
        return tuple((s.name,s.digest,s.risk) for s in sorted(self._specs.values(),key=lambda s:s.name))
