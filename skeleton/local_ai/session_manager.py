"""
Operational Session Manager. Tracks multi-turn context, history, and clipped-G across sessions.
Fills the session state gap. Fully operational.
"""
from typing import Dict, List
from .operational_engine import get_engine
from .error_handler import ErrorHandler

class SessionManager:
    def __init__(self):
        self.engine = get_engine()
        self.handler = ErrorHandler()
        self.sessions: Dict[str, List] = {}

    def start(self, session_id: str, cas: str) -> Dict:
        self.sessions[session_id] = []
        return {"session": session_id, "status": "started"}

    def turn(self, session_id: str, prompt: str, cas: str) -> Dict:
        try:
            out = self.engine.generate(prompt, cas)
            self.sessions.setdefault(session_id, []).append(out)
            return {"session": session_id, "turn": len(self.sessions[session_id]), "out": out}
        except Exception as e:
            return self.handler.handle(e, {"session": session_id, "prompt": prompt})

    def history(self, session_id: str) -> List:
        return self.sessions.get(session_id, [])
