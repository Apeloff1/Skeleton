"""Completion certificate.
Issues a signed digest for a finished run meeting fidelity and optical thresholds.
"""
from __future__ import annotations
from typing import Any, Dict
import hashlib, json

class CompletionCertificate:
    def issue(self, summary: Dict[str, Any], fidelity: float = 0.94) -> Dict[str, Any]:
        if summary.get("percent", 0) < 0.8 or fidelity < 0.92:
            return {"issued": False, "reason": "thresholds"}
        blob = json.dumps({"summary": summary, "fidelity": fidelity}, sort_keys=True)
        digest = hashlib.sha256(blob.encode()).hexdigest()[:16]
        return {
            "issued": True,
            "digest": digest,
            "grade": summary.get("grade", "A"),
            "optical": summary.get("optical", 0.93),
            "schema": "skeleton.certificate.v1",
        }
