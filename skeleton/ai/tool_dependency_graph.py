from dataclasses import dataclass
_ALLOWED_KINDS=frozenset({"runtime","schema","capability"})
@dataclass(frozen=True)
class ToolDependency: source:str; target:str; version:str; kind:str
@dataclass(frozen=True)
class ToolCompatibility: compatible:bool; reason:str
@dataclass(frozen=True)
class ToolGraph:
 dependencies:tuple[ToolDependency,...]; available:frozenset[tuple[str,str]]
 def validate(self):
  g={};seen=set()
  for d in self.dependencies:
   key=(d.source,d.target,d.version,d.kind)
   if not d.source or not d.target or not d.version or d.kind not in _ALLOWED_KINDS:return ToolCompatibility(False,"invalid dependency")
   if key in seen:return ToolCompatibility(False,"duplicate dependency")
   seen.add(key)
   if not any(tool==d.source for tool,_ in self.available):return ToolCompatibility(False,"unavailable source")
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
