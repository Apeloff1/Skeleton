from dataclasses import dataclass

@dataclass(frozen=True)
class AbsorbItem:
    item_id: str
    text: str
    source_id: str
    priority: float = 0.0
