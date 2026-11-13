"""Consumer CLI entry.
End-user command surface for brief -> build -> seal.
"""
from typing import Any, Dict

class ConsumerCLI:
    def run(self, command: str, brief: str = "", optical: float = 0.95) -> Dict[str, Any]:
        if not isinstance(command, str) or not command.strip():
            return {"ok": False, "reason": "empty_command", "schema": "skeleton.consumer.cli.v1"}
        if command == "build":
            if not brief.strip():
                return {"ok": False, "reason": "empty_brief", "schema": "skeleton.consumer.cli.v1"}
            ok = optical >= 0.9
            return {"ok": ok, "command": command, "brief": brief, "sealed": ok, "reason": "ok" if ok else "gates_failed", "schema": "skeleton.consumer.cli.v1"}
        if command == "status":
            return {"ok": True, "command": command, "sealed": True, "reason": "ok", "schema": "skeleton.consumer.cli.v1"}
        return {"ok": False, "reason": "unknown_command", "schema": "skeleton.consumer.cli.v1"}
