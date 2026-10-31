"""Currency converter. Salvage to reputation or keys."""
from typing import Any, Dict
class CurrencyConverter:
    def convert(self, salvage: int, rate: float = 0.1) -> int:
        return int(salvage * rate)
