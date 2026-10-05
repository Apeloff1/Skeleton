from dataclasses import dataclass
@dataclass(frozen=True)
class StrategyVersion: value:str
@dataclass(frozen=True)
class StrategyEvidence: benchmark_id:str; passed:bool
@dataclass(frozen=True)
class CognitiveStrategy: name:str; version:StrategyVersion; evidence:tuple[StrategyEvidence,...]; production:bool=False
def promote(s):
 if not s.evidence or not all(e.passed for e in s.evidence):raise PermissionError("strategy lacks passing evaluation evidence")
 return CognitiveStrategy(s.name,s.version,s.evidence,True)
