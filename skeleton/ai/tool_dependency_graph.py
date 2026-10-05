from dataclasses import dataclass
@dataclass(frozen=True)
class ToolDependency: source:str; target:str; version:str; kind:str
@dataclass(frozen=True)
class ToolCompatibility: compatible:bool; reason:str
@dataclass(frozen=True)
class ToolGraph:
 dependencies:tuple[ToolDependency,...]; available:frozenset[tuple[str,str]]
 def validate(self):
  g={}
  for d in self.dependencies:
   if (d.target,d.version) not in self.available:return ToolCompatibility(False,"unavailable dependency")
   g.setdefault(d.source,[]).append(d.target)
  visiting=set();done=set()
  def visit(n):
   if n in visiting:raise ValueError("cyclic tool chain")
   if n in done:return
   visiting.add(n)
   for x in g.get(n,()):visit(x)
   visiting.remove(n);done.add(n)
  for n in g:visit(n)
  return ToolCompatibility(True,"compatible")
