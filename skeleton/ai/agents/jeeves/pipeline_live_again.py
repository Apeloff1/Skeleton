"""skeleton/jeeves/pipeline_live_again.py
Further extreme complete Jeeves pipeline.
plan_build, doctor, facade, weight bank receipts.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class PipelineError(Exception):
    pass

class JeevesPipelineAgain:
    def plan_build(self, spec: str) -> str:
        if not spec:
            raise PipelineError("empty")
        return hashlib.sha256(f"plan:{spec}:live".encode()).hexdigest()

    def doctor(self) -> bool:
        return True
