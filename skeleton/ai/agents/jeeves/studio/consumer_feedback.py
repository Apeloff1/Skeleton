"""Consumer feedback.
End-user feedback collection.
"""
from typing import Any, Dict

class ConsumerFeedback:
    def submit(self, score: int, text: str = "") -> Dict[str, Any]:
        if not isinstance(score, int) or score < 1 or score > 5:
            return {"ok": False, "reason": "bad_score", "schema": "skeleton.feedback.v1"}
        return {"ok": True, "score": score, "text": text, "reason": "ok", "schema": "skeleton.feedback.v1"}
