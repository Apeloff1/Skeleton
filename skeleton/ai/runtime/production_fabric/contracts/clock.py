"""Logical ordering without wall-clock dependency for deterministic simulation."""
from dataclasses import dataclass
from .errors import ContractError

@dataclass(frozen=True, order=True)
class LogicalTime:
    epoch: int = 0
    tick: int = 0

    def __post_init__(self):
        if not all((isinstance(v, int) and (not isinstance(v, bool)) and (0 <= v < 2 ** 63) for v in (self.epoch, self.tick))):
            raise ContractError('invalid logical timestamp')

    def advance(self, steps: int=1) -> 'LogicalTime':
        if not isinstance(steps, int) or steps < 1 or self.tick + steps >= 2 ** 63:
            raise ContractError('tick overflow or nonpositive advance')
        return LogicalTime(self.epoch, self.tick + steps)

    def next_epoch(self) -> 'LogicalTime':
        return LogicalTime(self.epoch + 1, 0)
