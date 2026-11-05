"""Only a caller-authored plan can enter the durable workflow engine."""
from __future__ import annotations
from dataclasses import dataclass
from ..core.canonical import identifier,text,canonical,digest,uint
from ..core.errors import Invalid
KINDS=frozenset(('model','read','review','tool'))
@dataclass(frozen=True,slots=True)
class Step:
    step_id:str
    kind:str
    instruction:str
    depends_on:tuple[str,...]=()
    resource:str='none'
    def __post_init__(self):
        identifier(self.step_id,'step');text(self.instruction,'instruction',maximum=32768)
        if self.kind not in KINDS:raise Invalid('unsupported step kind')
        if not isinstance(self.depends_on,tuple) or len(self.depends_on)>64:raise Invalid('invalid dependencies')
        if len(set(self.depends_on))!=len(self.depends_on):raise Invalid('duplicate dependency')
        for dep in self.depends_on:identifier(dep,'dependency')
        identifier(self.resource,'resource')
        if self.kind!='tool' and self.resource!='none':raise Invalid('non-tool cannot claim resource')
    def record(self):return {'id':self.step_id,'kind':self.kind,'instruction':self.instruction,'depends_on':list(self.depends_on),'resource':self.resource}
@dataclass(frozen=True,slots=True)
class Plan:
    plan_id:str
    session_id:str
    steps:tuple[Step,...]
    purpose:str
    def __post_init__(self):
        identifier(self.plan_id,'plan');identifier(self.session_id,'session');text(self.purpose,'purpose',maximum=8192)
        if not isinstance(self.steps,tuple) or not self.steps:raise Invalid('plan must have typed steps')
        if any(not isinstance(s,Step) for s in self.steps):raise Invalid('untyped plan step')
        if len({s.step_id for s in self.steps})!=len(self.steps):raise Invalid('duplicate step ID')
    def record(self):return {'schema':'agent.plan.v1','id':self.plan_id,'session':self.session_id,'purpose':self.purpose,'steps':[s.record() for s in self.steps]}
    def sha256(self):return digest(self.record())
