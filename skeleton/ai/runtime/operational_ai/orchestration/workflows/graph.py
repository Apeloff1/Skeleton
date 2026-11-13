"""Typed DAG nodes; no unconstrained model-authored arbitrary executable code."""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
import re
ID=re.compile(r'^[a-z][a-z0-9_-]{0,63}$')

class WorkflowError(ValueError):pass

@dataclass(frozen=True,slots=True)
class Step:
    id:str
    kind:str
    dependencies:tuple[str,...]
    input_key:str
    output_key:str
    max_attempts:int=1
    def __post_init__(self):
        if not ID.fullmatch(self.id) or self.kind not in {'context','infer','verify','persist','tool-proposal'}:
            raise WorkflowError('unsupported workflow step identity or kind')
        if any(not ID.fullmatch(x) for x in self.dependencies) or self.id in self.dependencies:
            raise WorkflowError('malformed workflow prerequisites')
        if not ID.fullmatch(self.input_key) or not ID.fullmatch(self.output_key):
            raise WorkflowError('invalid step input/output keys')
        if type(self.max_attempts) is not int or not 1<=self.max_attempts<=3:
            raise WorkflowError('step retry bound exceeded')

@dataclass(frozen=True,slots=True)
class WorkflowGraph:
    steps:tuple[Step,...]
    def __post_init__(self):
        if not self.steps or len(self.steps)>128:raise WorkflowError('workflow has no bounded steps')
        mapping={s.id:s for s in self.steps}
        if len(mapping)!=len(self.steps):raise WorkflowError('duplicate workflow step')
        for s in self.steps:
            if any(dep not in mapping for dep in s.dependencies):raise WorkflowError('unresolved workflow dependency')
        temporary=set();done=set()
        def visit(key:str):
            if key in temporary:raise WorkflowError('workflow dependency cycle')
            if key in done:return
            temporary.add(key)
            for dep in mapping[key].dependencies:visit(dep)
            temporary.remove(key);done.add(key)
        for s in self.steps:visit(s.id)
        if len({s.output_key for s in self.steps})!=len(self.steps):
            raise WorkflowError('duplicate output ownership')

    def ordered(self)->tuple[Step,...]:
        edges={s.id:set(s.dependencies) for s in self.steps}
        mapping={s.id:s for s in self.steps}
        out=[]
        while edges:
            ready=sorted(key for key,deps in edges.items() if not deps)
            if not ready:raise WorkflowError('cycle after graph validation')
            for key in ready:
                out.append(mapping[key]);del edges[key]
            for deps in edges.values():deps.difference_update(ready)
        return tuple(out)

    def critical_path(self)->int:
        depth={}
        for s in self.ordered():
            depth[s.id]=1+max((depth[d] for d in s.dependencies),default=0)
        return max(depth.values())
