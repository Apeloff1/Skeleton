"""Canonical JSON serialization for CI feedback consumed by build automation."""
from __future__ import annotations
import json
from dataclasses import asdict
from .ci_feedback import Feedback
def render(feedback:Feedback)->str:
 return json.dumps({"schema":"autonomous-studio.ci-feedback.v1","head_sha":feedback.evidence.head_sha,"ci_evidence_sha256":feedback.evidence.digest(),"green":feedback.evidence.green() if not feedback.pending else False,"pending":feedback.pending,"quarantined":feedback.quarantined,"repairs":[asdict(x) for x in feedback.repairs]},sort_keys=True,indent=2)+"\n"
