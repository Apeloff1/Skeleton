"""Exit portal. Triggers extract ending."""
from typing import Any, Dict
class ExitPortal:
    def __init__(self, room: int):
        self.room = room
    def use(self, salvage: int) -> Dict[str, Any]:
        return {"extract": True, "salvage": salvage}
