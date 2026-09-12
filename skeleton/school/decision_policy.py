"""Evidence-aware deterministic arbitration for Jeeves."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Sequence
from skeleton.school.knowledge import KnowledgeState
class ArbitrationAction(str,Enum):
 RETEACH="reteach"; RETRIEVE="retrieve"; PRACTICE="practice"; CHALLENGE="challenge"; TRANSFER="transfer"; REFLECT="reflect"; PAUSE="pause"
@dataclass(frozen=True)
class EvidenceSignal:
 name:str; value:float; reliability:float=1.
 def __post_init__(self):
  if not 0<=self.value<=1 or not 0<=self.reliability<=1: raise ValueError("signal value and reliability must be in [0, 1]")
 @property
 def effective(self): return self.value*self.reliability
@dataclass(frozen=True)
class ArbitrationResult:
 action:ArbitrationAction; confidence:float; rationale:tuple[str,...]; signals:tuple[EvidenceSignal,...]
def arbitrate(state:KnowledgeState,skill_id:str,*,signals:Sequence[EvidenceSignal]=(),energy:float=1.,recent_failure:bool=False,transfer_ready:bool=False):
 if not skill_id: raise ValueError("skill_id cannot be empty")
 energy=max(0.,min(1.,energy)); mastery=state.mastery(skill_id); contradiction=any(s.name=="contradiction" and s.effective>=.5 for s in signals); retention=next((s.effective for s in signals if s.name=="retention"),mastery); independence=next((s.effective for s in signals if s.name=="independence"),mastery); reasons=[]
 if skill_id in state.misconceptions or contradiction: action=ArbitrationAction.RETEACH; reasons.append("repair conflicting or incorrect belief before escalation")
 elif energy<.25: action=ArbitrationAction.PAUSE; reasons.append("energy budget is too low for high-load work")
 elif recent_failure or mastery<.4: action=ArbitrationAction.PRACTICE; reasons.append("recent evidence indicates a foundational gap")
 elif transfer_ready and independence>=.7: action=ArbitrationAction.TRANSFER; reasons.append("mastery and independence support transfer")
 elif mastery>=.85 and retention>=.75: action=ArbitrationAction.CHALLENGE; reasons.append("strong mastery and retention support challenge")
 elif retention<.6: action=ArbitrationAction.RETRIEVE; reasons.append("retention evidence calls for retrieval")
 else: action=ArbitrationAction.PRACTICE; reasons.append("continue deliberate practice at current difficulty")
 confidence=min(1.,max(0.,.35+.45*mastery+.2*(1. if signals else 0.))); confidence*=.65 if contradiction else 1.
 return ArbitrationResult(action,confidence,tuple(reasons),tuple(signals))
