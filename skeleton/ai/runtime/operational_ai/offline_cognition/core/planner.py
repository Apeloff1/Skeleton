"""Dependency-backed operator work scheduling and bounded critical-path plans."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import identifier,integer,refuse,fingerprint
from .graph import topological,critical_path
@dataclass(frozen=True,slots=True)
class PlanTask:
    task_id:str
    duration_ms:int
    tokens:int
    role:str
    depends_on:tuple[str,...]
    def __post_init__(self):
        identifier(self.task_id)
        integer(self.duration_ms,minimum=1,maximum=3600000)
        integer(self.tokens,minimum=0,maximum=262144)
        if self.role not in ("model","retrieval","memory","verification","operator"):
            refuse("unapproved task execution role")
        if type(self.depends_on) is not tuple or len(self.depends_on)>128:
            refuse("dependency ceiling")
        for dep in self.depends_on:identifier(dep)
def plan_digest(record):
    """Canonical digest over JSON arrays; no tuple/list round-trip ambiguity."""
    fields={"order","edges","tokens","critical_path_ms",
            "critical_path","source_plan_not_authority_to_execute"}
    if type(record) is not dict or set(record)!=fields:
        refuse("exact source plan digest projection required")
    for k in ("order","edges","critical_path"):
        if type(record[k]) is not tuple:
            refuse("canonical ordered plan tuples required")
    if any(type(e) is not tuple or len(e)!=2 for e in record["edges"]):
        refuse("canonical dependency edge pairs required")
    if record["source_plan_not_authority_to_execute"] is not True:
        refuse("plan may not grant execution authority")
    return fingerprint({
        "order":list(record["order"]),
        "edges":[list(e) for e in record["edges"]],
        "tokens":record["tokens"],
        "critical_path_ms":record["critical_path_ms"],
        "critical_path":list(record["critical_path"]),
        "source_plan_not_authority_to_execute":True,
    })

def compile_plan(tasks,*,max_tasks=4096,max_tokens=262144):
    integer(max_tasks,minimum=1,maximum=100000)
    integer(max_tokens,minimum=1,maximum=262144)
    if type(tasks) not in (tuple,list) or not 1<=len(tasks)<=max_tasks:
        refuse("bounded plan inventory required")
    for t in tasks:
        if type(t) is not PlanTask:refuse("typed plan task required")
    tasks_by_id={t.task_id:t for t in tasks}
    if len(tasks_by_id)!=len(tasks):refuse("duplicate plan task")
    edges=[(dep,t.task_id) for t in tasks for dep in t.depends_on]
    order=topological(tuple(tasks_by_id),edges,maximum=max_tasks)
    token_cost=sum(t.tokens for t in tasks)
    if token_cost>max_tokens:refuse("plan exceeds operator token budget")
    critical=critical_path(tuple(tasks_by_id),edges,
        {t.task_id:t.duration_ms for t in tasks})
    record={"order":order,"edges":tuple(sorted(edges)),"tokens":token_cost,
            "critical_path_ms":critical["length"],
            "critical_path":critical["path"],
            "source_plan_not_authority_to_execute":True}
    return {**record,"sha256":plan_digest(record)}
