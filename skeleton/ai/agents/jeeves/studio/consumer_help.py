"""Consumer help.
End-user command help surface.
"""
from typing import Any, Dict

class ConsumerHelp:
    def show(self, topic: str = "all") -> Dict[str, Any]:
        topics = {"build": "brief -> sealed pack", "status": "current seal and progress", "all": "build, status, help"}
        if topic not in topics and topic != "all":
            return {"ok": False, "reason": "unknown_topic", "schema": "skeleton.help.v1"}
        return {"ok": True, "topic": topic, "text": topics.get(topic, topics["all"]), "reason": "ok", "schema": "skeleton.help.v1"}
