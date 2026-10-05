"""Constraint-preserving task decomposition for VOL-313."""
from dataclasses import dataclass
@dataclass(frozen=True,order=True)
class TaskDependency: source:str; target:str
@dataclass(frozen=True)
class Subtask:
 task_id:str; constraints:tuple[str,...]; authority:str; acceptance:tuple[str,...]; integration:bool=False
@dataclass(frozen=True)
class TaskDecomposition:
 parent_id:str; parent_constraints:tuple[str,...]; parent_authority:str; subtasks:tuple[Subtask,...]; dependencies:tuple[TaskDependency,...]; max_subtasks:int=32
 def __post_init__(self):
  ids=[x.task_id for x in self.subtasks]
  if not self.parent_id or not self.parent_authority or len(ids)!=len(set(ids)):raise ValueError("invalid task identity")
  if not self.subtasks or len(self.subtasks)>self.max_subtasks:raise ValueError("invalid decomposition size")
  if sum(x.integration for x in self.subtasks)!=1:raise ValueError("exactly one integration step required")
  required=set(self.parent_constraints)
  for x in self.subtasks:
   if x.authority!=self.parent_authority or not required.issubset(x.constraints):raise ValueError("subtask lost parent authority/constraint")
  known=set(ids); graph={x:[] for x in ids}
  for e in self.dependencies:
   if e.source not in known or e.target not in known or e.source==e.target:raise ValueError("invalid dependency")
   graph[e.source].append(e.target)
  visiting=set();done=set()
  def visit(n):
   if n in visiting:raise ValueError("dependency cycle")
   if n in done:return
   visiting.add(n)
   for q in graph[n]:visit(q)
   visiting.remove(n);done.add(n)
  for n in ids:visit(n)
