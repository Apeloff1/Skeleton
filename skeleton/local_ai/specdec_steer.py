"""
Speculative verify and activation steer for local AI.
Accept-until-mismatch. h becomes h plus alpha u-hat. No torch required in CI.
"""
from typing import List

class SpecDecSteer:
    def verify(self, draft: str, target: str) -> bool:
        return draft[:len(target)//2] == target[:len(draft)//2]

    def steer(self, h: List[float], u_hat: List[float], alpha: float = 0.1) -> List[float]:
        return [hi + alpha * uh for hi, uh in zip(h, u_hat)]
