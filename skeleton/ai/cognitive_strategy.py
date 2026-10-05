from dataclasses import dataclass
@dataclass(frozen=True)
class StrategyVersion: value:str
@dataclass(frozen=True)
class StrategyEvidence: benchmark_id:str; passed:bool
@dataclass(frozen=True)
class CognitiveStrategy:
 name:str; version:StrategyVersion; evidence:tuple[StrategyEvidence,...]; production:bool=False
 def __post_init__(self):
  if not self.name or not self.version.value or not isinstance(self.production,bool) or any(not e.benchmark_id or not isinstance(e.passed,bool) for e in self.evidence):raise ValueError("strategy identity required")
  if self.production and (not self.evidence or not all(e.passed for e in self.evidence)):raise PermissionError("production strategy requires passing evidence")
def promote(s):
 if s.production:return s
 if not s.evidence or not all(e.passed for e in s.evidence):raise PermissionError("strategy lacks passing evaluation evidence")
 return CognitiveStrategy(s.name,s.version,s.evidence,True)
