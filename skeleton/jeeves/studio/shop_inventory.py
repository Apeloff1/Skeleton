"""Shop inventory. Stock list with prices."""
from typing import Any, Dict, List
class ShopInventory:
    def __init__(self):
        self.stock = [{"id": "speed", "cost": 20}, {"id": "armor", "cost": 25}]
    def list(self) -> List[Dict[str, Any]]:
        return self.stock
