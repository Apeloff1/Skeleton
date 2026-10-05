from dataclasses import dataclass
@dataclass(frozen=True)
class ResearchRisk: human_subjects:bool; sensitive_data:bool; dual_use:bool
@dataclass(frozen=True)
class EthicsReview: review_id:str; risk:ResearchRisk; consent:bool; oversight_id:str|None
@dataclass(frozen=True)
class EthicsDecision: approved:bool; reason:str
def decide(r):
 sensitive=any((r.risk.human_subjects,r.risk.sensitive_data,r.risk.dual_use))
 if sensitive and (not r.consent or not r.oversight_id):return EthicsDecision(False,"consent and oversight required")
 return EthicsDecision(True,"review criteria satisfied")
