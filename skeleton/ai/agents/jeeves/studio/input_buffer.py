"""Input buffer. Queues recent actions for combo detection."""
from typing import Any, List
class InputBuffer:
    def __init__(self, size: int = 8):
        self.buf: List[str] = []
        self.size = size
    def push(self, action: str) -> None:
        self.buf.append(action)
        self.buf = self.buf[-self.size:]
    def combo(self, seq: List[str]) -> bool:
        return self.buf[-len(seq):] == seq if len(self.buf) >= len(seq) else False
