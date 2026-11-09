"""Cutscene script.
Ending for cutscene_director.gd.
"""
from typing import Any, Dict

class CutsceneScript:
    def emit(self, ending: str) -> Dict[str, Any]:
        if not isinstance(ending, str) or not ending.strip():
            return {"ok": False, "reason": "empty_ending", "schema": "skeleton.cutscene.script.v1"}
        text = f"var ending = \\\"{ending}\\\"\\nfunc play():\\n\\tpass"
        return {"ok": True, "ending": ending, "text": text, "reason": "ok", "schema": "skeleton.cutscene.script.v1"}
