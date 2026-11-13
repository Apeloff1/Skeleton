"""New game plus. Carries optical and skills forward."""
from typing import Any, Dict
class NewGamePlus:
    def start(self, prior: Dict[str, Any]) -> Dict[str, Any]:
        return {"optical_bonus": prior.get("optical", 0.9) * 0.1, "skills": prior.get("skills", []), "cycle": prior.get("cycle", 0) + 1}
